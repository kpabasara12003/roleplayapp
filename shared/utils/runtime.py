import asyncio
import signal

def install_shutdown_handlers():
    loop=asyncio.get_running_loop()
    task=asyncio.current_task()
    previous={}
    def cancel(*_):
        loop.call_soon_threadsafe(task.cancel)
    for name in ('SIGTERM','SIGINT','SIGBREAK'):
        sig=getattr(signal,name,None)
        if sig is not None:
            previous[sig]=signal.signal(sig,cancel)
    return lambda: [signal.signal(sig,handler) for sig,handler in previous.items()]
