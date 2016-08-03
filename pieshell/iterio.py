import os
import fcntl
import select
import threading
import signalfd
import signal

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

    def register(self, io_handler):
        self.poll.register(io_handler.fd, io_handler.events)
        self.io_handlers[io_handler.fd] = io_handler
        if debug: print "REGISTER", io_handler.fd, io_handler.events, io_handler

    def _do_cleanup(self):
        while self.delay == 0 and not len(self.io_handlers) and self.cleanup:
            self.cleanup.pop()()

    def deregister(self, io_handler):
        self.poll.unregister(io_handler.fd)
        del self.io_handlers[io_handler.fd]
        self._do_cleanup()
        if debug: print "DEREGISTER", io_handler.fd, io_handler
    
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
    global signal_manager
    if not hasattr(io_managers, 'manager'):
        io_managers.manager = IOManager()
        if isinstance(threading.current_thread(), threading._MainThread):
            signal_manager = SignalManager()
    return io_managers.manager

signal_manager = None
def get_signal_manager():
    global signal_manager
    get_io_manager()
    return signal_manager


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

ALL_SIGNALS = set(getattr(signal, name) for name in dir(signal) if name.startswith("SIG") and '_' not in name)

class SignalManager(IOHandler):
    events = select.POLLIN
    
    def __init__(self, mask = ALL_SIGNALS):
        self.mask = mask
        IOHandler.__init__(self, signalfd.signalfd(-1, mask, signalfd.SFD_CLOEXEC))
        signalfd.sigprocmask(signalfd.SIG_BLOCK, mask)
        self.signal_handlers = {}

    def filter_to_key(self, flt):
        key = flt.items()
        key.sort(lambda item: item[0])
        return tuple(key)

    def register(self, signal_handler):
        flt = signal_handler.filter.items()

        key = self.filter_to_key(signal_handler.filter)
        self.signal_handlers[key] = signal_handler
        if debug: print "REGISTER", key, signal_handler

    def deregister(self, signal_handler):
        key = self.filter_to_key(signal_handler.filter)
        del self.signal_handlers[key]
        if debug: print "DEREGISTER", key, signal_handler

    def match_signal(self, siginfo, flt):
        for key, value in flt.iteritems():
            if getattr(siginfo, key) != value:
                return False
        return True

    def handle_event(self, event):
        siginfo = signalfd.read_siginfo(self.fd)
        res = False
        for key, signal_handler in self.signal_handlers.items():
            if self.match_signal(siginfo, signal_handler.filter):
                res = res or signal_handler.handle_event(siginfo)
        return res

class SignalHandler(object):
    def __init__(self, filter):
        self.filter = filter
        get_signal_manager().register(self)
    def handle_event(self, event):
        pass
    def destroy(self):
        get_signal_manager().deregister(self)
        if debug: print "CLOSE DESTROY", self.filter, self
    
class SignalIteratorHandler(SignalHandler):
    def __init__(self, filter):
        SignalHandler.__init__(self, filter)
        self.buffer = []
    def handle_event(self, event):
        self.buffer[0:0] = [event]

    def __iter__(self):
        return self

    def next(self):
        while not self.buffer:
            get_io_manager().handle_io()
        return self.buffer.pop()

CLD_EXITED = 1

class ProcessSignalHandler(SignalHandler):
    def __init__(self, pid):
        self.is_running = True
        self.pid = pid
        SignalHandler.__init__(self, {"ssi_pid": pid})

    def handle_event(self, event):
        print "Event"
        for key in dir(event):
            print "    ", key, getattr(event, key)
        if event.ssi_code == CLD_EXITED:
            print "    EXIT"
            os.waitpid(self.pid, 0)
            print "    EXIT DONE"
            self.is_running = False
            self.destroy()
            return True

# Generate an io-manager, hopefully for the main thread
# If we don't have one in the main thread, signal handling won't work.
get_io_manager()
