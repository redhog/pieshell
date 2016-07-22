import os
import fcntl
import select

debug = False

class IOHandlers(object):
    ioHandlers = {}
    delay = 0

    poll = select.poll()

    cleanup = []

    @classmethod
    def register_cleanup(cls, cleanup):
        cls.cleanup.append(cleanup)

    @classmethod
    def delay_cleanup(cls):
        cls.delay += 1

    @classmethod
    def perform_cleanup(cls):
        if cls.delay > 0:
            cls.delay -= 1
        cls._do_cleanup()

    @classmethod
    def register(cls, ioHandler):
        cls.poll.register(ioHandler.fd, ioHandler.events)
        cls.ioHandlers[ioHandler.fd] = ioHandler
        if debug: print "REGISTER", ioHandler.fd, ioHandler.events, ioHandler

    @classmethod    
    def _do_cleanup(cls):
        while cls.delay == 0 and not len(cls.ioHandlers) and cls.cleanup:
            cls.cleanup.pop()()

    @classmethod
    def deregister(cls, ioHandler):
        cls.poll.unregister(ioHandler.fd)
        del cls.ioHandlers[ioHandler.fd]
        cls._do_cleanup()
        if debug: print "DEREGISTER", ioHandler.fd, ioHandler
    
    @classmethod
    def handleIo(cls):
        while cls.ioHandlers:
            events = cls.poll.poll()
            if debug: print "EVENTS", events
            assert events
            done = False
            for fd, event in events:
                event_done = cls.ioHandlers[fd].handle_event(event)
                done = done or event_done
            if done:
                return

class IOHandler(object):
    events = 0
    def __init__(self, fd):
        self.fd = fd
        IOHandlers.register(self)
    def handle_event(self, event):
        pass
    def destroy(self):
        IOHandlers.deregister(self)
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
            IOHandlers.handleIo()
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
            IOHandlers.handleIo()
            if self.eof:
                raise StopIteration
        ret, self.buffer = self.buffer.split("\n", 1)
        return ret
