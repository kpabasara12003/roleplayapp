#roleplay_backend/app/services/ws_manager.py
import json
from typing import Dict, Set
from fastapi import WebSocket
from shared.utils.logger import get_logger

logger = get_logger(__name__)

class WebSocketConnectionManager:
    """Manages active stateful client sockets mapped by conversation IDs."""
    
    def __init__(self):
        # Maps conversation_id -> Set of active WebSocket connections
        self._active_connections: Dict[int, Set[WebSocket]] = {}

    async def connect(self, conversation_id: int, websocket: WebSocket):
        """Register an accepted connection into the live state matrix."""
        if conversation_id not in self._active_connections:
            self._active_connections[conversation_id] = set()
        self._active_connections[conversation_id].add(websocket)
        logger.info("Registered active WebSocket for conversation_id=%s (Total: %d)", 
                    conversation_id, len(self._active_connections[conversation_id]))

    async def disconnect(self, conversation_id: int, websocket: WebSocket):
        """Safely drop connection allocations on user exit."""
        if conversation_id in self._active_connections:
            self._active_connections[conversation_id].discard(websocket)
            if not self._active_connections[conversation_id]:
                del self._active_connections[conversation_id]
            logger.info("Unregistered WebSocket for conversation_id=%s", conversation_id)

    async def broadcast_to_conversation(self, conversation_id: int, message_dict: dict):
        """Fan out a dictionary message to all sockets listening to a conversation."""
        sockets = self._active_connections.get(conversation_id, set())
        if not sockets:
            return

        payload_bytes = json.dumps(message_dict, default=str)
        dead_sockets = set()

        for ws in sockets:
            try:
                await ws.send_text(payload_bytes)
            except Exception as e:
                logger.warning("Failed delivery to active socket in conversation %s: %s", conversation_id, e)
                dead_sockets.add(ws)

        # Cleanup ghost connections detected during broadcast
        for ws in dead_sockets:
            await self.disconnect(conversation_id, ws)

# Single global reference instance
ws_manager = WebSocketConnectionManager()