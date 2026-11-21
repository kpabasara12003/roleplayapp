"""Safe push-to-pull cutover without replaying already persisted history."""
from nats.js.api import ConsumerConfig,DeliverPolicy
from nats.js.errors import NotFoundError

async def pull_consumer(js,subject,durable,stream,legacy=None):
    try:
        await js.consumer_info(stream,durable)
        return await js.pull_subscribe(subject,durable=durable,stream=stream)
    except NotFoundError:
        config=ConsumerConfig(ack_wait=60,max_ack_pending=32)
        if legacy:
            try:
                old=await js.consumer_info(stream,legacy)
                config.deliver_policy=DeliverPolicy.BY_START_SEQUENCE
                config.opt_start_seq=old.ack_floor.stream_seq+1
            except NotFoundError:
                config.deliver_policy=DeliverPolicy.ALL
        return await js.pull_subscribe(subject,durable=durable,stream=stream,config=config)
