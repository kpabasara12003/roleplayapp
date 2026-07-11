#roleplay_backend/app/api/chat.py
import json
from typing import Optional, List
import asyncio
from datetime import datetime

from fastapi import APIRouter, HTTPException, Depends, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from shared.db.postgres import fetch_one, fetch_all, execute_returning
from shared.utils.nats_client import NATSPublisher
from shared.schemas.protocol import OutboundWSEvent
from fastapi_server.app.services.ws_manager import ws_manager
from fastapi_server.app.api.users import get_current_user
from shared.utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/chat", tags=["Chat"])

nats_publisher = NATSPublisher()

class ChatStartRequest(BaseModel):
    scenario_id: int
    ai_character_id: int
    user_character_id: Optional[int] = None

class ChatMessageRequest(BaseModel):
    conversation_id: int
    content: str

class ChatMessageResponse(BaseModel):
    id: int
    conversation_id: int
    sender: str
    content: str
    created_at: datetime


# Real-time NATS to WebSocket Bridge Worker
async def nats_to_websocket_bridge():
    """Background loop that listens to NATS channels and routes to the live WebSocket Manager."""
    await nats_publisher.connect()
    
    # Safely extract the raw core NATS client instance from your custom wrapper
    nc = getattr(nats_publisher, "nc", None) or getattr(nats_publisher, "_nc", None) or getattr(nats_publisher, "client", None)
    
    if not nc:
        logger.error("Bridge Failure: Could not locate the raw NATS client inside NATSPublisher.")
        return

    async def message_handler(msg):
        try:
            subject = msg.subject
            data = json.loads(msg.data.decode()) if msg.data else {}
            
            # Extract the active conversation_id from the end of the routing subject string
            # e.g., "roleplay.chat.stream.3" -> 3
            parts = subject.split(".")
            conversation_id = int(parts[-1])
            
            # Route directly to our stateful memory connection registry
            await ws_manager.broadcast_to_conversation(conversation_id, data)
            logger.debug("Successfully fanned out event from subject %s to WebSocket", subject)
            
        except Exception as e:
            logger.error("Failed to parse or route background NATS packet to WebSocket: %s", e)

    # Listen directly to final AI outputs from Chronicler and context updates from Director
    await nc.subscribe("roleplay.chat.stream.>", cb=message_handler)
    await nc.subscribe("roleplay.events.updates.>", cb=message_handler)
    logger.info("Real-time NATS-to-WebSocket messaging bridge connected and sniffing targets.")


@router.on_event("startup")
async def launch_background_bridge():
    """Asynchronously starts our event router alongside the core FastAPI application worker."""
    asyncio.create_task(nats_to_websocket_bridge())


@router.post("/start", response_model=dict)
async def start_conversation(
    payload: ChatStartRequest,
    user: dict = Depends(get_current_user),
):
    """Create a new conversation for a scenario."""
    scenario = await fetch_one(
        "SELECT id, place, time FROM scenarios WHERE id = %s AND user_id = %s",
        (payload.scenario_id, user["id"]),
    )
    if not scenario:
        raise HTTPException(status_code=404, detail="Scenario not found")

    ai_char = await fetch_one(
        "SELECT id FROM characters WHERE id = %s AND scenario_id = %s AND is_ai = true",
        (payload.ai_character_id, payload.scenario_id),
    )
    if not ai_char:
        raise HTTPException(status_code=404, detail="AI character not found in scenario")

    if payload.user_character_id:
        uc = await fetch_one(
            "SELECT id FROM characters WHERE id = %s AND scenario_id = %s AND is_ai = false",
            (payload.user_character_id, payload.scenario_id),
        )
        if not uc:
            raise HTTPException(status_code=404, detail="User character not found in scenario")

    conv = await execute_returning(
        """
        INSERT INTO conversations (scenario_id, user_id, ai_character_id, user_character_id, current_place, "current_time", status)
        VALUES (%s, %s, %s, %s, %s, %s, 'active')
        RETURNING id, scenario_id, user_id, ai_character_id, user_character_id, current_place, "current_time", status, created_at, updated_at
        """,
        (
            payload.scenario_id,
            user["id"],
            payload.ai_character_id,
            payload.user_character_id,
            scenario["place"] or "Unknown",
            scenario["time"] or "Unknown",
        ),
    )

    # Publish durable transaction message
    payload_json = json.dumps({
        "event": "conversation_started",
        "conversation_id": conv["id"],
        "user_id": user["id"],
    })
    await nats_publisher.publish("roleplay.events.conversation_started", payload_json.encode())

    ai_char_data = await fetch_one("SELECT greeting FROM characters WHERE id = %s", (payload.ai_character_id,))
    greeting = ai_char_data.get("greeting") if ai_char_data else None
    if greeting:
        await execute_returning(
            """
            INSERT INTO messages (conversation_id, sender, content, metadata)
            VALUES (%s, 'ai', %s, %s)
            RETURNING id
            """,
            (conv["id"], greeting, json.dumps({"type": "greeting"})),
        )

    return conv


@router.post("/send", response_model=ChatMessageResponse)
async def send_message(
    payload: ChatMessageRequest,
    user: dict = Depends(get_current_user),
):
    """Fallback HTTP Message gateway routing straight into NATS processing."""
    conv = await fetch_one(
        "SELECT id FROM conversations WHERE id = %s AND user_id = %s AND status = 'active'",
        (payload.conversation_id, user["id"]),
    )
    if not conv:
        raise HTTPException(status_code=404, detail="Active conversation not found")

    msg = await execute_returning(
        """
        INSERT INTO messages (conversation_id, sender, content, metadata)
        VALUES (%s, 'user', %s, %s)
        RETURNING id, conversation_id, sender, content, created_at
        """,
        (payload.conversation_id, payload.content, json.dumps({"source": "api"})),
    )

    event = {
        "event": "user_message",
        "conversation_id": conv["id"],
        "message_id": msg["id"],
        "user_id": user["id"],
        "content": payload.content
    }
    await nats_publisher.publish("roleplay.chat.user_message", json.dumps(event).encode())
    return msg


@router.get("/history/{conversation_id}", response_model=List[ChatMessageResponse])
async def get_history(conversation_id: int, user: dict = Depends(get_current_user)):
    return await fetch_all(
        """SELECT id, conversation_id, sender, content, created_at
           FROM messages WHERE conversation_id = %s ORDER BY created_at ASC""",
        (conversation_id,),
    )


@router.websocket("/ws/{conversation_id}")
async def websocket_chat(websocket: WebSocket, conversation_id: int):
    """Pure, decoupled real-time gateway pipeline channel."""
    api_key = websocket.query_params.get("api_key")
    if not api_key:
        await websocket.close(code=1008, reason="Missing api_key")
        return

    user = await fetch_one("SELECT id FROM users WHERE api_key = %s", (api_key,))
    if not user:
        await websocket.close(code=1008, reason="Invalid api_key")
        return

    conv = await fetch_one(
        "SELECT id FROM conversations WHERE id = %s AND user_id = %s AND status = 'active'",
        (conversation_id, user["id"]),
    )
    if not conv:
        await websocket.close(code=1008, reason="Active conversation access denied")
        return

    # Accept connection and transfer state registration to the live registry manager
    await websocket.accept()
    await ws_manager.connect(conversation_id, websocket)

    try:
        while True:
            raw_data = await websocket.receive_text()
            try:
                packet = json.loads(raw_data)
                content = packet.get("content", "").strip()
            except Exception:
                await websocket.send_text(json.dumps({"error": "Invalid JSON mapping structure"}))
                continue

            if not content:
                continue

            # CRITICAL OPTIMIZATION: Emit a fire-and-forget message straight to NATS.
            # We don't perform SQL block updates here. The Chronicler Agent handles database
            # ingest, allowing the thread to instantly listen for more user actions.
            event = {
                "event": "user_message",
                "conversation_id": conversation_id,
                "user_id": user["id"],
                "content": content,
                "timestamp": str(datetime.utcnow())
            }
            
            # Broadcast user message through fast ephemeral channels
            await nats_publisher.publish_ephemeral(
                "roleplay.chat.user_message", 
                json.dumps(event).encode()
            )

    except WebSocketDisconnect:
        logger.info("Connection tunnel dropped cleanly for conversation %s", conversation_id)
    finally:
        await ws_manager.disconnect(conversation_id, websocket)