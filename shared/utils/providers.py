"""Shared HTTP pools, Valkey admission control, circuit breaking, total deadlines."""
import asyncio
import hashlib
import json
import os
import random
import time
from contextlib import asynccontextmanager
import httpx
from redis.asyncio import Redis

_http = None
_valkey = None

def http_client():
    global _http
    if _http is None or _http.is_closed:
        _http = httpx.AsyncClient(timeout=httpx.Timeout(45,connect=5),limits=httpx.Limits(max_connections=32,max_keepalive_connections=16))
    return _http

def valkey():
    global _valkey
    if _valkey is None:
        _valkey = Redis.from_url(os.getenv('VALKEY_URL','redis://127.0.0.1:6379/0'),decode_responses=True,socket_connect_timeout=2,socket_timeout=2)
    return _valkey

# One atomic reservation across workers. Token counts are conservative reservations,
# not billing records. A bounded call deadline prevents permanent semaphore claims.
ADMIT = """
local tm=redis.call('TIME'); local now=tonumber(tm[1]); local bucket=math.floor(now/60)
local req=KEYS[1]..':rpm:'..bucket; local tok=KEYS[1]..':tpm:'..bucket
if redis.call('EXISTS',KEYS[1]..':open')==1 then return -2 end
if tonumber(redis.call('GET',req) or '0')>=tonumber(ARGV[1]) then return -1 end
if tonumber(redis.call('GET',tok) or '0')+tonumber(ARGV[3])>tonumber(ARGV[2]) then return -1 end
redis.call('ZREMRANGEBYSCORE',KEYS[1]..':active','-inf',now)
if redis.call('ZCARD',KEYS[1]..':active')>=tonumber(ARGV[4]) then return -1 end
redis.call('INCR',req); redis.call('EXPIRE',req,120)
redis.call('INCRBY',tok,ARGV[3]); redis.call('EXPIRE',tok,120)
redis.call('ZADD',KEYS[1]..':active',now+tonumber(ARGV[6]),ARGV[5]); redis.call('EXPIRE',KEYS[1]..':active',tonumber(ARGV[6])+5)
return 1
"""

@asynccontextmanager
async def admission(url, token_budget=1):
    import uuid
    # An optional group lets different endpoints share one provider-account budget.
    group=os.getenv('PROVIDER_BUDGET_GROUP') or url
    key = 'rp:provider:'+hashlib.sha256(group.encode()).hexdigest()[:16]
    owner = str(uuid.uuid4())
    client = valkey()
    limit = int(os.getenv('PROVIDER_RPM','120'))
    tpm = int(os.getenv('PROVIDER_TPM','1000000'))
    if token_budget>tpm:
        raise ValueError('Request exceeds configured provider token budget')
    async with asyncio.timeout(30):
        while True:
            result = await client.eval(ADMIT,1,key,limit,tpm,token_budget,int(os.getenv('PROVIDER_CONCURRENCY','8')),owner,90)
            if result == 1:
                break
            if result == -2:
                raise RuntimeError('Provider circuit is open')
            await asyncio.sleep(random.uniform(.15,.4))
    try:
        async with asyncio.timeout(75):
            yield http_client()
        await client.delete(key+':failures')
    except (httpx.TransportError,httpx.HTTPStatusError,TimeoutError) as exc:
        if isinstance(exc,httpx.HTTPStatusError) and exc.response.status_code<500:
            if exc.response.status_code==429:
                await client.set(key+':open','1',ex=3)
            raise
        failures = await client.incr(key+':failures')
        await client.expire(key+':failures',60)
        if failures>=5:
            await client.set(key+':open','1',ex=20)
        raise
    finally:
        await client.zrem(key+':active',owner)

async def close_clients():
    global _http, _valkey
    if _http:
        await _http.aclose()
    if _valkey:
        await _valkey.aclose()
    _http = _valkey = None

async def retry_delay(attempt, retry_after=None):
    try:
        seconds = min(30,float(retry_after)) if retry_after else min(15,2**attempt)+random.uniform(0,.5)
    except ValueError:
        seconds = min(15,2**attempt)+random.uniform(0,.5)
    await asyncio.sleep(seconds)
