"""Database-backed fixed-window limits shared by gateway workers."""
import hashlib
import time
from fastapi import Request, HTTPException
from shared.db.postgres import execute_returning

async def authentication_limit(request: Request):
    address = request.client.host if request.client else 'unknown'
    key = hashlib.sha256(address.encode()).hexdigest()
    bucket = int(time.time() // 60)
    result = await execute_returning('INSERT INTO request_limits(key,bucket,count) VALUES (%s,%s,1) ON CONFLICT(key,bucket) DO UPDATE SET count=request_limits.count+1 RETURNING count', (key,bucket))
    if result['count'] > 20:
        raise HTTPException(status_code=429, detail='Too many authentication attempts; retry in one minute', headers={'Retry-After':'60'})
