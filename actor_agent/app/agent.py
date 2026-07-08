import json
import httpx
from typing import Optional, List, Any

from nats.aio.client import Client as NATS
from shared.db.postgres import fetch_one, fetch_all, execute_returning
from shared.db.qdrant import embed_texts, search_similar
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
        "You are a roleplay AI character. Stay in character at all times.",
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
            lines.append(f"Likes: {', '.join(user_char['likes'])}")
        if user_char.get("role_description"):
            lines.append(f"Role: {user_char['role_description']}")

    if memories:
        lines.extend(["", "=== Relevant Past Memories ==="])
        for m in memories[:5]:
            lines.append(f"- {m.get('payload', {}).get('summary', 'Memory')}")

    lines.extend([
        "",
        "Instructions:",
        "- Respond ONLY as your character.",
        "- Do not break the fourth wall unless the scenario demands it.",
        "- Keep responses natural and consistent with your personality.",
        "- Do not narrate actions in third person unless that's your character's style.",
    ])
    return "\n".join(lines)


async def _call_llm(messages: List[dict]) -> str:
    payload = {
        "model": settings.llm_model,
        "messages": messages,
        "max_tokens": settings.llm_max_tokens,
        "temperature": settings.llm_temperature,
    }
    async with httpx.AsyncClient(timeout=60.0) as client:
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {settings.llm_api_key}",
        }
        resp = await client.post(settings.llm_api_url, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]


class ActorAgent:
    def __init__(self):
        self.nc: Optional[NATS] = None
        self.js = None

    async def connect(self):
        self.nc = NATS()
        opts: Any = {"servers": settings.nats_url}
        if settings.nats_user and settings.nats_password:
            opts["user"] = settings.nats_user
            opts["password"] = settings.nats_password
        await self.nc.connect(**opts)
        self.js = self.nc.jetstream()

        for stream_name, subjects in [
            ("roleplay_chat", ["roleplay.chat.>"]),
            ("roleplay_events", ["roleplay.events.>"]),
        ]:
            try:
                await self.js.add_stream(name=stream_name, subjects=subjects)
            except Exception:
                pass

    async def close(self):
        if self.nc:
            await self.nc.close()

    async def handle_user_message(self, data: dict):
        conversation_id = data["conversation_id"]

        conv = await fetch_one(
            """
            SELECT c.id, c.scenario_id, c.ai_character_id, c.user_character_id,
                   c.current_place, c.current_time, s.title, s.introduction
            FROM conversations c
            JOIN scenarios s ON c.scenario_id = s.id
            WHERE c.id = %s
            """,
            (conversation_id,),
        )
        if not conv:
            logger.error("Conversation %s not found", conversation_id)
            return

        ai_char = await fetch_one(
            "SELECT * FROM characters WHERE id = %s",
            (conv["ai_character_id"],),
        )
        user_char = None
        if conv["user_character_id"]:
            user_char = await fetch_one(
                "SELECT * FROM characters WHERE id = %s",
                (conv["user_character_id"],),
            )

        recent_messages = await fetch_all(
            """
            SELECT sender, content FROM messages
            WHERE conversation_id = %s
            ORDER BY created_at DESC
            LIMIT 20
            """,
            (conversation_id,),
        )
        recent_messages.reverse()

        search_text = recent_messages[-1]["content"] if recent_messages else ""
        memories: List[dict] = []
        if search_text:
            try:
                emb = await embed_texts([search_text])
                memories = await search_similar(
                    "conversations", emb[0], limit=5,
                    filters={"must": [{"key": "conversation_id", "match": {"value": conversation_id}}]}
                )
            except Exception as e:
                logger.warning("Memory search failed: %s", e)

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

        try:
            ai_content = await _call_llm(messages)
        except Exception as e:
            logger.error("LLM call failed: %s", e)
            ai_content = "(The character seems lost in thought...)"

        ai_msg = await execute_returning(
            """
            INSERT INTO messages (conversation_id, sender, content, metadata)
            VALUES (%s, 'ai', %s, %s)
            RETURNING id, conversation_id, sender, content, created_at
            """,
            (conversation_id, ai_content, json.dumps({"actor": True})),
        )
        logger.info("Actor responded for conv=%s msg=%s", conversation_id, ai_msg["id"])

        # Publish ai_response event for Director agent (reuse same connection)
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
            logger.warning("Failed to publish ai_response: %s", e)

        return ai_msg["content"]

    async def run(self):
        await self.connect()
        sub = await self.js.subscribe("roleplay.chat.user_message", durable="actor_agent")
        logger.info("Actor Agent listening on roleplay.chat.user_message")

        async def process(msg):
            try:
                data = json.loads(msg.data.decode()) if msg.data else {}
                await self.handle_user_message(data)
                await msg.ack()
            except Exception as e:
                logger.error("Error processing message: %s", e)
                await msg.nak()

        async for msg in sub:
            await process(msg)


if __name__ == "__main__":
    import asyncio
    agent = ActorAgent()
    asyncio.run(agent.run())
