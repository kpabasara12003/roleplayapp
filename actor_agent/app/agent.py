import os
import sys
import json
import httpx
import asyncio
import selectors
from typing import Optional, List, Any
from datetime import datetime

from shared.db.postgres import fetch_one, fetch_all
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
    lines = [
        "You are a roleplay AI character, designed to engage in immersive and dynamic roleplaying experiences. Maintain your character's personality, beliefs, and emotions at all times, responding creatively to every situation.",
        "Think and behave as your character would in the given scenario, incorporating thoughts, feelings, and behaviors that align with your role. Stay in character consistently, and adapt your responses to keep the story engaging and believable for the user.",
        "Your goal is to create an immersive, vivid roleplaying experience that feels natural and compelling.",
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
        "- Respond ONLY as your character. be natural not robotic.",
        "- Do not break the fourth wall unless explicitly guided by the scenario constraints.",
        "- Keep responses natural and consistent with your personality, describe the environment and thoghts/feelings within **asterisks**.",
        "- Do not narrate actions in third person unless that's your character's explicit style.",
    ])
    return "\n".join(lines)


async def _stream_llm(messages: List[dict]):
    """
    Executes a streaming inference call, yielding tokens one by one as they
    arrive from the LLM provider. Includes automated backoff handling for 429 errors.
    """
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

    for attempt in range(max_retries):
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                async with client.stream("POST", settings.llm_api_url, headers=headers, json=payload) as resp:
                    
                    if resp.status_code == 429:
                        sleep_time = backoff_factor ** attempt
                        logger.warning("LLM Inference endpoint returned 429 Rate Limit. Retrying in %.1fs...", sleep_time)
                        await asyncio.sleep(sleep_time)
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
                                    yield token
                            except (json.JSONDecodeError, KeyError, IndexError):
                                continue
                    return  # Successfully generated without errors, break retry loop

        except httpx.HTTPError as e:
            if attempt == max_retries - 1:
                logger.error("LLM execution ultimately failed after maximum retry attempts: %s", e)
                raise e
            await asyncio.sleep(backoff_factor ** attempt)


class ActorAgent:
    def __init__(self):
        self.nats_publisher = NATSPublisher()

    async def run(self):
        """Bind consumer loops and listen for event distributions indefinitely via JetStream."""
        await self.nats_publisher.connect()
        assert self.nats_publisher.js is not None

        # Subscribe using a durable consumer profile via JetStream
        sub = await self.nats_publisher.js.subscribe(
            "roleplay.chat.user_message", 
            durable="actor_agent_stream_worker"
        )
        logger.info("Upgraded Actor Agent listening continuously on 'roleplay.chat.user_message'")

        while True:
            try:
                msg = await sub.next_msg(timeout=2.0)
                try:
                    data = json.loads(msg.data.decode()) if msg.data else {}
                    await self.handle_user_message(data)
                    await msg.ack()
                except Exception as e:
                    logger.error("Error processing event pipeline payload: %s", e)
                    await msg.nak()
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error("Actor lifecycle main loop error caught: %s", e)
                await asyncio.sleep(2)

    async def handle_user_message(self, data: dict):
        conversation_id = data.get("conversation_id")
        user_id = data.get("user_id")
        user_content = data.get("content", "")
        
        if not conversation_id:
            logger.error("Malformed NATS payload received; missing core identifier 'conversation_id'")
            return

        try:
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
                   WHERE conversation_id = %s
                   ORDER BY created_at DESC LIMIT 10
                """,
                (conversation_id,),
            )
            recent_messages.reverse()

            # Context Retrieval Pipeline (Vector Match -> Cross Encoder Rerank) using user input context
            search_text = user_content if user_content else (recent_messages[-1]["content"] if recent_messages else "")
            memories: List[dict] = []
            
            if search_text:
                try:
                    # 1. Base Vector Match over Qdrant index
                    emb = await embed_texts([search_text])
                    raw_vector_matches = await search_similar(
                        collection="conversations",
                        vector=emb[0],
                        limit=8,
                        filters={"conversation_id": conversation_id}
                    )
                    
                    # 2. Local Cross-Encoder Reranking filter pass
                    memories = rerank_documents(query=search_text, documents=raw_vector_matches, top_n=5)
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

            messages = [{"role": "system", "content": system_prompt}]
            for m in recent_messages:
                role = "user" if m["sender"] == "user" else "assistant"
                messages.append({"role": role, "content": m["content"]})

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
            except Exception as llm_err:
                logger.error("Inference pipeline stream dropped mid-generation: %s", llm_err)
                full_response_text = "*(The character looks down, temporarily lost in thought...)*"
                await self._send_ui_chunk(conversation_id, full_response_text, index)

            # PIPELINE STATE 4: Hand off final text payload out-of-band to Chronicler Agent
            # We don't perform SQL block inserts here. We broadcast the finished log event to NATS JetStream
            # and immediately return back to standby, keeping the worker unblocked.
            chronicler_payload = {
                "event": "ai_message_completed",
                "conversation_id": conversation_id,
                "user_id": user_id,
                "content": full_response_text,
                "metadata": {"actor_version": "2.5-streaming", "reranked": True},
                "timestamp": str(datetime.utcnow())
            }
            
            await self.nats_publisher.publish(
                "roleplay.chat.ai_reply_completed", 
                json.dumps(chronicler_payload).encode()
            )

            # Close transaction cycle on frontend side
            await self._send_ui_state(conversation_id, "completed", "Streaming cycle executed cleanly.")
            logger.info("Handed generation logs off to Chronicler for conversation_id=%s", conversation_id)

        except Exception as e:
            logger.error("Fatal failure running Actor Agent processing segment: %s", e)
            await self._send_ui_error(conversation_id, str(e))

    async def _send_ui_state(self, conversation_id: int, state: str, message: str):
        """Ships state updates over core ephemeral subjects directly to active connections."""
        packet = {
            "event": "state_change",
            "conversation_id": conversation_id,
            "timestamp": str(datetime.utcnow()),
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
            "timestamp": str(datetime.utcnow()),
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
            "timestamp": str(datetime.utcnow()),
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
    agent = ActorAgent()
    try:
        if sys.platform == "win32":
            def win_loop_factory():
                return asyncio.SelectorEventLoop(selectors.SelectSelector())
            asyncio.run(agent.run(), loop_factory=win_loop_factory)
        else:
            asyncio.run(agent.run())
    except KeyboardInterrupt:
        logger.info("Agent shutting down cleanly via interface break request...")