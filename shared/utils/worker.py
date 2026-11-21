"""Replica-safe job workers. SQL owns execution; NATS supplies wakeups."""
import asyncio
import json
import os
import time
from shared.utils.logger import get_logger
from shared.utils.turns import job_claim, claim_job, heartbeat, fail_job, StaleJob

logger = get_logger(__name__)

async def consume(publisher, sub, handler, concurrency=4):
    tasks = set()
    async def process(msg):
        claim = None
        token = None
        span_scope = None
        started=time.monotonic()
        outcome='success'
        try:
            data = json.loads(msg.data)
            from shared.utils.observability import tracer
            from opentelemetry.propagate import extract
            span_scope=tracer().start_as_current_span('job.'+handler.__name__,context=extract(data.get('_trace',{})))
            span=span_scope.__enter__()
            if data.get('job_id'):
                claim = await claim_job(data['job_id'])
                if claim is None:
                    await msg.ack()
                    return
                token = job_claim.set(claim)
                span.set_attributes({'turn.id':claim.turn_id,'job.id':claim.id,'job.stage':claim.stage,'job.fence':claim.fence})
            async def renew():
                while True:
                    await asyncio.sleep(10)
                    if claim:
                        await heartbeat(claim)
                    await msg.in_progress()
            work = asyncio.create_task(handler(data))
            renewer = asyncio.create_task(renew())
            try:
                done, _ = await asyncio.wait([work,renewer], timeout=float(os.getenv('JOB_TIMEOUT_SECONDS','180')), return_when=asyncio.FIRST_COMPLETED)
                if not done:
                    raise TimeoutError('Job exceeded total deadline')
                if renewer in done and work not in done:
                    await renewer
                    raise StaleJob('Heartbeat stopped')
                await work
            finally:
                for task in (work,renewer):
                    if not task.done():
                        task.cancel()
                await asyncio.gather(work,renewer,return_exceptions=True)
            await msg.ack()
        except Exception as exc:
            outcome='failed'
            if span_scope:
                span.record_exception(exc)
            logger.exception('Job failed')
            if token is not None:
                job_claim.reset(token)
                token = None
            if claim:
                await fail_job(claim,exc)
                await msg.ack()  # Durable SQL recovery schedules the retry.
            elif msg.metadata.num_delivered >= 5:
                await publisher.publish('roleplay.events.deadletter.worker',json.dumps({'subject':msg.subject,'error':str(exc)[:500],'payload':msg.data.decode(errors='replace')}).encode())
                await msg.term()
            else:
                await msg.nak(delay=5)
        finally:
            from opentelemetry import metrics
            attributes={'stage':claim.stage if claim else handler.__name__,'outcome':outcome}
            meter=metrics.get_meter('roleplay.backend')
            meter.create_counter('roleplay.job.attempts').add(1,attributes)
            meter.create_histogram('roleplay.job.duration',unit='s').record(time.monotonic()-started,attributes)
            if span_scope:
                span_scope.__exit__(None,None,None)
            if token is not None:
                job_claim.reset(token)

    try:
        while True:
            if len(tasks) >= concurrency:
                done,_ = await asyncio.wait(tasks,return_when=asyncio.FIRST_COMPLETED)
                for task in done:
                    task.result()
                    tasks.remove(task)
            try:
                if hasattr(sub,'fetch'):
                    messages = await sub.fetch(batch=1,timeout=1)
                    msg = messages[0]
                else:
                    msg = await sub.next_msg(timeout=1)
            except asyncio.TimeoutError:
                for task in list(tasks):
                    if task.done():
                        task.result()
                        tasks.remove(task)
                continue
            tasks.add(asyncio.create_task(process(msg)))
    finally:
        try:
            await asyncio.wait_for(asyncio.gather(*tasks,return_exceptions=True),timeout=20)
        except asyncio.TimeoutError:
            logger.warning('Unfinished jobs will recover after their leases expire')

async def run_agent(agent):
    from shared.utils.runtime import install_shutdown_handlers
    restore=install_shutdown_handlers()
    from shared.db.migrate import check_schema
    from shared.utils.observability import setup_telemetry
    setup_telemetry(type(agent).__name__)
    from shared.utils.observability import flush_telemetry
    telemetry=asyncio.create_task(flush_telemetry())
    await check_schema()
    try:
        await agent.nats_publisher.connect()
        async def health(msg):
            await msg.respond(b'{"status":"ok"}')
        name = type(agent).__name__.lower().replace('agent','')
        await agent.nats_publisher.nc.subscribe('roleplay.health.'+name,cb=health)
        await agent.run()
    finally:
        telemetry.cancel()
        await asyncio.gather(telemetry,return_exceptions=True)
        for name in ('rpc_task','indexing_task','deletion_task'):
            task = getattr(agent,name,None)
            if task:
                task.cancel()
                await asyncio.gather(task,return_exceptions=True)
        await agent.nats_publisher.close()
        from shared.utils.providers import close_clients
        await close_clients()
        from shared.db.postgres import close_pool
        await close_pool()
        from shared.db import qdrant
        if qdrant._client is not None:
            await qdrant._client.close()
            qdrant._client=None
        restore()
