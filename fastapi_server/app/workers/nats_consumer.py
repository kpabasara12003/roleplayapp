import json
import asyncio
from nats.aio.client import Client as NATS
from fastapi_server.app.services.ws_manager import ws_manager
from shared.utils.logger import get_logger
from typing import Optional

logger = get_logger(__name__)

class NATSConsumerWorker:
    """Background loop worker matching NATS topic events to browser WebSockets."""
    
    def __init__(self):
        self._main_task: Optional[asyncio.Task] = None
        self._sub = None

    async def start(self, nc: NATS):
        """Initialize consumer loop against core NATS connection topology."""
        self._main_task = asyncio.create_task(self._consume_loop(nc))
        logger.info("NATS UI Stream Routing Consumer launched successfully.")

    async def _consume_loop(self, nc: NATS):
        """Listens natively to ephemeral token streams and lifecycle updates."""
        try:
            # Subscribe to all live text streams via wildcard token matching
            self._sub = await nc.subscribe("roleplay.chat.stream.>*")
            logger.info("Subscribed to core streaming subject: roleplay.chat.stream.>")

            while True:
                try:
                    msg = await self._sub.next_msg(timeout=1.0)
                    subject_parts = msg.subject.split(".")
                    
                    # Expected format: roleplay.chat.stream.{conversation_id}
                    if len(subject_parts) < 4:
                        continue
                        
                    conversation_id = int(subject_parts[3])
                    payload_data = json.loads(msg.data.decode())

                    # Stream data straight through memory manager to the matching socket
                    await ws_manager.broadcast_to_conversation(conversation_id, payload_data)
                    
                except asyncio.TimeoutError:
                    continue
                except Exception as e:
                    logger.error("Exception handling packet entry inside NATS pipeline: %s", e)
                    await asyncio.sleep(1)
        except asyncio.CancelledError:
            logger.info("NATS stream consumer loop received shutdown command.")
        except Exception as e:
            logger.critical("Fatal crash on NATS event stream listener block: %s", e)

    async def stop(self):
        """Cleanly close and unsubscribe the NATS worker."""
        if self._sub:
            await self._sub.unsubscribe()
        if self._main_task:
            self._main_task.cancel()
            await asyncio.gather(self._main_task, return_exceptions=True)
        logger.info("NATS UI Stream Consumer worker completely stopped.")

# Single global reference worker
nats_consumer_worker = NATSConsumerWorker()