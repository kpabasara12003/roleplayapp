#roleplay_agent/app/utils/nats_client.py
import os
import asyncio
import uuid
from contextlib import asynccontextmanager
from nats.js.api import ConsumerConfig
from nats.js.errors import NotFoundError
from typing import Optional
from dotenv import load_dotenv

from nats.aio.client import Client as NATS
from shared.utils.logger import get_logger

# Force load the .env file immediately before evaluating variables
load_dotenv()

logger = get_logger(__name__)

NATS_URL = os.getenv("NATS_URL", "nats://127.0.0.1:4222")
NATS_USER = os.getenv("NATS_USER") or None
NATS_PASSWORD = os.getenv("NATS_PASSWORD") or None

# JetStream streams are strictly for durable, guaranteed delivery (database syncs, vital state)
_JETSTREAM_STREAMS = [
    ("roleplay_events", ["roleplay.events.>"]),
    ("roleplay_chat", ["roleplay.chat.>"]),
]

async def get_nats_client() -> NATS:
    """Connect and return a NATS client with robust timeout handling."""
    
    logger.info("=========================================")
    logger.info(" NATS CONFIG DIAGNOSTIC:")
    logger.info(" Target URL:  %s", NATS_URL)
    logger.info(" Auth User:    %s", "Set" if NATS_USER else "None")
    logger.info("=========================================")

    if "your-nats-host" in NATS_URL:
        logger.error(" CRITICAL: The NATS_URL environment variable is still using the placeholder text!")
        raise ValueError("Invalid NATS_URL configuration.")

    nc = NATS()
    
    # Configure robust timeout parameters for remote/cloud brokers
    opts: dict = {
        "servers": [NATS_URL],
        "connect_timeout": 10.0,       # 10s for WAN stability
        "max_reconnect_attempts": 5,   # Prevents infinite flooding of the terminal
        "reconnect_time_wait": 2.0,    # Time to wait between retries
    }
    
    if NATS_USER and NATS_PASSWORD:
        opts["user"] = NATS_USER
        opts["password"] = NATS_PASSWORD

    try:
        await nc.connect(**opts)
        logger.info("Successfully connected to NATS at %s", NATS_URL)
        return nc
    except Exception as e:
        logger.error("Failed structural handshake to NATS server: %s", e)
        raise

async def get_jetstream(nc: Optional[NATS] = None):
    """Return JetStream context, initializing durable streams if needed."""
    if nc is None:
        nc = await get_nats_client()
    js = nc.jetstream()
    for stream_name, subjects in _JETSTREAM_STREAMS:
        max_age = float(os.getenv('NATS_RETENTION_SECONDS', '604800'))
        max_bytes = int(os.getenv('NATS_STREAM_MAX_BYTES', '536870912'))
        try:
            info = await js.stream_info(stream_name)
            config = info.config
            if config.max_age != max_age or config.max_bytes != max_bytes:
                config.max_age = max_age
                config.max_bytes = max_bytes
                await js.update_stream(config=config)
        except NotFoundError:
            await js.add_stream(name=stream_name, subjects=subjects, max_age=max_age, max_bytes=max_bytes)
    return js

class NATSPublisher:
    """Helper to publish messages to NATS/JetStream."""

    def __init__(self, nc: Optional[NATS] = None):
        self.nc = nc
        self.js = None

    async def connect(self):
        """Establish dual-connections for Core NATS and JetStream."""
        if self.nc is None or not self.nc.is_connected:
            self.nc = await get_nats_client()
        if self.js is None:
            self.js = await get_jetstream(self.nc)

    async def publish(self, subject: str, payload: bytes):
        """
        DURABLE PUBLISH: Uses JetStream. 
        Use this for final messages, database triggers, and critical events.
        """
        from shared.db.postgres import _transaction_conn, execute
        if _transaction_conn.get() is not None:
            await execute('INSERT INTO event_outbox(subject,payload) VALUES (%s,%s)', (subject,payload))
            return
        if self.js is None:
            await self.connect()
        assert self.js is not None
        await self.js.publish(subject, payload)
        logger.debug("Published durable JetStream msg to %s", subject)

    async def publish_ephemeral(self, subject: str, payload: bytes):
        """
        FAST PUBLISH: Uses Core NATS (Fire-and-forget).
        Use this for high-throughput UI updates like tokens and 'typing...' states.
        """
        if self.nc is None or not self.nc.is_connected:
            await self.connect()
        assert self.nc is not None
        import json
        from shared.utils.turns import job_claim
        claim = job_claim.get()
        if claim:
            from shared.db.postgres import fetch_one
            if not await fetch_one("SELECT id FROM jobs WHERE id=%s AND owner=%s AND fence=%s AND status='running' AND lease_until>clock_timestamp()",(claim.id,claim.owner,claim.fence)):
                return
            packet = json.loads(payload)
            packet.update(turn_id=claim.turn_id,generation_id=claim.id,attempt=claim.fence)
            payload = json.dumps(packet).encode()
        # Transient UI subjects are deliberately outside durable stream filters.
        subject = subject.replace('roleplay.chat.stream.', 'roleplay.live.stream.', 1)
        await self.nc.publish(subject, payload) 
        logger.debug("Published ephemeral core msg to %s", subject)

    async def close(self):
        """Cleanly drain and close the NATS connection."""
        if self.nc and self.nc.is_connected:
            await self.nc.drain()
            logger.info("NATS connection closed safely.")

    @asynccontextmanager
    async def processing(self, msg):
        import json
        async def heartbeat():
            while True:
                await asyncio.sleep(10)
                await msg.in_progress()
                data = json.loads(msg.data)
        task = asyncio.create_task(heartbeat())
        try:
            yield
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async def relay_outbox(self):
        from shared.db.postgres import transaction
        from psycopg.rows import dict_row
        while True:
            try:
                async with transaction() as conn:
                    async with conn.cursor(row_factory=dict_row) as cur:
                        await cur.execute('SELECT id,subject,payload FROM event_outbox ORDER BY id LIMIT 50 FOR UPDATE SKIP LOCKED')
                        for row in await cur.fetchall():
                            await self.js.publish(row['subject'], bytes(row['payload']), headers={'Nats-Msg-Id': 'outbox-' + str(row['id'])})
                            await cur.execute('DELETE FROM event_outbox WHERE id=%s',(row['id'],))
            except Exception:
                logger.exception('Outbox delivery failed; retrying')
            await asyncio.sleep(0.5)
