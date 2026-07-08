"""
Roleplay AI Backend - FastAPI Server
Handles HTTP / WebSocket, Swagger docs, and routes messages to NATS.
"""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from fastapi_server.config import settings
from shared.db.postgres import close_pool
from shared.utils.nats_client import NATSPublisher
from shared.utils.logger import get_logger

from fastapi_server.app.api import users, scenarios, characters, chat

logger = get_logger(__name__)

nats_pub = NATSPublisher()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup & shutdown hooks."""
    logger.info("Starting FastAPI server on port %s", settings.api_port)
    await nats_pub.connect()
    chat.nats_publisher.nc = nats_pub.nc  # Share connection with chat router
    chat.nats_publisher.js = nats_pub.js
    yield
    logger.info("Shutting down FastAPI server")
    await close_pool()
    await nats_pub.close()


app = FastAPI(
    title="Roleplay AI API",
    description="Backend API for Roleplay AI Chat Application",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(users.router)
app.include_router(scenarios.router)
app.include_router(characters.router)
app.include_router(chat.router)


@app.get("/health", tags=["Health"])
async def health_check():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "fastapi_server.app.main:app",
        host="0.0.0.0",
        port=settings.api_port,
        reload=True,
    )
