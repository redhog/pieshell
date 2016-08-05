import os
import fcntl
import select
import threading
import signalfd
import signal
import errno

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
        IOHandler.__init__(self, signalfd.signalfd(-1, mask, signalfd.SFD_CLOEXEC | signalfd.SFD_NONBLOCK))
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
            if siginfo[key] != value:
                return False
        return True

    def handle_event(self, event):
        res = False
        while True:
            try:
                siginfo = signalfd.read_siginfo(self.fd)
            except (OSError, IOError), e:
                if e.errno == errno.EAGAIN:
                    break
                raise

            siginfo = {name: getattr(siginfo, name) for name in dir(siginfo)}

            # Handle multiple simultaneously delivered SIGCHLD which
            # gets squashed into just one delivered signal event by
            # Linux...
            siginfos = [siginfo]
            if siginfo["ssi_signo"] == signal.SIGCHLD:
                siginfos = get_sigchlds()

            for siginfo in siginfos:
                if debug:
                    print "Signal"
                    for key, val in siginfo_to_names(siginfo).iteritems():
                        print "    ", key, val

                for key, signal_handler in self.signal_handlers.items():
                    if self.match_signal(siginfo, signal_handler.filter):
                        sighandlerres = signal_handler.handle_event(siginfo)
                        res = res or sighandlerres
        return res

CLD_EXITED = 1    # Child has exited.
CLD_KILLED = 2    # Child was killed.
CLD_DUMPED = 3    # Child terminated abnormally.
CLD_TRAPPED = 4   # Traced child has trapped.
CLD_STOPPED = 5   # Child has stopped.
CLD_CONTINUED = 6 # Stopped child has continued.

def siginfo_to_names(siginfo):
    siginfo = dict(siginfo)
    for key in siginfo:
        val = siginfo[key]
        if key == "ssi_code":
            val = {
                1: "CLD_EXITED",
                2: "CLD_KILLED",
                3: "CLD_DUMPED",
                4: "CLD_TRAPPED",
                5: "CLD_STOPPED",
                6: "CLD_CONTINUED"}.get(val, val)
        if (   key == "ssi_signo"
            or (key == "ssi_status"
                and siginfo["ssi_code"] != CLD_EXITED)):
            val = [name for name in dir(signal)
                   if getattr(signal, name) == val][0]
        siginfo[key] = val
            
def get_sigchlds():
    try:
        while True:
            (pid, status) = os.waitpid(-1, os.WUNTRACED | os.WCONTINUED | os.WNOHANG)
            if pid == 0:
                raise StopIteration()

            res = {
                "ssi_signo": 0,   # Signal number
                "ssi_errno": 0,   # Error number (unused)
                "ssi_code": 0,    # Signal code
                "ssi_pid": 0,     # PID of sender
                "ssi_uid": 0,     # Real UID of sender
                "ssi_fd": 0,      # File descriptor (SIGIO)
                "ssi_tid": 0,     # Kernel timer ID (POSIX timers)
                "ssi_band": 0,    # Band event (SIGIO)
                "ssi_overrun": 0, # POSIX timer overrun count
                "ssi_trapno": 0,  # Trap number that caused signal
                "ssi_status": 0,  # Exit status or signal (SIGCHLD)
                "ssi_int": 0,     # Integer sent by sigqueue(3)
                "ssi_ptr": 0,     # Pointer sent by sigqueue(3)
                "ssi_utime": 0,   # User CPU time consumed (SIGCHLD)
                "ssi_stime": 0,   # System CPU time consumed (SIGCHLD)
                "ssi_addr": 0,    # Address that generated signal (for hardware-generated signals)
            }

            res["ssi_signo"] = signal.SIGCHLD
            res["ssi_pid"] = pid

            if os.WIFEXITED(status):
                res["ssi_code"] = CLD_EXITED
                res["ssi_status"] = os.WEXITSTATUS(status)
            elif os.WCOREDUMP(status):
                res["ssi_code"] = CLD_DUMPED
                res["ssi_status"] = os.WTERMSIG(status)
            elif os.WIFCONTINUED(status):
                res["ssi_code"] = CLD_CONTINUED
            elif os.WIFSTOPPED(status):
                res["ssi_code"] = CLD_STOPPED
                res["ssi_status"] = os.WSTOPSIG(status)
            elif os.WIFSIGNALED(status):
                res["ssi_code"] = CLD_KILLED
                res["ssi_status"] = os.WTERMSIG(status)

            yield res
    except OSError:
        raise StopIteration()

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

class ProcessSignalHandler(SignalHandler):
    def __init__(self, pid):
        self.last_event = None
        self.is_running = True
        self.pid = pid
        SignalHandler.__init__(self, {"ssi_pid": pid})

    def handle_event(self, event):
        if debug: print "Process event", self.pid
        self.last_event = event
        if event["ssi_code"] == CLD_EXITED:
            if debug: print "EXIT", self.pid
            self.is_running = False
            self.destroy()
            return True

# Generate an io-manager, hopefully for the main thread
# If we don't have one in the main thread, signal handling won't work.
get_io_manager()
