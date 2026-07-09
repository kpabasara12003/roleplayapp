import json
import asyncio
from collections import defaultdict
from typing import Dict

from nats.aio.client import Client as NATS
from qdrant_client.models import PointStruct

from shared.db.postgres import fetch_one, fetch_all
from shared.db.qdrant import embed_texts, upsert_points
from shared.utils.logger import get_logger
from chronicler_agent.app.config import settings

logger = get_logger(__name__)

_message_counts: Dict[int, int] = defaultdict(int)


class ChroniclerAgent:
    def __init__(self):
        self.nc = None
        self.js = None

    async def connect(self):
        self.nc = NATS()
        opts: dict = {
            "servers": [settings.nats_url],
            "connect_timeout": 10.0,
            "max_reconnect_attempts": 5,
            "reconnect_time_wait": 2.0,
        }
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

    async def handle_message(self, data: dict):
        conversation_id = data.get("conversation_id")
        if not conversation_id:
            return

        total = await self._get_message_count(conversation_id)
        last_processed = _message_counts.get(conversation_id, 0)
        delta = total - last_processed

        if delta < settings.summarize_every_n:
            logger.debug("Not enough new messages (delta=%d) for conv=%s", delta, conversation_id)
            return

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
        logger.info("Summarized conv=%s messages %s-%s", conversation_id, start_id, end_id)

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
            logger.info("Stored memory for conv=%s", conversation_id)

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
        except Exception as e:
            logger.error("Failed to embed/store memory: %s", e)
            return

    async def run(self):
        await self.connect()
        sub = await self.js.subscribe("roleplay.chat.user_message", durable="chronicler_agent")
        logger.info("Chronicler Agent listening on roleplay.chat.user_message")

        async def process(msg):
            try:
                data = json.loads(msg.data.decode()) if msg.data else {}
                await self.handle_message(data)
                await msg.ack()
            except Exception as e:
                logger.error("Chronicler error: %s", e)
                await msg.nak()

        while True:
            try:
                msg = await sub.next_msg(timeout=2.0)
                await process(msg)
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error("Chronicler loop error: %s", e)
                await asyncio.sleep(1)


if __name__ == "__main__":
    agent = ChroniclerAgent()
    try:
        asyncio.run(agent.run())
    except KeyboardInterrupt:
        logger.info("Chronicler Agent shutting down cleanly...")