import os
from contextlib import asynccontextmanager
from typing import Any, List, Optional, Tuple
from dotenv import load_dotenv

from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool
from shared.utils.logger import get_logger

# Force an environment refresh on import
load_dotenv()

logger = get_logger(__name__)

_pool: Optional[AsyncConnectionPool] = None


async def get_pool() -> AsyncConnectionPool:
    """Lazy-init and return the async connection pool."""
    global _pool
    if _pool is None or _pool.closed:
        db_url = os.getenv("DATABASE_URL")
        
        if not db_url:
            logger.critical("DATABASE_URL environment variable is missing or NoneType!")
            raise ValueError("DATABASE_URL environment variable is not set. Check your .env file loading sequence.")

        _pool = AsyncConnectionPool(
            conninfo=db_url,
            min_size=2,
            max_size=10,
            open=False,
            timeout=30,
        )
        await _pool.open()
        
        # Safely split for logging mask
        masked_url = db_url.split("@")[-1] if "@" in db_url else "Remote Host"
        logger.info("PostgreSQL pool successfully created (%s)", masked_url)
        
    return _pool
async def close_pool():
    """Gracefully close the pool."""
    global _pool
    if _pool and not _pool.closed:
        await _pool.close()
        logger.info("PostgreSQL pool closed")


@asynccontextmanager
async def get_conn():
    """Yield a connection from the pool as an async context manager."""
    pool = await get_pool()
    async with pool.connection() as conn:
        yield conn


async def fetch_one(sql: str, params: Tuple[Any, ...] = ()) -> Optional[dict]:
    """Execute parameterized SELECT and return one row as dict."""
    async with get_conn() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(sql, params)
            return await cur.fetchone()


async def fetch_all(sql: str, params: Tuple[Any, ...] = ()) -> List[dict]:
    """Execute parameterized SELECT and return all rows as list of dicts."""
    async with get_conn() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(sql, params)
            return await cur.fetchall()


async def execute(sql: str, params: Tuple[Any, ...] = ()) -> int:
    """Execute parameterized INSERT/UPDATE/DELETE and return affected row count."""
    async with get_conn() as conn:
        async with conn.cursor() as cur:
            await cur.execute(sql, params)
            await conn.commit()
            return cur.rowcount


async def execute_returning(sql: str, params: Tuple[Any, ...] = ()) -> Optional[dict]:
    """Execute parameterized INSERT/UPDATE RETURNING and return the row."""
    async with get_conn() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(sql, params)
            row = await cur.fetchone()
            await conn.commit()
            return row
