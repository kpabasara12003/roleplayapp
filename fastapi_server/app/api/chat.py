#roleplay_backend/app/api/chat.py
import json
import uuid
import secrets
from typing import Optional, List
import asyncio
from datetime import datetime
from shared.schemas.engine import DirectorEvaluation
from fastapi import APIRouter, HTTPException, Depends, WebSocket, WebSocketDisconnect, Query
from pydantic import BaseModel, Field
from nats.js.api import ConsumerConfig, DeliverPolicy
from shared.utils.game_engine import GameEngine 
from shared.db.postgres import fetch_one, fetch_all, execute_returning, execute, transaction
from shared.utils.nats_client import NATSPublisher
from fastapi_server.app.services.ws_manager import ws_manager
from fastapi_server.app.api.users import get_current_user, key_digest
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
    content: str = Field(min_length=1, max_length=16000)
    request_id: uuid.UUID = Field(default_factory=uuid.uuid4)

@router.post('/ticket/{conversation_id}')
async def websocket_ticket(conversation_id: int, user: dict = Depends(get_current_user)):
    owned = await fetch_one('SELECT id FROM conversations WHERE id=%s AND user_id=%s', (conversation_id,user['id']))
    if not owned:
        raise HTTPException(status_code=404, detail='Conversation not found')
    ticket = secrets.token_urlsafe(32)
    await execute('DELETE FROM websocket_tickets WHERE expires_at<now()')
    await execute("INSERT INTO websocket_tickets(digest,user_id,conversation_id,expires_at) VALUES (%s,%s,%s,now()+interval '1 minute')", (key_digest(ticket),user['id'],conversation_id))
    return {'ticket': ticket}

class ChatMessageResponse(BaseModel):
    turn_id: Optional[uuid.UUID] = None
    request_id: Optional[uuid.UUID] = None
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
    from shared.utils.turns import enqueue
    async with transaction() as conn:
        await conn.execute('SELECT pg_advisory_xact_lock(%s)', (payload.conversation_id,))
        conv = await fetch_one("SELECT id,state_version FROM conversations WHERE id=%s AND user_id=%s AND status='active'", (payload.conversation_id,user['id']))
        if not conv:
            raise HTTPException(status_code=404, detail='Active conversation not found')
        existing = await fetch_one('SELECT * FROM turns WHERE conversation_id=%s AND request_id=%s', (payload.conversation_id,payload.request_id))
        if existing:
            if existing['content'] != payload.content:
                raise HTTPException(status_code=409, detail='Request ID was already used for different content')
            msg = await fetch_one('SELECT * FROM messages WHERE id=%s',(existing['user_message_id'],))
            return {**msg,'turn_id':existing['id'],'request_id':payload.request_id}
        active = await fetch_one("SELECT id FROM turns WHERE conversation_id=%s AND status IN ('validating','generating','narrating')", (payload.conversation_id,))
        if active:
            raise HTTPException(status_code=409, detail='A response is still being generated for this conversation')
        turn_id = uuid.uuid4()
        msg = await execute_returning("INSERT INTO messages(conversation_id,sender,content,metadata,event_id) VALUES (%s,'user',%s,'{\"action_status\":\"pending\"}',%s) RETURNING *", (payload.conversation_id,payload.content,'user-'+str(turn_id)))
        await execute("INSERT INTO turns(id,conversation_id,request_id,user_message_id,content,user_id,status,state_version) VALUES (%s,%s,%s,%s,%s,%s,'validating',%s)", (turn_id,payload.conversation_id,payload.request_id,msg['id'],payload.content,user['id'],conv['state_version']))
        data = {'turn_id':str(turn_id),'event_id':str(turn_id),'conversation_id':payload.conversation_id,'user_id':user['id'],'content':payload.content,'message_id':msg['id']}
        await enqueue(turn_id,'validate',data)
        await nats_publisher.publish('roleplay.chat.user_message',json.dumps({'event':'user_message',**data}).encode())
        return {**msg,'turn_id':turn_id,'request_id':payload.request_id}


@router.get('/turn/{turn_id}')
async def turn_status(turn_id: uuid.UUID, user: dict = Depends(get_current_user)):
    row = await fetch_one('SELECT * FROM turns WHERE id=%s AND user_id=%s',(turn_id,user['id']))
    if not row:
        raise HTTPException(status_code=404,detail='Turn not found')
    row['stages'] = await fetch_all('SELECT stage,status,attempts,last_error,completed_at FROM jobs WHERE turn_id=%s ORDER BY created_at',(turn_id,))
    return row


@router.post('/turn/{turn_id}/retry')
async def retry_turn(turn_id: uuid.UUID, user: dict = Depends(get_current_user)):
    async with transaction() as conn:
        row = await fetch_one('SELECT * FROM turns WHERE id=%s AND user_id=%s',(turn_id,user['id']))
        if not row:
            raise HTTPException(status_code=404,detail='Turn not found')
        await conn.execute('SELECT pg_advisory_xact_lock(%s)',(row['conversation_id'],))
        current = await fetch_one('SELECT state_version FROM conversations WHERE id=%s FOR UPDATE',(row['conversation_id'],))
        if row['status'] != 'failed' or current['state_version'] != row['state_version']:
            raise HTTPException(status_code=409,detail='Only failed turns with an unchanged scene can resume')
        if await fetch_one("SELECT id FROM turns WHERE conversation_id=%s AND status IN ('validating','generating','narrating')",(row['conversation_id'],)):
            raise HTTPException(status_code=409,detail='Another turn is active')
        job = await fetch_one("SELECT stage FROM jobs WHERE turn_id=%s AND status='dead' FOR UPDATE",(turn_id,))
        if not job:
            raise HTTPException(status_code=409,detail='No failed stage to retry')
        await execute("UPDATE jobs SET status='pending',attempts=0,last_error=NULL,available_at=now(),last_notified_at=NULL WHERE turn_id=%s AND status='dead'",(turn_id,))
        await execute('UPDATE turns SET status=%s,failure=NULL WHERE id=%s',({'validate':'validating','actor':'generating','director':'narrating'}[job['stage']],turn_id))
    return {'turn_id':turn_id,'status':'resuming'}


@router.get("/history/{conversation_id}", response_model=List[ChatMessageResponse])
async def get_history(conversation_id: int, user: dict = Depends(get_current_user), before_id: Optional[int] = None, limit: int = Query(100, ge=1, le=500)):
    conv = await fetch_one("SELECT id FROM conversations WHERE id=%s AND user_id=%s", (conversation_id, user["id"]))
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return await fetch_all(
        """SELECT id, conversation_id, sender, content, created_at
           FROM (SELECT * FROM messages WHERE conversation_id = %s AND (%s::int IS NULL OR id < %s) ORDER BY id DESC LIMIT %s) recent ORDER BY id ASC""",
        (conversation_id, before_id, before_id, limit),
    )

@router.websocket("/ws/{conversation_id}")
async def websocket_chat(
    websocket: WebSocket, 
    conversation_id: int,
    last_seen_seq: Optional[int] = Query(None)  # Client supplies this parameter on reconnection
):
    """Decoupled real-time gateway pipeline channel with JetStream stream tracking."""
    ticket = websocket.query_params.get("ticket")
    if not ticket:
        await websocket.close(code=1008, reason="Missing ticket")
        return

    user = await execute_returning('DELETE FROM websocket_tickets WHERE digest=%s AND conversation_id=%s AND expires_at>now() RETURNING user_id AS id', (key_digest(ticket),conversation_id))
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
    async def forward_live(msg):
        await websocket.send_json({'stream_sequence_id': None, 'event_body': json.loads(msg.data)})
    live_sub = await nats_publisher.nc.subscribe(f'roleplay.live.stream.{conversation_id}', cb=forward_live)

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
                await websocket.send_text(json.dumps({"event_body": {"event": "state_change", "payload": {"state": "error", "error_detail": "Invalid message"}}}))
                continue

            if not content:
                continue

            try:
                accepted = await send_message(ChatMessageRequest(conversation_id=conversation_id, content=content, request_id=packet.get('request_id') or uuid.uuid4()), user)
                await websocket.send_json({'event_body': {'event':'turn_accepted','turn_id':str(accepted['turn_id']),'request_id':str(accepted['request_id'])}})
            except HTTPException as exc:
                await websocket.send_json({"event_body": {"event": "action_blocked", "payload": {"reason": exc.detail}}})
            except Exception:
                logger.exception("WebSocket turn failed")
                await websocket.send_json({"event_body": {"event": "state_change", "payload": {"state": "error", "error_detail": "Unable to process turn; please retry."}}})

    except WebSocketDisconnect:
        logger.info("Connection tunnel dropped cleanly for conversation %s", conversation_id)
    finally:
        # 5. Clean up open threads and references to prevent context leakage
        nats_task.cancel()
        await asyncio.gather(nats_task, return_exceptions=True)
        try:
            await nats_sub.unsubscribe()
            await live_sub.unsubscribe()
        except Exception:
            pass
        await ws_manager.disconnect(conversation_id, websocket)
