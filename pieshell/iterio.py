import os
import select
import signal
import errno
from . import log
import asyncio
from .utils.asyncutils import asyncmap, itertoasync

class RecursiveEvent(Exception): pass

def events_to_str(events):
    return ",".join([name for name in dir(select)
                     if (    name.startswith("POLL")
                         and events & getattr(select, name) != 0)])



class IOHandler(object):
    events = 0
    def __init__(self, fd, borrowed = False, usage = None):
        self.fd = fd
        self.borrowed = borrowed
        self.enabled = True
        self.usage = usage
        self.destroyed = False
        self.enable()
    def handle_event(self, event):
        pass
    def destroy(self):
        if self.destroyed: return
        if self.enabled:
            self.disable()
        if self.borrowed:
            log.log("HAND BACK %s, %s" % (self.fd, self), "ioreg")
        else:
            log.log("CLOSE DESTROY %s, %s" % (self.fd, self), "ioreg")
            os.close(self.fd)
        self.destroyed = True
    def enable(self):
        self.enabled = True
        loop = asyncio.get_event_loop()
        def callback(event):
            self.handle_event(event)
        if self.events & select.POLLIN:
            loop.add_reader(self.fd, callback, select.POLLIN)
        if self.events & select.POLLOUT:
            loop.add_writer(self.fd, callback, select.POLLOUT)
        log.log("REGISTER %s, %s, %s" % (self.fd, events_to_str(self.events), self), "ioreg")
    def disable(self):
        self.enabled = False
        loop = asyncio.get_event_loop()
        if self.events & select.POLLIN:
            loop.remove_reader(self.fd)
        if self.events & select.POLLOUT:
            loop.remove_writer(self.fd)
    def _repr_args(self):
        args = [str(self.fd)]
        if self.usage:
            args.append("for %s" % repr(self.usage))
        if self.enabled:
            args.append("enabled")
        return args
    def __repr__(self):
        t = type(self)
        return "%s.%s(%s)" % (t.__module__, t.__name__, ",".join(self._repr_args()))

class OutputHandler(IOHandler):
    events = select.POLLOUT

    def __init__(self, fd, iter, borrowed = False, usage = None):
        self.iter = iter
        self.done_future = asyncio.get_event_loop().create_future()
        IOHandler.__init__(self, fd, borrowed, usage)

    @property
    def is_running(self):
        return not self.done_future.done()

    @property
    def exception(self):
        if self.is_running: return None
        return self.done_future.exception()
    
    async def wait(self):
        return await self.done_future
    
    def destroy(self, exception = None, value = None):
        if not self.done_future.done():
            if exception is not None:
                self.done_future.set_exception(exception)
            else:
                self.done_future.set_result(value)
        IOHandler.destroy(self)

    def handle_event(self, event):
        asyncio.get_event_loop().create_task(self.send_output())

    async def get_iter(self):
        if not hasattr(self.iter, "__anext__"):
            if not hasattr(self.iter, "__aiter__"):
                self.iter = itertoasync(self.iter)
            self.iter = await self.iter.__aiter__()
        return self.iter
            
    async def send_output(self):
        iter = await self.get_iter()
        try:
            val = await iter.__anext__()
            if val is not None:
                os.write(self.fd, val)                
        except StopAsyncIteration:
            self.destroy()
        except Exception as e:
            self.destroy(e)

    def _repr_args(self):
        args = IOHandler._repr_args(self)
        if not self.is_running:
            args.append("stopped")
        return args


class LineOutputHandler(OutputHandler):
    async def send_output(self):
        iter = await self.get_iter()
        try:
            val = await iter.__anext__()
            if val is not None:
                os.write(self.fd, val + b"\n")
            log.log("WRITE %s, %s" % (self.fd, repr(val)), "io")
        except StopAsyncIteration:
            log.log("STOP ITERATION %s" % self.fd, "ioevent")
            self.destroy()
        except Exception as e:
            self.destroy(e)

class InputHandler(IOHandler):
    events = select.POLLIN | select.POLLHUP | select.POLLERR
    
    def __init__(self, fd, borrowed = False, usage = None, at_eof = None):
        self.buffer = None
        self.eof = False
        self.future = None
        self.at_eof = at_eof
        IOHandler.__init__(self, fd, borrowed, usage)

    def handle_event(self, event):
        if self.buffer is None:
            self.buffer = os.read(self.fd, 1024)
            if not self.buffer:
                self.eof = True
                self.destroy()
        if self.future is not None:
            self.future.set_result(None)
            self.future = None

    def __aiter__(self):
        return self
    
    async def __anext__(self):
        if self.buffer is None:
            if self.eof:
                if self.at_eof: await self.at_eof()
                raise StopAsyncIteration
            future = self.future = asyncio.get_event_loop().create_future()
            await future
        try:
            return self.buffer
        finally:
            self.buffer = None

    def _repr_args(self):
        args = IOHandler._repr_args(self)
        if self.eof:
            args.append("EOF")
        if self.buffer:
            args.append("data")
        return args

class LineInputHandler(InputHandler):
    def __init__(self, fd, borrowed = False, usage = None, at_eof = None):
        InputHandler.__init__(self, fd, borrowed, usage, at_eof)
        self.buffer = b""

    def handle_event(self, event):
        if b'\n' not in self.buffer:
            read_data = os.read(self.fd, 1024)
            self.buffer += read_data
            if not read_data:
                self.eof = True
                self.destroy()
            if self.future is not None:
                self.future.set_result(None)
                self.future = None

    def __aiter__(self):
        return self
    
    async def __anext__(self):
        while not self.eof and b'\n' not in self.buffer:
            future = self.future = asyncio.get_event_loop().create_future()
            await future
        if not self.buffer:
            assert self.eof
            if self.at_eof: await self.at_eof()
            raise StopAsyncIteration
        if b'\n' not in self.buffer:
            self.buffer += b'\n' # No newline at end of file...
        ret, self.buffer = self.buffer.split(b"\n", 1)
        return ret.decode("utf-8")

