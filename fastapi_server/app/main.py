"""
Roleplay AI Backend - FastAPI Server  fastapi_server/app/main.py
Handles HTTP / WebSocket, Swagger docs, and routes messages to NATS.
"""
import os
import sys
import selectors
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from fastapi_server.config import settings
from shared.db.postgres import close_pool
from shared.utils.nats_client import NATSPublisher
from shared.utils.logger import get_logger

# Import the new consumer background routing agent
from fastapi_server.app.workers.nats_consumer import nats_consumer_worker
from fastapi_server.app.api import users, scenarios, characters, chat

logger = get_logger(__name__)

nats_pub = NATSPublisher()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handles startup registration and clean teardown mechanics."""
    logger.info("Starting FastAPI server on port %s", settings.api_port)
    
    # Establish shared connection pool infrastructure
    await nats_pub.connect()
    chat.nats_publisher.nc = nats_pub.nc  
    chat.nats_publisher.js = nats_pub.js
    
    # Launch the backplane NATS to WebSocket forwarder task
    await nats_consumer_worker.start(nats_pub.nc)
    
    yield
    
    logger.info("Shutting down FastAPI server framework...")
    await nats_consumer_worker.stop()
    await close_pool()
    await nats_pub.close()

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

@app.get("/health", tags=["Health"])
async def health_check():
    return {"status": "ok"}

if __name__ == "__main__":
    import uvicorn
    
    # Apply standard WindowsSelectorEventLoopPolicy setup implicitly if executing directly via CLI on Windows
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        
    uvicorn.run(
        "fastapi_server.app.main:app",
        host="0.0.0.0",
        port=settings.api_port,
        reload=True,
    )