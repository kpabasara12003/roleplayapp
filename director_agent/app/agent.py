import json
import re
import asyncio
from typing import Optional

from nats.aio.client import Client as NATS

from shared.db.postgres import fetch_one, execute
from shared.utils.logger import get_logger
from director_agent.app.config import settings

logger = get_logger(__name__)

_PLACE_PATTERNS = [
    r"(?:go|move|walk|travel|head) (?:to|toward|in)?\s*(?:the\s+)?(.+?)(?:\.|,|!|;|\Z)",
    r"(?:arrive|enter)\s+(?:the\s+)?(.+?)(?:\.|,|!|;|\Z)",
]

_TIME_PATTERNS = [
    r"(?:now|it is|time is|current time)\s+(?:is\s+)?(.+?)(?:\.|,|!|;|\Z)",
    r"(?:morning|noon|afternoon|evening|night|midnight|dawn|dusk)",
]


def _extract_place(text: str) -> Optional[str]:
    for pat in _PLACE_PATTERNS:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            place = m.group(1).strip()
            if place and len(place) < 100:
                return place
    return None


def _extract_time(text: str) -> Optional[str]:
    for pat in _TIME_PATTERNS:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            time_val = m.group(1).strip() if m.lastindex else m.group(0).strip()
            if time_val and len(time_val) < 100:
                return time_val
    simple = re.search(r"\b(morning|noon|afternoon|evening|night|midnight|dawn|dusk)\b", text, re.IGNORECASE)
    if simple:
        return simple.group(1).capitalize()
    return None


class DirectorAgent:
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

    async def handle_ai_response(self, data: dict):
        conversation_id = data.get("conversation_id")
        message_id = data.get("message_id")
        if not conversation_id or not message_id:
            return

        msg = await fetch_one(
            "SELECT content FROM messages WHERE id = %s AND conversation_id = %s",
            (message_id, conversation_id),
        )
        if not msg:
            return
        text = msg["content"]

        new_place = _extract_place(text)
        new_time = _extract_time(text)

        if new_place or new_time:
            updates = []
            params = []
            if new_place:
                updates.append("current_place = %s")
                params.append(new_place)
                logger.info("Director updated place for conv=%s -> %s", conversation_id, new_place)
            if new_time:
                updates.append('"current_time" = %s')
                params.append(new_time)
                logger.info("Director updated time for conv=%s -> %s", conversation_id, new_time)

            params.append(conversation_id)
            sql = f"UPDATE conversations SET {', '.join(updates)} WHERE id = %s"
            await execute(sql, tuple(params))

    async def run(self):
        await self.connect()
        sub = await self.js.subscribe("roleplay.chat.ai_response", durable="director_agent")
        logger.info("Director Agent listening on roleplay.chat.ai_response")

        async def process(msg):
            try:
                data = json.loads(msg.data.decode()) if msg.data else {}
                await self.handle_ai_response(data)
                await msg.ack()
            except Exception as e:
                logger.error("Director error: %s", e)
                await msg.nak()

        while True:
            try:
                msg = await sub.next_msg(timeout=2.0)
                await process(msg)
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error("Director loop error: %s", e)
                await asyncio.sleep(1)


if __name__ == "__main__":
    import sys
    # FIXED: Force Windows to use SelectorEventLoop for psycopg compatibility
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    agent = DirectorAgent()
    try:
        asyncio.run(agent.run())
    except KeyboardInterrupt:
        logger.info("Director Agent shutting down cleanly...")