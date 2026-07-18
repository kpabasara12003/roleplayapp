#roleplay_backend/app/api/chat.py
import json
from typing import Optional, List
import asyncio
from datetime import datetime
from shared.schemas.engine import DirectorEvaluation
from fastapi import APIRouter, HTTPException, Depends, WebSocket, WebSocketDisconnect, Query
from pydantic import BaseModel
from nats.js.api import ConsumerConfig, DeliverPolicy
from shared.utils.game_engine import GameEngine 
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
    """Background loop for real-time un-journaled states like Director updates."""
    await nats_publisher.connect()
    nc = getattr(nats_publisher, "nc", None) or getattr(nats_publisher, "_nc", None)
    if not nc:
        return

    async def message_handler(msg):
        try:
            subject = msg.subject
            data = json.loads(msg.data.decode()) if msg.data else {}
            conversation_id = int(subject.split(".")[-1])
            
            # Fan out ephemeral updates (like time/place mutations from the Director)
            await ws_manager.broadcast_to_conversation(conversation_id, data)
        except Exception as e:
            logger.error("Failed to route background message: %s", e)

    # We ONLY listen to events/updates here. Chat stream updates are handled inside the WS loop.
    await nc.subscribe("roleplay.events.updates.>", cb=message_handler)
    logger.info("Real-time Ephemeral Update Bridge connected.")


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
async def websocket_chat(
    websocket: WebSocket, 
    conversation_id: int,
    last_seen_seq: Optional[int] = Query(None)  # Client supplies this parameter on reconnection
):
    """Decoupled real-time gateway pipeline channel with JetStream stream tracking."""
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

    await websocket.accept()
    await ws_manager.connect(conversation_id, websocket)

    # Connect to the local client's JetStream manager layer
    await nats_publisher.connect()
    js = nats_publisher.js
    game_engine = GameEngine(nats_publisher=nats_publisher)

    # 1. Evaluate user delivery alignment instructions
    if last_seen_seq is not None and last_seen_seq > 0:
        config = ConsumerConfig(
            deliver_policy=DeliverPolicy.BY_START_SEQUENCE,
            opt_start_seq=last_seen_seq + 1,  # Playback starting at the first missed packet
            inactive_threshold=300.0          # Clear memory allocation if gone for 5 mins
        )
        logger.info("Configured catch-up playback consumer for conv=%s from sequence=%s", conversation_id, last_seen_seq + 1)
    else:
        config = ConsumerConfig(
            deliver_policy=DeliverPolicy.NEW,  # Fresh connection, only push incoming text going forward
            inactive_threshold=300.0
        )
        logger.info("Configured brand-new live session consumer for conv=%s", conversation_id)

    # 2. Subscribe directly to JetStream messages for this distinct conversation channel
    chat_subject = f"roleplay.chat.stream.{conversation_id}"
    nats_sub = await js.subscribe(subject=chat_subject, config=config)

    # 3. Asynchronous loop to pull from NATS JetStream and forward straight out the WebSocket
    async def stream_nats_to_client():
        try:
            async for msg in nats_sub.messages:
                stream_seq = msg.metadata.sequence.stream
                raw_payload = json.loads(msg.data.decode()) if msg.data else {}
                
                # Combine original payload with the critical sequence tracker id
                wrapped_response = {
                    "stream_sequence_id": stream_seq,
                    "event_body": raw_payload
                }
                
                await websocket.send_text(json.dumps(wrapped_response))
                await msg.ack()  # Tell NATS server this message successfully hit the user browser
        except Exception as e:
            logger.debug("Local socket listener teardown finished safely: %s", e)

    nats_task = asyncio.create_task(stream_nats_to_client())

    # 4. Handle inbound user text messages from the client
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

            # ENGINE INTERCEPTION STEP (The Director's Gate via NATS RPC)
            try:
                # A. Retrieve current status metrics from local engine
                current_game_state = await game_engine.get_state(conversation_id)

                # B. Pack up the request context for the standalone Director Microservice
                rpc_payload = {
                    "conversation_id": conversation_id,
                    "user_id": user["id"],
                    "content": content,
                    "game_state": current_game_state
                }

                logger.info("Requesting pre-flight action validation from Director microservice...")
                
                # C. Make a blocking request over NATS (timeout after 4 seconds)
                nc = nats_publisher.nc  # Access raw NATS connection client
                rpc_response = await nc.request(
                    "roleplay.director.validate_action",
                    json.dumps(rpc_payload).encode(),
                    timeout=4.0
                )

                raw_eval_dict = json.loads(rpc_response.data.decode())
                raw_eval_dict.setdefault("reasoning", "No explicit reasoning provided by director.")
                # D. Check if action breaks game logic using safe dict `.get()`
                if not raw_eval_dict.get("is_action_allowed", True):
                    blocked_response = {
                        "stream_sequence_id": None,
                        "event_body": {
                            "event": "action_blocked",
                            "conversation_id": conversation_id,
                            "payload": {
                                "reason": raw_eval_dict.get("failure_explanation", "Action rejected by the director.")
                            }
                        }
                    }
                    await websocket.send_text(json.dumps(blocked_response))
                    continue  # Abort here — do not forward message to the Actor agent

                # E. Action passed verification! Convert to Pydantic model and apply mutations locally
                try:
                    # Convert dict to Pydantic model before passing to the engine
                    evaluation_model = DirectorEvaluation(**raw_eval_dict)
                    
                    await game_engine.apply_mutations(
                        conversation_id, 
                        evaluation_model,  # Pass the full Pydantic model, NOT .get("mutations", {})
                        current_game_state
                    )
                except Exception as mutation_err:
                    logger.error("Failed to apply game mutations safely: %s", mutation_err)
            except Exception as engine_err:
                logger.error("Director's Gate failed to validate turn safely: %s", engine_err)
                await websocket.send_text(json.dumps({"error": "Game state evaluation timeout or failure encountered."}))
                continue

            # Proceed to Actor pipeline if validation succeeds
            event = {
                "event": "user_message",
                "conversation_id": conversation_id,
                "user_id": user["id"],
                "content": content,
                "timestamp": str(datetime.utcnow())
            }
            
            # Fire user message into NATS for backend agents to digest
            await nats_publisher.publish_ephemeral(
                "roleplay.chat.user_message", 
                json.dumps(event).encode()
            )

    except WebSocketDisconnect:
        logger.info("Connection tunnel dropped cleanly for conversation %s", conversation_id)
    finally:
        # 5. Clean up open threads and references to prevent context leakage
        nats_task.cancel()
        try:
            await nats_sub.unsubscribe()
        except Exception:
            pass
        await ws_manager.disconnect(conversation_id, websocket)