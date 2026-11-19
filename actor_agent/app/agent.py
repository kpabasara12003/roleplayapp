# actor_agent/app/agent.py
from shared.utils.observability import traced
import sys
import uuid
import json
import httpx
from shared.utils.providers import admission, retry_delay
import asyncio
import selectors
from typing import Optional, List
from datetime import datetime, timezone

from shared.db.postgres import fetch_one, fetch_all, execute_returning, transaction
from shared.db.qdrant import embed_texts, search_similar, rerank_documents
from shared.utils.nats_client import NATSPublisher
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
    """
    Constructs a structured, RAG-safe system prompt for the Actor LLM. Enforces strict roleplay immersion, formatting standards, and memory pacing."""
    lines = [
        "You are an expert AI roleplay actor. Your sole directive is to embody your character with emotional depth, consistency, and realistic pacing.",
        "Think, feel, and react exclusively as your character would in this moment. Adapt dynamically to the user while keeping the narrative immersive, interactive and believable.give an immersive, vivid roleplaying experience that feels natural and compelling.",
        "",
        "### WORLD CONTEXT",
        f"- Scenario: {scenario.get('title', 'Untitled')}",
        f"- Location: {current_place}",
        f"- Time: {current_time}",
    ]
    
    if scenario.get("introduction"):
        lines.append(f"- Premise: {scenario['introduction']}")
    # 1. AI CHARACTER PERSONA
    lines.extend([
        "",
        "### YOUR CHARACTER PERSONA",
        f"Name: {ai_char.get('name', 'Unknown')}",
    ])
    if ai_char.get("role_description"):
        lines.append(f"Role: {ai_char['role_description']}")
    if ai_char.get("personality"):
        lines.append(f"Personality & Traits: {ai_char['personality']}")
    if ai_char.get("backstory"):
        lines.append(f"Backstory: {ai_char['backstory']}")
    if ai_char.get("example_dialogue"):
        lines.append(f"Dialogue Tone/Style Example: {ai_char['example_dialogue']}")

    # 2. USER CHARACTER CONTEXT
    if user_char:
        lines.extend([
            "",
            "### THE USER'S CHARACTER (Your Co-Actor)",
            f"Name: {user_char.get('name', 'User')}",
        ])
        if user_char.get("role_description"):
            lines.append(f"Role: {user_char['role_description']}")
        if user_char.get("personality"):
            lines.append(f"Personality: {user_char['personality']}")
        if user_char.get("likes"):
            likes_data = user_char["likes"]
            likes_str = ", ".join(likes_data) if isinstance(likes_data, list) else str(likes_data)
            lines.append(f"Known Preferences/Likes: {likes_str}")
    # 3. RAG MEMORY GUARDRAILS (The Fix for Lore Dumping)
    if memories:
        lines.extend([
            "",
            "### PASSIVE BACKGROUND LORE & PAST MEMORIES",
            "CRITICAL INSTRUCTION: The following items are retrieved background context to help you understand the ongoing history. Treat them as PASSIVE KNOWLEDGE.",
            "- DO NOT recite, list, or dump these details into your dialogue.",
            "- DO NOT mention these memories unless the user explicitly brings them up, or they are directly triggered by the immediate action.",
            "- Let the narrative flow naturally without forcing past lore into the current moment."
        ])
        for m in memories:
            payload = m.get("payload", {})
            summary = payload.get("summary") or payload.get("content") or payload.get("description") or "Past event recorded."
            lines.append(f"  * {summary}")

    # 4. EXECUTION & FORMATTING RULES
    lines.extend([
        "",
        "### BEHAVIORAL & FORMATTING DIRECTIVES",
        "1. Stay '100%' in Character: Never break the fourth wall, never refer to yourself as an AI, and never mention system prompts or vector databases.",
        "2. Roleplay Formatting: ",
        "   - Use single asterisks for physical actions, gestures, sensory details, and internal thoughts.",
        "   - Write spoken dialogue in plain, regular text without asterisks.",
        "3. Pacing & Length Control:",
        "   - Keep your responses concise and impactful—typically 1 to 3 short paragraphs.",
        "   - NEVER monologue endlessly. Always leave room for the user to react.",
        "   - Ensure your response ends on a completed sentence or action. Never stop mid-thought.",
        "4. Agency: Play ONLY your character. Never describe the user's thoughts, feelings, or dialogue for them."
    ])
    
    return "\n".join(lines)


@traced('provider.actor')
async def _stream_llm(messages: List[dict]):
    """
    Executes a streaming inference call, yielding tokens one by one as they
    arrive from the LLM provider. Includes automated backoff handling for 429 errors.
    """
    from shared.utils.context import budget_messages
    messages = budget_messages(messages)
    payload = {
        "model": settings.llm_model,
        "messages": messages,
        "max_tokens": settings.llm_max_tokens,
        "temperature": settings.llm_temperature,
        "stream": True,  # Enable token streaming
    }
    
    max_retries = 4
    backoff_factor = 2.0
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {settings.llm_api_key}",
    }

    emitted = False
    for attempt in range(max_retries):
        try:
            async with admission(settings.llm_api_url, len(json.dumps(messages))+settings.llm_max_tokens) as client:
                async with client.stream("POST", settings.llm_api_url, headers=headers, json=payload) as resp:
                    
                    if resp.status_code == 429:
                        sleep_time = backoff_factor ** attempt
                        logger.warning("LLM Inference endpoint returned 429 Rate Limit. Retrying in %.1fs...", sleep_time)
                        await retry_delay(attempt, resp.headers.get("Retry-After"))
                        continue
                    
                    resp.raise_for_status()
                    
                    # Parse Server-Sent Events (SSE) data chunks
                    async for line in resp.aiter_lines():
                        if line.startswith("data: "):
                            data_str = line[6:].strip()
                            if data_str == "[DONE]":
                                break
                            try:
                                chunk_json = json.loads(data_str)
                                token = chunk_json["choices"][0]["delta"].get("content", "")
                                if token:
                                    emitted = True
                                    yield token
                            except (json.JSONDecodeError, KeyError, IndexError):
                                continue
                    return  # Successfully generated without errors, break retry loop

        except httpx.HTTPError as e:
            if emitted or attempt == max_retries - 1:
                logger.error("LLM execution ultimately failed after maximum retry attempts: %s", e)
                raise e
            await retry_delay(attempt)

    raise RuntimeError("Model provider rate limit retries exhausted")

class ActorAgent:
    def __init__(self):
        self.nats_publisher = NATSPublisher()

    async def run(self):
        """Bind consumer loops and listen for event distributions indefinitely via JetStream."""
        await self.nats_publisher.connect()
        assert self.nats_publisher.js is not None

        # Subscribe using a durable consumer profile via JetStream
        sub = await self.nats_publisher.js.pull_subscribe(
            "roleplay.events.jobs.actor",
            durable="actor_jobs_v3"
        )
        logger.info("Upgraded Actor Agent listening continuously on 'roleplay.chat.user_message'")

        from shared.utils.worker import consume
        await consume(self.nats_publisher, sub, self.handle_user_message)

    async def handle_user_message(self, data: dict):
        conversation_id = data.get("conversation_id")
        user_id = data.get("user_id")
        user_content = data.get("content", "")
        
        if not conversation_id:
            logger.error("Malformed NATS payload received; missing core identifier 'conversation_id'")
            return

        try:
            if data.get("event_id") and await fetch_one("SELECT id FROM messages WHERE event_id=%s", ("actor-" + data["event_id"],)):
                return
            # PIPELINE STATE 1: Broadcast 'processing_memory' state over Core NATS
            await self._send_ui_state(conversation_id, "processing_memory", "Querying vector profiles and cross-reranking records...")

            # Fetch foundational conversation state mapping
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

            # Execute concurrent tasks for character configuration profiles
            ai_char_task = fetch_one("SELECT * FROM characters WHERE id = %s", (conv["ai_character_id"],))
            user_char_task = (
                fetch_one("SELECT * FROM characters WHERE id = %s", (conv["user_character_id"],))
                if conv["user_character_id"] else asyncio.sleep(0, result=None)
            )
            
            ai_char, user_char = await asyncio.gather(ai_char_task, user_char_task)
            if not ai_char:
                logger.error("Base processing error: Target AI character data sheet is blank.")
                return

            # Retrieve conversational context history window
            recent_messages = await fetch_all(
                """SELECT sender, content FROM messages
                   WHERE conversation_id = %s AND COALESCE(metadata->>'action_status','accepted') NOT IN ('blocked','pending')
                   ORDER BY id DESC LIMIT 10
                """,
                (conversation_id,),
            )
            recent_messages.reverse()

            # Context Retrieval Pipeline (Vector Match -> Cross Encoder Rerank) using user input context
            search_text = user_content if user_content else (recent_messages[-1]["content"] if recent_messages else "")
            memories: List[dict] = []
            
            if search_text:
                try:
                    from shared.utils.retrieval import retrieve
                    memories = await retrieve(search_text,conversation_id,conv['scenario_id'],user_id)
                except Exception as e:
                    logger.warning("Context retrieval subsystem caught a non-breaking error: %s", e)

            # Build contextual system mapping framework
            system_prompt = _build_system_prompt(
                scenario=conv,
                ai_char=ai_char,
                user_char=user_char,
                current_place=conv["current_place"] or "Unknown",
                current_time=conv["current_time"] or "Unknown",
                memories=memories,
            )

            from shared.utils.game_engine import GameEngine
            state = await GameEngine(self.nats_publisher).get_state(conversation_id)
            system_prompt += '\nAuthoritative mechanical state: ' + json.dumps(state)
            for field in ('appearance', 'likes', 'dislikes', 'scenario'):
                if ai_char.get(field):
                    system_prompt += '\n' + field + ': ' + str(ai_char[field])
            messages = [{"role": "system", "content": system_prompt}]
            for m in recent_messages:
                role = "user" if m["sender"] == "user" else "assistant"
                messages.append({"role": role, "content": m["content"]})

            # A durable input ID fences context to the triggering turn.
            if data.get("message_id"):
                recent_messages = await fetch_all("SELECT sender, content FROM messages WHERE conversation_id=%s AND id<=%s AND COALESCE(metadata->>'action_status','accepted') NOT IN ('blocked','pending') ORDER BY id DESC LIMIT 10", (conversation_id, data["message_id"]))
                recent_messages.reverse()
                messages = [{"role": "system", "content": system_prompt}]
                messages.extend({"role": "user" if m["sender"] == "user" else "assistant", "content": m["content"]} for m in recent_messages)
            elif not recent_messages or recent_messages[-1]["content"] != user_content:
                messages.append({"role": "user", "content": user_content})

            # PIPELINE STATE 2: Broadcast 'typing' state to trigger immediate bubble UI animation
            await self._send_ui_state(conversation_id, "typing", f"{ai_char.get('name', 'AI')} is formulating an action...")

            # PIPELINE STATE 3: Stream individual text tokens in real time
            full_response_text = ""
            index = 0

            try:
                async for token in _stream_llm(messages):
                    full_response_text += token
                    await self._send_ui_chunk(conversation_id, token, index)
                    index += 1
            except Exception:
                await self._send_ui_state(conversation_id, 'retrying', 'Generation interrupted; retrying the current turn')
                raise
            if not full_response_text.strip():
                raise RuntimeError('Provider returned an empty reply')

            # PIPELINE STATE 4: Hand off final text payload out-of-band to Chronicler Agent
            # We don't perform SQL block inserts here. We broadcast the finished log event to NATS JetStream
            # and immediately return back to standby, keeping the worker unblocked.
            chronicler_payload = {
                "event_id": "actor-" + str(data.get("event_id") or uuid.uuid4()),
                "turn_id": data.get("turn_id"),
                "event": "ai_message_completed",
                "conversation_id": conversation_id,
                "user_id": user_id,
                "content": full_response_text,
                "metadata": {"actor_version": "2.5-streaming", "reranked": True},
                "timestamp": str(datetime.now(timezone.utc))
            }
            
            async with transaction():
                saved = await execute_returning("INSERT INTO messages(conversation_id,sender,content,metadata,event_id) VALUES (%s,%s,%s,%s,%s) ON CONFLICT(event_id) DO UPDATE SET event_id=EXCLUDED.event_id RETURNING id", (conversation_id, "ai", chronicler_payload["content"], json.dumps(chronicler_payload["metadata"]), chronicler_payload["event_id"]))
                chronicler_payload["message_id"] = saved["id"]
                await self.nats_publisher.publish("roleplay.chat.ai_reply_completed", json.dumps(chronicler_payload).encode())
                from shared.utils.turns import complete_job
                await complete_job(chronicler_payload)

            # Close transaction cycle on frontend side
            await self._send_ui_state(conversation_id, "completed", "Streaming cycle executed cleanly.")
            logger.info("Handed generation logs off to Chronicler for conversation_id=%s", conversation_id)

        except Exception as e:
            logger.error("Fatal failure running Actor Agent processing segment: %s", e)
            await self._send_ui_error(conversation_id, "Agent processing failed; please retry.")
            raise

    async def _send_ui_state(self, conversation_id: int, state: str, message: str):
        """Ships state updates over core ephemeral subjects directly to active connections."""
        packet = {
            "event": "state_change",
            "conversation_id": conversation_id,
            "timestamp": str(datetime.now(timezone.utc)),
            "payload": {
                "state": state,
                "message": message
            }
        }
        await self.nats_publisher.publish_ephemeral(
            f"roleplay.chat.stream.{conversation_id}", 
            json.dumps(packet).encode()
        )

    async def _send_ui_chunk(self, conversation_id: int, chunk: str, index: int):
        """Pipes raw character token modifications to the browser without JetStream latency."""
        packet = {
            "event": "text_chunk",
            "conversation_id": conversation_id,
            "timestamp": str(datetime.now(timezone.utc)),
            "payload": {
                "chunk": chunk,
                "index": index
            }
        }
        await self.nats_publisher.publish_ephemeral(
            f"roleplay.chat.stream.{conversation_id}", 
            json.dumps(packet).encode()
        )

    async def _send_ui_error(self, conversation_id: int, error_msg: str):
        """Alerts the active client UI interface of any system exceptions."""
        packet = {
            "event": "state_change",
            "conversation_id": conversation_id,
            "timestamp": str(datetime.now(timezone.utc)),
            "payload": {
                "state": "error",
                "error_detail": error_msg
            }
        }
        await self.nats_publisher.publish_ephemeral(
            f"roleplay.chat.stream.{conversation_id}", 
            json.dumps(packet).encode()
        )


if __name__ == "__main__":
    from shared.utils.worker import run_agent
    agent = ActorAgent()
    try:
        if sys.platform == "win32":
            def win_loop_factory():
                return asyncio.SelectorEventLoop(selectors.SelectSelector())
            asyncio.run(run_agent(agent), loop_factory=win_loop_factory)
        else:
            asyncio.run(run_agent(agent))
    except KeyboardInterrupt:
        logger.info("Agent shutting down cleanly via interface break request...")
