"""Session advisory lock coordinates vector I/O with deletion without an SQL transaction."""
from contextlib import asynccontextmanager
from shared.db.postgres import get_conn

@asynccontextmanager
async def index_lock(scenario_id):
    async with get_conn() as conn:
        key=2000000000+scenario_id
        await conn.execute('SELECT pg_advisory_lock(%s)',(key,))
        await conn.commit()
        try:
            yield
        finally:
            await conn.execute('SELECT pg_advisory_unlock(%s)',(key,))
            await conn.commit()
