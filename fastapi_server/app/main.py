"""
Roleplay AI Backend - FastAPI Server  fastapi_server/app/main.py
Handles HTTP / WebSocket, Swagger docs, and routes messages to NATS.
"""
from contextlib import asynccontextmanager
import asyncio

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from fastapi_server.config import settings
from shared.db.postgres import close_pool
from shared.utils.nats_client import NATSPublisher
from shared.utils.logger import get_logger

from fastapi_server.app.api import users, scenarios, characters, chat, lore, playthroughs, story_controls

logger = get_logger(__name__)

nats_pub = NATSPublisher()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handles startup registration and clean teardown mechanics."""
    logger.info("Starting FastAPI server on port %s", settings.api_port)
    from shared.db.migrate import check_schema
    from shared.utils.observability import setup_telemetry
    setup_telemetry('gateway')
    await check_schema()
    
    # Establish shared connection pool infrastructure
    await nats_pub.connect()
    chat.nats_publisher.nc = nats_pub.nc  
    chat.nats_publisher.js = nats_pub.js
    
    from shared.utils.observability import flush_telemetry
    telemetry=asyncio.create_task(flush_telemetry())
    try:
        yield
    finally:
        telemetry.cancel()
        await asyncio.gather(telemetry,return_exceptions=True)
    
    logger.info("Shutting down FastAPI server framework...")
    await close_pool()
    await nats_pub.close()
    from shared.utils.providers import close_clients
    await close_clients()

app = FastAPI(
    title="Roleplay AI API",
    description="Decoupled Bidirectional Backend Engine for Roleplay AI Chat",
    version="0.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(users.router)
app.include_router(scenarios.router)
app.include_router(characters.router)
app.include_router(chat.router)
app.include_router(lore.router)
app.include_router(playthroughs.router)
app.include_router(story_controls.router)

@app.middleware('http')
async def trace_request(request,call_next):
    from shared.utils.observability import tracer
    with tracer().start_as_current_span('http.request') as span:
        span.set_attribute('http.request.method',request.method)
        response=await call_next(request)
        span.set_attribute('http.response.status_code',response.status_code)
        return response

@app.get('/diagnostics', tags=['Health'])
async def diagnostics():
    from shared.db.postgres import fetch_all,fetch_one
    return {'jobs':await fetch_all('SELECT stage,status,count(*) AS count FROM jobs GROUP BY stage,status'),
            'outbox':await fetch_one('SELECT count(*) AS pending,extract(epoch FROM now()-min(created_at)) AS oldest_seconds FROM event_outbox'),
            'latency':await fetch_all("SELECT stage,percentile_cont(.5) WITHIN GROUP(ORDER BY extract(epoch FROM completed_at-created_at)) AS p50_seconds,percentile_cont(.95) WITHIN GROUP(ORDER BY extract(epoch FROM completed_at-created_at)) AS p95_seconds FROM jobs WHERE completed_at>now()-interval '1 day' GROUP BY stage")}

@app.get("/health", tags=["Health"])
async def health_check():
    return {"status": "ok"}

@app.get('/ready', tags=['Health'])
async def readiness():
    from shared.db.postgres import fetch_one
    try:
        await asyncio.wait_for(fetch_one('SELECT 1'), timeout=3)
        if not nats_pub.nc or not nats_pub.nc.is_connected:
            raise RuntimeError('NATS disconnected')
        await nats_pub.js.stream_info('roleplay_chat')
        await asyncio.gather(*(nats_pub.nc.request('roleplay.health.' + name, b'{}', timeout=2) for name in ('actor','director','chronicler','outbox')))
        from shared.utils.providers import valkey
        await valkey().ping()
    except Exception:
        raise HTTPException(status_code=503, detail='Dependencies unavailable')
    return {'status': 'ready'}

if __name__ == "__main__":
    # Never call uvicorn's CLI here: it builds its own event loop (Proactor on
    # Windows), which psycopg cannot use in async mode. The launcher below runs the
    # server inside a SelectorEventLoop instead.
    from fastapi_server.run import main as run_server

    run_server()
