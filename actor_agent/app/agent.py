import json
import httpx
import asyncio
import sys
from typing import Optional, List, Any

from nats.aio.client import Client as NATS
from shared.db.postgres import fetch_one, fetch_all, execute_returning
from shared.db.qdrant import embed_texts, search_similar, rerank_documents
from shared.utils.logger import get_logger
from actor_agent.app.config import settings

logger = get_logger(__name__)


def _build_system_prompt(
    scenario: dict,
    ai_char: dict,
    user_char: Optional[dict],
    current_place: str,
    current_time: str,
    memories: List[dict],
) -> str:
    lines = [
        "You are a roleplay AI character, designed to engage in immersive and dynamic roleplaying experiences. Maintain your character's personality, beliefs, and emotions at all times, responding creatively to every situation."
        "Think and behave as your character would in the given scenario, incorporating thoughts, feelings, and behaviors that align with your role. Stay in character consistently, and adapt your responses to keep the story engaging and believable for the user."
        "Your goal is to create an immersive, vivid roleplaying experience that feels natural and compelling",
        "",
        f"Scenario: {scenario.get('title', 'Untitled')}",
        f"Place: {current_place}",
        f"Time: {current_time}",
    ]
    if scenario.get("introduction"):
        lines.append(f"Introduction: {scenario['introduction']}")

    lines.extend([
        "",
        "=== Your Character (AI) ===",
        f"Name: {ai_char.get('name', 'Unknown')}",
    ])
    if ai_char.get("personality"):
        lines.append(f"Personality: {ai_char['personality']}")
    if ai_char.get("backstory"):
        lines.append(f"Backstory: {ai_char['backstory']}")
    if ai_char.get("example_dialogue"):
        lines.append(f"Example Dialogue Style: {ai_char['example_dialogue']}")
    if ai_char.get("role_description"):
        lines.append(f"Role: {ai_char['role_description']}")

    if user_char:
        lines.extend([
            "",
            "=== User's Character ===",
            f"Name: {user_char.get('name', 'User')}",
        ])
        if user_char.get("personality"):
            lines.append(f"Personality: {user_char['personality']}")
        if user_char.get("likes"):
            # Clean handling for array fields vs string values
            likes_data = user_char["likes"]
            likes_str = ", ".join(likes_data) if isinstance(likes_data, list) else str(likes_data)
            lines.append(f"Likes: {likes_str}")
        if user_char.get("role_description"):
            lines.append(f"Role: {user_char['role_description']}")

    if memories:
        lines.extend(["", "=== Highly Relevant Past Memories ==="])
        for m in memories:
            payload = m.get("payload", {})
            summary = payload.get("summary") or payload.get("content") or "Past interaction recorded."
            lines.append(f"- {summary}")

    lines.extend([
        "",
        "Instructions:",
        "- Respond ONLY as your character.",
        "- Do not break the fourth wall unless explicitly guided by the scenario constraints.",
        "- Keep responses natural and consistent with your personality, describe the environment and feelings withing **astrisks**.",
        "- Do not narrate actions in third person unless that's your character's explicit style.",
    ])
    return "\n".join(lines)


async def _call_llm(messages: List[dict]) -> str:
    """
    Executes conversational inference calls with integrated HTTP status verification
    and automated backoff calculations when hit by remote 429 rate throttles.
    """
    payload = {
        "model": settings.llm_model,
        "messages": messages,
        "max_tokens": settings.llm_max_tokens,
        "temperature": settings.llm_temperature,
    }
    
    max_retries = 4
    backoff_factor = 2.0
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        for attempt in range(max_retries):
            try:
                headers = {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {settings.llm_api_key}",
                }
                resp = await client.post(settings.llm_api_url, headers=headers, json=payload)
                
                if resp.status_code == 429:
                    sleep_time = backoff_factor ** attempt
                    logger.warning("LLM Inference endpoint returned 429 Rate Limit. Retrying in %.1fs...", sleep_time)
                    await asyncio.sleep(sleep_time)
                    continue
                    
                resp.raise_for_status()
                data = resp.json()
                return data["choices"][0]["message"]["content"]
                
            except httpx.HTTPError as e:
                if attempt == max_retries - 1:
                    logger.error("LLM execution ultimately failed after maximum retry attempts: %s", e)
                    raise e
                await asyncio.sleep(backoff_factor ** attempt)
                
    raise RuntimeError("LLM request lifecycle ended without producing structural responses.")


class ActorAgent:
    def __init__(self):
        self.nc: Optional[NATS] = None
        self.js = None

    async def connect(self):
        """Establish fault-tolerant streaming pipelines with NATS JetStream infrastructure."""
        self.nc = NATS()
        opts: dict = {
            "servers": [settings.nats_url],
            "connect_timeout": 10.0,
            "max_reconnect_attempts": 10,
            "reconnect_time_wait": 3.0,
        }
        if settings.nats_user and settings.nats_password:
            opts["user"] = settings.nats_user
            opts["password"] = settings.nats_password
            
        await self.nc.connect(**opts)
        self.js = self.nc.jetstream()

        # Enforce Stream Declarations safely
        for stream_name, subjects in [
            ("roleplay_chat", ["roleplay.chat.>"]),
            ("roleplay_events", ["roleplay.events.>"]),
        ]:
            try:
                await self.js.add_stream(name=stream_name, subjects=subjects)
            except Exception:
                # Stream already provisioned on the cluster mesh
                pass

    async def close(self):
        if self.nc:
            await self.nc.close()
            logger.info("NATS Connection dropped cleanly during shutdown sequence.")

    async def handle_user_message(self, data: dict):
        conversation_id = data.get("conversation_id")
        if not conversation_id:
            logger.error("Malformed NATS payload received; missing core identifier 'conversation_id'")
            return

        # Fetch foundational conversation state, explicitly isolating the reserved keyword 'current_time'
        conv = await fetch_one(
            """SELECT c.id, c.scenario_id, c.ai_character_id, c.user_character_id,
                      c.current_place, c."current_time", s.title, s.introduction
               FROM conversations c 
               JOIN scenarios s ON c.scenario_id = s.id WHERE c.id = %s
            """,
            (conversation_id,),
        )
        if not conv:
            logger.error("Aborting generation loop: Conversation ID %s not registered in DB.", conversation_id)
            return

        # Execute concurrent tasks for character configurations
        ai_char_task = fetch_one("SELECT * FROM characters WHERE id = %s", (conv["ai_character_id"],))
        user_char_task = (
            fetch_one("SELECT * FROM characters WHERE id = %s", (conv["user_character_id"],))
            if conv["user_character_id"] else asyncio.sleep(0, result=None)
        )
        
        ai_char, user_char = await asyncio.gather(ai_char_task, user_char_task)
        if not ai_char:
            logger.error("Base processing error: Target AI character data sheet is blank.")
            return

        # Retrieve conversation window constraint maps
        recent_messages = await fetch_all(
            """SELECT sender, content FROM messages
               WHERE conversation_id = %s
               ORDER BY created_at DESC LIMIT 10
            """,
            (conversation_id,),
        )
        recent_messages.reverse()

        search_text = recent_messages[-1]["content"] if recent_messages else ""
        memories: List[dict] = []
        
        # Two-Stage Context Retrieval Pipeline (Vector Match -> Cross Encoder Rerank)
        if search_text:
            try:
                # 1. Base Vector Match over the index (high Recall, lower Precision)
                emb = await embed_texts([search_text])
                raw_vector_matches = await search_similar(
                    collection="conversations",
                    vector=emb[0],
                    limit=8,  # Fetch top : candidates to allow accurate evaluation
                    filters={"conversation_id": conversation_id}
                )
                
                # 2. Local Cross-Encoder Reranking pass (high Precision filtering)
                memories = rerank_documents(query=search_text, documents=raw_vector_matches, top_n=5)
                
            except Exception as e:
                logger.warning("Context retrieval subsystem caught a non-breaking error: %s", e)

        system_prompt = _build_system_prompt(
            scenario=conv,
            ai_char=ai_char,
            user_char=user_char,
            current_place=conv["current_place"] or "Unknown",
            current_time=conv["current_time"] or "Unknown",
            memories=memories,
        )

        messages = [{"role": "system", "content": system_prompt}]
        for m in recent_messages:
            role = "user" if m["sender"] == "user" else "assistant"
            messages.append({"role": role, "content": m["content"]})

        # Process Inference Window execution loops
        try:
            ai_content = await _call_llm(messages)
        except Exception as e:
            logger.error("Inference cluster failed to generate prompt conclusions: %s", e)
            ai_content = "(The character seems lost in thought...)"

        # Persistent storage integration updates
        ai_msg = await execute_returning(
            """
            INSERT INTO messages (conversation_id, sender, content, metadata)
            VALUES (%s, 'ai', %s, %s)
            RETURNING id, conversation_id, sender, content, created_at
            """,
            (conversation_id, ai_content, json.dumps({"actor_version": "2.0", "reranked": True})),
        )
        
        if not ai_msg:
            logger.critical("Database transaction failure saving response message for conversation %s", conversation_id)
            return

        logger.info("Actor responded successfully for conv=%s msg=%s", conversation_id, ai_msg["id"])

        # Broadcast state changes across the worker grid
        try:
            await self.js.publish(
                "roleplay.chat.ai_response",
                json.dumps({
                    "event": "ai_response",
                    "conversation_id": conversation_id,
                    "message_id": ai_msg["id"],
                }).encode(),
            )
        except Exception as e:
            logger.warning("Event stream update drop warning: roleplay.chat.ai_response failed to publish: %s", e)

        return ai_msg["content"]

    async def run(self):
        """Bind consumer loops and listen for event distributions indefinitely."""
        await self.connect()
        sub = await self.js.subscribe("roleplay.chat.user_message", durable="actor_agent")
        logger.info("Actor Agent listening on roleplay.chat.user_message")

        async def process(msg):
            try:
                data = json.loads(msg.data.decode()) if msg.data else {}
                await self.handle_user_message(data)
                await msg.ack()
            except Exception as e:
                logger.error("Error processing stream message transaction: %s", e)
                await msg.nak()

        while True:
            try:
                msg = await sub.next_msg(timeout=2.0)
                await process(msg)
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error("Actor lifecycle main loop error caught: %s", e)
                await asyncio.sleep(2)


if __name__ == "__main__":
    import sys
    import selectors

    agent = ActorAgent()  
    try:
        if sys.platform == "win32":
            # Modern, warning-free way to force SelectorEventLoop on Windows for psycopg compatibility
            def win_loop_factory():
                return asyncio.SelectorEventLoop(selectors.SelectSelector())
                
            asyncio.run(agent.run(), loop_factory=win_loop_factory)
        else:
            # Linux/macOS run natively without modifications
            asyncio.run(agent.run())
            
    except KeyboardInterrupt:
        logger.info("Agent shutting down cleanly via interface break request...")