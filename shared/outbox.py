"""Independent event delivery and expired-job recovery service."""
import asyncio
import selectors
import sys
from shared.utils.nats_client import NATSPublisher
from shared.utils.turns import recover_jobs
from shared.db.migrate import check_schema
from shared.db.postgres import close_pool

async def main():
    from shared.utils.observability import setup_telemetry,flush_telemetry
    setup_telemetry('outbox')
    from shared.utils.runtime import install_shutdown_handlers
    restore=install_shutdown_handlers()
    await check_schema()
    publisher = NATSPublisher()
    await publisher.connect()
    async def health(msg):
        await msg.respond(b'{"status":"ok"}')
    await publisher.nc.subscribe('roleplay.health.outbox',cb=health)
    async def recover():
        while True:
            await recover_jobs()
            await asyncio.sleep(5)
    from shared.utils.catalog_index import catalog_index_loop
    tasks = [asyncio.create_task(publisher.relay_outbox()),asyncio.create_task(recover()),asyncio.create_task(flush_telemetry()),asyncio.create_task(catalog_index_loop())]
    try:
        await asyncio.gather(*tasks)
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks,return_exceptions=True)
        await publisher.close()
        await close_pool()
        restore()

if __name__=='__main__':
    try:
        asyncio.run(main(),loop_factory=(lambda: asyncio.SelectorEventLoop(selectors.SelectSelector())) if sys.platform=='win32' else asyncio.new_event_loop)
    except (KeyboardInterrupt,asyncio.CancelledError):
        pass
