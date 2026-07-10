import os
import asyncio
from typing import Optional
from dotenv import load_dotenv

from nats.aio.client import Client as NATS
from nats.js.manager import JetStreamManager
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
    ("roleplay_memory", ["roleplay.memory.>"]),
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
        try:
            await js.add_stream(name=stream_name, subjects=subjects)
            logger.debug("JetStream stream '%s' ready", stream_name)
        except Exception as e:
            if "already exists" in str(e).lower() or "stream name already" in str(e).lower():
                pass # Stream is already configured
            else:
                logger.error("Error creating stream '%s': %s", stream_name, e)
                raise
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
        # Core NATS publish skips JetStream journals entirely
        await self.nc.publish(subject, payload) 
        logger.debug("Published ephemeral core msg to %s", subject)

    async def close(self):
        """Cleanly drain and close the NATS connection."""
        if self.nc and self.nc.is_connected:
            await self.nc.close()
            logger.info("NATS connection closed safely.")