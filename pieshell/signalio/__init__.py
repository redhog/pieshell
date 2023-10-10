import os
from .. import log
import asyncio
from .signalutils import *

try:
    import signalfd
except Exception as e:
    log.log("No support for signalfd: %s" % (e, ), "signalsupport")
    print("No signalfd support", e)
    from . import manager_asyncio as manager
else:
    from . import manager_signalfd as manager


class SignalHandler(object):
    def __init__(self, filter):
        self.filter = filter
        manager.get_signal_manager().register(self)
    def handle_event(self, event):
        pass
    def destroy(self):
        manager.get_signal_manager().deregister(self)
        log.log("CLOSE DESTROY %s, %s" % (self.filter, self), "signalreg")
    
class SignalIteratorHandler(SignalHandler):
    def __init__(self, filter):
        SignalHandler.__init__(self, filter)
        self.future = None
        self.buffer = []
    def handle_event(self, event):
        self.buffer[0:0] = [event]
        if self.future is not None:
            self.future.set_result(None)

    async def __aiter__(self):
        return self
    
    async def __anext__(self):
        if not self.buffer:
            self.future = asyncio.get_event_loop().create_future()
            await self.future
        return self.buffer.pop()

class ProcessSignalHandler(SignalHandler):
    def __init__(self, pid):
        self.last_event = None
        self.done_future = asyncio.get_event_loop().create_future()
        self.pid = pid
        SignalHandler.__init__(self, {"ssi_pid": pid})

    def handle_event(self, event):
        log.log("Process event %s" % self.pid, "signal")
        self.last_event = event
        if event["ssi_code"] == CLD_EXITED:
            log.log("EXIT %s" % self.pid, "signal")
            #if exception is not None:
            #    self.done_future.set_exception(exception)
            #else:
            # Do something with exit code here?
            self.done_future.set_result(event)
            self.destroy()

    @property
    def is_running(self):
        return not self.done_future.done()

    @property
    def exception(self):
        if self.is_running: return None
        return self.done_future.exception()
    
    async def wait(self):
        return await self.done_future
        
