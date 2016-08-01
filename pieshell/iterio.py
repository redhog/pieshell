import os
import fcntl
import select
import threading

debug = False

class IOManager(object):
    def __init__(self):
        self.io_handlers = {}
        self.delay = 0

        self.poll = select.poll()

        self.cleanup = []

    def register_cleanup(self, cleanup):
        self.cleanup.append(cleanup)

    def delay_cleanup(self):
        self.delay += 1

    def perform_cleanup(self):
        if self.delay > 0:
            self.delay -= 1
        self._do_cleanup()

    def register(self, ioHandler):
        self.poll.register(ioHandler.fd, ioHandler.events)
        self.io_handlers[ioHandler.fd] = ioHandler
        if debug: print "REGISTER", ioHandler.fd, ioHandler.events, ioHandler

    def _do_cleanup(self):
        while self.delay == 0 and not len(self.io_handlers) and self.cleanup:
            self.cleanup.pop()()

    def deregister(self, ioHandler):
        self.poll.unregister(ioHandler.fd)
        del self.io_handlers[ioHandler.fd]
        self._do_cleanup()
        if debug: print "DEREGISTER", ioHandler.fd, ioHandler
    
    def handle_io(self):
        while self.io_handlers:
            events = self.poll.poll()
            if debug: print "EVENTS", events
            assert events
            done = False
            for fd, event in events:
                event_done = self.io_handlers[fd].handle_event(event)
                done = done or event_done
            if done:
                return

io_managers = threading.local()
def get_io_manager():
    if not hasattr(io_managers, 'manager'):
        io_managers.manager = IOManager()
    return io_managers.manager


class IOHandler(object):
    events = 0
    def __init__(self, fd):
        self.fd = fd
        get_io_manager().register(self)
    def handle_event(self, event):
        pass
    def destroy(self):
        get_io_manager().deregister(self)
        if debug: print "CLOSE DESTROY", self.fd, self
        os.close(self.fd)

class OutputHandler(IOHandler):
    events = select.POLLOUT

    def __init__(self, fd, iter):
        self.iter = iter
        IOHandler.__init__(self, fd)

    def handle_event(self, event):
        try:
            os.write(self.fd, self.iter.next())
        except StopIteration:
            self.destroy()

class LineOutputHandler(OutputHandler):
    def handle_event(self, event):
        try:
            val = self.iter.next()
            os.write(self.fd, val + "\n")
            if debug: print "WRITE", self.fd, val
        except StopIteration:
            if debug: print "STOP ITERATION", self.fd
            self.destroy()

class InputHandler(IOHandler):
    events = select.POLLIN | select.POLLHUP | select.POLLERR
    
    def __init__(self, fd):
        IOHandler.__init__(self, fd)
        self.buffer = None
        self.eof = False

    def handle_event(self, event):
        if event == select.POLLHUP or event == select.POLLERR:
            self.eof = True
            self.destroy()
        elif self.buffer is None:
            self.buffer = os.read(self.fd, 1024)
        return True

    def __iter__(self):
        return self

    def next(self):
        while self.buffer is None:
            get_io_manager().handle_io()
            if self.eof:
                raise StopIteration
        try:
            return self.buffer
        finally:
            self.buffer = None

class LineInputHandler(InputHandler):
    def __init__(self, fd):
        InputHandler.__init__(self, fd)
        self.buffer = ""

    def handle_event(self, event):
        if event == select.POLLHUP or event == select.POLLERR:
            self.eof = True
            self.destroy()
        elif '\n' not in self.buffer:
            self.buffer = self.buffer + os.read(self.fd, 1024)
        return True


    def next(self):
        while '\n' not in self.buffer:
            get_io_manager().handle_io()
            if self.eof:
                raise StopIteration
        ret, self.buffer = self.buffer.split("\n", 1)
        return ret
