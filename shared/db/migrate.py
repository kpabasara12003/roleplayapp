"""Additive, repeatable upgrades for existing installations."""
from pathlib import Path
import hashlib
import asyncio
import selectors
import sys
from shared.db.postgres import get_conn

def migration_paths():
    candidates=[Path(__file__).resolve().parents[2]/'migrations',Path(sys.prefix)/'share'/'roleplay'/'migrations']
    for candidate in candidates:
        paths=sorted(candidate.glob('*.sql'))
        if paths:
            return paths
    raise RuntimeError('SQL migration files are missing from this installation')

async def migrate():
    async with get_conn() as conn:
        async with conn.transaction():
            await conn.execute('SELECT pg_advisory_xact_lock(735410)')
            await conn.execute('CREATE TABLE IF NOT EXISTS schema_migrations(version TEXT PRIMARY KEY, checksum TEXT NOT NULL, applied_at TIMESTAMPTZ NOT NULL DEFAULT now())')
            for path in migration_paths():
                sql = path.read_text(encoding='utf-8')
                checksum = hashlib.sha256(sql.encode()).hexdigest()
                cur = await conn.execute('SELECT checksum FROM schema_migrations WHERE version=%s', (path.name,))
                applied = await cur.fetchone()
                if applied:
                    if applied[0] != checksum:
                        raise RuntimeError(f'Applied migration changed: {path.name}')
                    continue
                await conn.execute(sql)
                if path.name.startswith('001_'):
                    cur = await conn.execute('SELECT id,api_key FROM users WHERE NOT api_key_hashed FOR UPDATE')
                    for uid, key in await cur.fetchall():
                        await conn.execute('UPDATE users SET api_key=%s,api_key_hashed=TRUE WHERE id=%s', (hashlib.sha256(key.encode()).hexdigest(), uid))
                await conn.execute('INSERT INTO schema_migrations(version,checksum) VALUES (%s,%s)', (path.name,checksum))

async def check_schema():
    from shared.db.postgres import fetch_one,fetch_all
    expected={path.name for path in migration_paths()}
    actual={row['version'] for row in await fetch_all('SELECT version FROM schema_migrations')}
    if actual!=expected:
        raise RuntimeError('Application/schema versions differ; run the matching migration release')
    for path in migration_paths():
        row = await fetch_one('SELECT checksum FROM schema_migrations WHERE version=%s', (path.name,))
        if not row or row['checksum'] != hashlib.sha256(path.read_text(encoding='utf-8').encode()).hexdigest():
            raise RuntimeError('Schema upgrade required: python -m shared.db.migrate')

async def main():
    from shared.db.postgres import close_pool
    try:
        await migrate()
    finally:
        await close_pool()

if __name__ == '__main__':
    asyncio.run(main(), loop_factory=(lambda: asyncio.SelectorEventLoop(selectors.SelectSelector())) if sys.platform == 'win32' else asyncio.new_event_loop)
