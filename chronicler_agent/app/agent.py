import os
import sys
import json
import asyncio
import selectors
from collections import defaultdict
from typing import Dict
from datetime import datetime, timezone  # FIX: Explicitly import timezone to prevent class attribute errors

from shared.utils.nats_client import NATSPublisher
from qdrant_client.models import PointStruct

from shared.db.postgres import fetch_one, fetch_all, execute_returning
from shared.db.qdrant import embed_texts, upsert_points
from shared.utils.logger import get_logger
from chronicler_agent.app.config import settings

logger = get_logger(__name__)

# Track historical message metrics locally to isolate memory indexing operations
_message_counts: Dict[int, int] = defaultdict(int)

class ChroniclerAgent:
    def __init__(self):
        self.nats_publisher = NATSPublisher()

    async def _get_message_count(self, conversation_id: int) -> int:
        row = await fetch_one(
            "SELECT COUNT(*) as cnt FROM messages WHERE conversation_id = %s",
            (conversation_id,),
        )
        return row["cnt"] if row else 0

    async def _summarize_range(self, conversation_id: int, start_id: int, end_id: int) -> str:
        rows = await fetch_all(
            """
            SELECT sender, content FROM messages
            WHERE conversation_id = %s AND id >= %s AND id <= %s
            ORDER BY created_at ASC
            """,
            (conversation_id, start_id, end_id),
        )
        parts = []
        for r in rows:
            prefix = "User" if r["sender"] == "user" else "AI"
            parts.append(f"{prefix}: {r['content']}")
        summary = " | ".join(parts)
        return summary[:1500]

    async def handle_message(self, data: dict, subject: str):
        """Processes transactional storage entries and synchronizes client caches."""
        event = data.get("event")
        conversation_id = data.get("conversation_id")
        user_id = data.get("user_id")
        content = data.get("content", "").strip()

        if not conversation_id:
            logger.warning("Dropped an un-routable pipeline log frame due to missing conversation identifiers.")
            return

        message_saved = False
        inserted_msg_id = None
        sender_type = None

        # -----------------------------------------------------------------
        # CASE 1: Inbound User Message Handling
        # -----------------------------------------------------------------
        if event == "user_message" or "user_message" in subject:
            sender_type = "user"
            if "message_id" not in data:
                logger.info("Offloading WebSocket user string commit for conversation_id=%s", conversation_id)
                msg = await execute_returning(
                    """
                    INSERT INTO messages (conversation_id, sender, content, metadata)
                    VALUES (%s, 'user', %s, %s)
                    RETURNING id
                    """,
                    (conversation_id, content, json.dumps({"source": "ws"})),
                )
                if msg:
                    inserted_msg_id = msg["id"]
                    message_saved = True
            else:
                inserted_msg_id = data["message_id"]
                message_saved = True

        # -----------------------------------------------------------------
        # CASE 2: Finished AI Generation Handling
        # -----------------------------------------------------------------
        elif event == "ai_message_completed" or "ai_reply_completed" in subject:
            sender_type = "ai"
            logger.info("Persisting completely formulated AI generation block for conversation_id=%s", conversation_id)
            metadata = data.get("metadata", {"actor_version": "2.5-streaming", "reranked": True})
            
            msg = await execute_returning(
                """
                INSERT INTO messages (conversation_id, sender, content, metadata)
                VALUES (%s, 'ai', %s, %s)
                RETURNING id
                """,
                (conversation_id, content, json.dumps(metadata)),
            )
            if msg:
                inserted_msg_id = msg["id"]
                message_saved = True

        # -----------------------------------------------------------------
        # POST-WRITE: Interface Synchronization & Summarization Evaluate
        # -----------------------------------------------------------------
        if message_saved and inserted_msg_id:
            
            # Trigger Director Agent for AI Replies
            if sender_type == "ai":
                director_packet = {
                    "conversation_id": conversation_id,
                    "message_id": inserted_msg_id
                }
                director_subject = f"roleplay.chat.ai_response.{conversation_id}"
                
                await self.nats_publisher.publish_ephemeral(
                    director_subject,
                    json.dumps(director_packet).encode()
                )
                logger.info("Chronicler forwarded context token validation to Director on subject=%s", director_subject)

            # Send database index resolution back to the user via the fast ephemeral channel
            await self._send_ui_confirmation(conversation_id, inserted_msg_id, sender_type, content)
            
            # Evaluate if the active message history requires long-term compression/upsert
            await self._check_and_trigger_summarization(conversation_id)

    async def _send_ui_confirmation(self, conversation_id: int, message_id: int, sender: str, content: str):
        """Notifies frontend sockets that raw stream contents are safely hard-indexed."""
        packet = {
            "event": "message_completed",
            "conversation_id": conversation_id,
            "timestamp": str(datetime.now(timezone.utc)),  # FIX: Uses backward-compatible, warning-free UTC format
            "payload": {
                "message_id": message_id,
                "sender": sender,
                "full_content": content
            }
        }
        await self.nats_publisher.publish_ephemeral(
            f"roleplay.chat.stream.{conversation_id}", 
            json.dumps(packet).encode()
        )

    async def _check_and_trigger_summarization(self, conversation_id: int):
        """Analyzes moving session counts to compute context summaries and populate Qdrant layers."""
        total = await self._get_message_count(conversation_id)
        last_processed = _message_counts[conversation_id]
        
        if last_processed == 0 and total > 0:
            _message_counts[conversation_id] = total
            last_processed = total

        delta = total - last_processed
        if delta < settings.summarize_every_n:
            return

        logger.info("Memory summarization criteria met (delta=%d) for conversation_id=%s", delta, conversation_id)
        rows = await fetch_all(
            """
            SELECT id FROM messages
            WHERE conversation_id = %s
            ORDER BY created_at DESC LIMIT %s
            """,
            (conversation_id, settings.summarize_every_n),
        )
        if not rows:
            return
            
        ids = [r["id"] for r in rows]
        start_id = min(ids)
        end_id = max(ids)

        summary_text = await self._summarize_range(conversation_id, start_id, end_id)

        try:
            vectors = await embed_texts([summary_text])
            
            point = PointStruct(
                id=f"{conversation_id}_{start_id}_{end_id}",
                vector=vectors[0],
                payload={
                    "conversation_id": conversation_id,
                    "summary": summary_text,
                    "start_id": start_id,
                    "end_id": end_id,
                },
            )
            await upsert_points("conversations", [point])

            conv = await fetch_one(
                "SELECT scenario_id FROM conversations WHERE id = %s", (conversation_id,)
            )
            if conv:
                lore_point = PointStruct(
                    id=f"lore_{conversation_id}_{start_id}_{end_id}",
                    vector=vectors[0],
                    payload={
                        "scenario_id": conv["scenario_id"],
                        "description": summary_text,
                        "category": "conversation_summary",
                    },
                )
                await upsert_points("lorebook", [lore_point])
                
            _message_counts[conversation_id] = total
            logger.info("Successfully vectorized and synced long-term memories for conv=%s", conversation_id)
            
        except Exception as e:
            logger.error("Failed to execute context embedding summaries or vector cluster sync: %s", e)

    async def run(self):
        """Bind consumer lines and parse all internal workspace event states."""
        await self.nats_publisher.connect()
        assert self.nats_publisher.js is not None

        sub = await self.nats_publisher.js.subscribe(
            "roleplay.chat.>", 
            durable="chronicler_agent_durable"
        )
        logger.info("Upgraded Chronicler Agent successfully listening to 'roleplay.chat.>'")

        while True:
            try:
                msg = await sub.next_msg(timeout=2.0)
                try:
                    data = json.loads(msg.data.decode()) if msg.data else {}
                    await self.handle_message(data, msg.subject)
                    await msg.ack()
                except Exception as e:
                    logger.error("Error processing stream message within Chronicler pipeline: %s", e)
                    await msg.nak()
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error("Chronicler lifecycle main loop error caught: %s", e)
                await asyncio.sleep(1)


if __name__ == "__main__":
    agent = ChroniclerAgent()
    try:
        if sys.platform == "win32":
            def win_loop_factory():
                return asyncio.SelectorEventLoop(selectors.SelectSelector())
            asyncio.run(agent.run(), loop_factory=win_loop_factory)
        else:
            asyncio.run(agent.run())
    except KeyboardInterrupt:
        logger.info("Chronicler Agent shutting down safely via terminal termination request...")