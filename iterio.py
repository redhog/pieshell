import os
import fcntl
import select

def _set_cloexec_flag(fd, cloexec=True):
    try:
        cloexec_flag = fcntl.FD_CLOEXEC
    except AttributeError:
        cloexec_flag = 1

    old = fcntl.fcntl(fd, fcntl.F_GETFD)
    if cloexec:
        fcntl.fcntl(fd, fcntl.F_SETFD, old | cloexec_flag)
    else:
        fcntl.fcntl(fd, fcntl.F_SETFD, old & ~cloexec_flag)

def pipe_cloexec():
    """Create a pipe with FDs set CLOEXEC."""
    # Pipes' FDs are set CLOEXEC by default because we don't want them
    # to be inherited by other subprocesses: the CLOEXEC flag is removed
    # from the child's FDs by _dup2(), between fork() and exec().
    # This is not atomic: we would need the pipe2() syscall for that.
    r, w = os.pipe()
    _set_cloexec_flag(r)
    _set_cloexec_flag(w)
    return r, w

class IOHandlers(object):
    ioHandlers = {}

    poll = select.poll()

    @classmethod
    def register(cls, ioHandler):
        cls.poll.register(ioHandler.fd, ioHandler.events)
        cls.ioHandlers[ioHandler.fd] = ioHandler

    @classmethod
    def deregister(cls, ioHandler):
        cls.poll.unregister(ioHandler.fd)
        cls.ioHandlers[ioHandler.fd]
    
    @classmethod
    def handleIo(cls):
        while True:
            events = cls.poll.poll()
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
        os.close(self.fd)

class InputHandler(IOHandler):
    events = select.POLLOUT

    def __init__(self, iter):
        self.iter = iter
        inr, inw = pipe_cloexec()
        IOHandler.__init__(self, inw)
        self.pipe_fd = inr

    def handle_event(self, event):
        try:
            os.write(self.fd, self.iter.next())
        except StopIteration:
            self.destroy()

class LineInputHandler(InputHandler):
    def handle_event(self, event):
        try:
            os.write(self.fd, self.iter.next() + "\n")
        except StopIteration:
            self.destroy()

class OutputHandler(IOHandler):
    events = select.POLLIN | select.POLLHUP | select.POLLERR
    
    def __init__(self):
        outr, outw = pipe_cloexec()
        IOHandler.__init__(self, outr)
        self.pipe_fd = outw
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

class LineOutputHandler(OutputHandler):
    def __init__(self):
        OutputHandler.__init__(self)
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
