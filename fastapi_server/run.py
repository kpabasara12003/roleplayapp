"""Selector-loop launcher for the FastAPI gateway.

Windows' default ProactorEventLoop is incompatible with psycopg's async mode
(``Psycopg cannot use the 'ProactorEventLoop' to run in async mode``), which makes
every database call fail with a 30s pool timeout. uvicorn's CLI builds its own event
loop, so the fix has to live here: construct the server inside a SelectorEventLoop.

Usage:
    python -m fastapi_server.run
"""
import asyncio
import selectors
import sys

import uvicorn

from fastapi_server.config import settings
from shared.utils.logger import get_logger

logger = get_logger(__name__)


async def _serve() -> None:
    config = uvicorn.Config(
        "fastapi_server.app.main:app",
        host="0.0.0.0",
        port=settings.api_port,
        loop="asyncio",
        reload=False,
        access_log=False,  # WebSocket query strings contain credentials.
        log_level=settings.log_level.lower(),
    )
    server = uvicorn.Server(config)
    await server.serve()


def main() -> None:
    logger.info("Starting FastAPI gateway on port %s", settings.api_port)
    if sys.platform == "win32":
        # psycopg async only supports a SelectorEventLoop on Windows.
        asyncio.run(
            _serve(),
            loop_factory=lambda: asyncio.SelectorEventLoop(selectors.SelectSelector()),
        )
    else:
        asyncio.run(_serve())


if __name__ == "__main__":
    main()
