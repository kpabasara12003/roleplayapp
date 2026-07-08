import json
from typing import Optional, List
from datetime import datetime

from fastapi import APIRouter, HTTPException, Depends, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from shared.db.postgres import fetch_one, fetch_all, execute_returning
from shared.db.qdrant import embed_texts, search_similar
from shared.utils.nats_client import NATSPublisher
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
        INSERT INTO conversations (scenario_id, user_id, ai_character_id, user_character_id, current_place, current_time, status)
        VALUES (%s, %s, %s, %s, %s, %s, 'active')
        RETURNING id, scenario_id, user_id, ai_character_id, user_character_id, current_place, current_time, status, created_at, updated_at
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

    # Publish event to chronicler
    payload_json = json.dumps({
        "event": "conversation_started",
        "conversation_id": conv["id"],
        "user_id": user["id"],
    })
    await nats_publisher.publish("roleplay.events.conversation_started", payload_json.encode())

    # If AI has a greeting, insert it as first message
    ai_char_data = await fetch_one(
        "SELECT greeting FROM characters WHERE id = %s",
        (payload.ai_character_id,),
    )
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
    """Send a user message and trigger the Actor agent via NATS."""
    conv = await fetch_one(
        """
        SELECT c.* FROM conversations c
        WHERE c.id = %s AND c.user_id = %s AND c.status = 'active'
        """,
        (payload.conversation_id, user["id"]),
    )
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found or inactive")

    msg = await execute_returning(
        """
        INSERT INTO messages (conversation_id, sender, content, metadata)
        VALUES (%s, 'user', %s, %s)
        RETURNING id, conversation_id, sender, content, created_at
        """,
        (payload.conversation_id, payload.content, json.dumps({"source": "api"})),
    )

    # Notify Actor agent via NATS
    event = {
        "event": "user_message",
        "conversation_id": conv["id"],
        "message_id": msg["id"],
        "user_id": user["id"],
    }
    await nats_publisher.publish("roleplay.chat.user_message", json.dumps(event).encode())

    return msg


@router.get("/history/{conversation_id}", response_model=List[ChatMessageResponse])
async def get_history(
    conversation_id: int,
    user: dict = Depends(get_current_user),
):
    rows = await fetch_all(
        """
        SELECT id, conversation_id, sender, content, created_at
        FROM messages
        WHERE conversation_id = %s
        ORDER BY created_at ASC
        """,
        (conversation_id,),
    )
    return rows


@router.websocket("/ws/{conversation_id}")
async def websocket_chat(websocket: WebSocket, conversation_id: int):
    """WebSocket for real-time messaging."""
    api_key = websocket.query_params.get("api_key")
    if not api_key:
        await websocket.close(code=1008, reason="Missing api_key")
        return

    user = await fetch_one(
        "SELECT id, username FROM users WHERE api_key = %s",
        (api_key,),
    )
    if not user:
        await websocket.close(code=1008, reason="Invalid api_key")
        return

    conv = await fetch_one(
        "SELECT id FROM conversations WHERE id = %s AND user_id = %s",
        (conversation_id, user["id"]),
    )
    if not conv:
        await websocket.close(code=1008, reason="Conversation not found")
        return

    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_text()
            try:
                req = json.loads(data)
            except json.JSONDecodeError:
                await websocket.send_text(json.dumps({"error": "Invalid JSON"}))
                continue

            content = req.get("content", "").strip()
            if not content:
                await websocket.send_text(json.dumps({"error": "Empty content"}))
                continue

            msg = await execute_returning(
                """
                INSERT INTO messages (conversation_id, sender, content, metadata)
                VALUES (%s, 'user', %s, %s)
                RETURNING id, conversation_id, sender, content, created_at
                """,
                (conversation_id, content, json.dumps({"source": "websocket"})),
            )

            # Publish to actor
            event = {
                "event": "user_message",
                "conversation_id": conversation_id,
                "message_id": msg["id"],
                "user_id": user["id"],
            }
            await nats_publisher.publish(
                "roleplay.chat.user_message", json.dumps(event).encode()
            )

            # Simple immediate response placeholder; in production, actor publishes back
            await websocket.send_text(json.dumps({"status": "sent", "message_id": msg["id"]}))

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected for conv=%s", conversation_id)
