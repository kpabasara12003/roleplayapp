"""Bound HTTP request bodies before JSON parsing; this app has no file uploads."""
import json

class RequestBodyLimit:
    def __init__(self, app, max_bytes=1048576):
        self.app=app
        self.max_bytes=max_bytes

    async def __call__(self, scope, receive, send):
        if scope['type']!='http' or scope['method'] not in ('POST','PUT','PATCH'):
            return await self.app(scope,receive,send)
        chunks=[]
        size=0
        while True:
            message=await receive()
            if message['type']=='http.disconnect':
                return
            chunk=message.get('body',b'')
            size+=len(chunk)
            if size>self.max_bytes:
                body=json.dumps({'detail':f'Request body exceeds {self.max_bytes} bytes'}).encode()
                await send({'type':'http.response.start','status':413,'headers':[(b'content-type',b'application/json'),(b'content-length',str(len(body)).encode())]})
                await send({'type':'http.response.body','body':body})
                return
            chunks.append(chunk)
            if not message.get('more_body',False):break
        pending=True
        async def replay():
            nonlocal pending
            if pending:
                pending=False
                return {'type':'http.request','body':b''.join(chunks),'more_body':False}
            return await receive()
        await self.app(scope,replay,send)
