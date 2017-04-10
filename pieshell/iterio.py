import os
import fcntl
import select
import threading
import signalfd
import signal
import errno
import log

class RecursiveEvent(Exception): pass

def events_to_str(events):
    return ",".join([name for name in dir(select)
                     if (    name.startswith("POLL")
                         and events & getattr(select, name) != 0)])


class IOManager(object):
    def __init__(self):
        self.io_handlers = {}
        self.poll = select.poll()

    def register(self, io_handler):
        self.enable(io_handler)
        if io_handler.fd not in self.io_handlers:
            self.io_handlers[io_handler.fd] = []
        self.io_handlers[io_handler.fd].append(io_handler)
        log.log("REGISTER %s, %s, %s" % (io_handler.fd, events_to_str(io_handler.events), io_handler), "ioreg")

    def enable(self, io_handler):
        self.poll.register(io_handler.fd, io_handler.events)

    def disable(self, io_handler):
        self.poll.unregister(io_handler.fd)

    def deregister(self, io_handler):
        self.disable(io_handler)
        self.io_handlers[io_handler.fd] = [item for item in self.io_handlers[io_handler.fd]
                                           if item is not io_handler]
        if not self.io_handlers[io_handler.fd]:
            del self.io_handlers[io_handler.fd]
        log.log("DEREGISTER %s, %s" % (io_handler.fd, io_handler), "ioreg")
    
    def handle_io(self, timeout = None):
        while self.io_handlers:
            try:
                events = self.poll.poll(timeout)
            except IOError as e:
                if e.errno == errno.EINTR:
                    continue
                raise

            log.log("EVENTS %s" % (", ".join("%s:%s" % (fd, events_to_str(event))
                                             for (fd, event) in events),), "ioevent")
            assert timeout is not None or events
            done = False
            recursive = False
            for fd, event in events:
                # Check if the fd is still registered. If we have
                # multiple events for the same fd, this might not be
                # the case for the second event...
                if fd in self.io_handlers:
                    for io_handler in self.io_handlers[fd]:
                        try:
                            event_done = io_handler.handle_event(event)
                            done = done or event_done
                        except RecursiveEvent:
                            recursive = True
            if done:
                return
            if recursive:
                raise RecursiveEvent
            if timeout is not None:
                return

    def __repr__(self):
        return "IOManager(%s)" % (", ".join(repr(iohandler) for iohandler in self.io_handlers.itervalues()),)

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
    def __init__(self, fd, borrowed = False, usage = None):
        self.fd = fd
        self.borrowed = borrowed
        self.enabled = True
        self.usage = usage
        get_io_manager().register(self)
    def handle_event(self, event):
        pass
    def destroy(self):
        get_io_manager().deregister(self)
        if self.borrowed:
            log.log("HAND BACK %s, %s" % (self.fd, self), "ioreg")
        else:
            log.log("CLOSE DESTROY %s, %s" % (self.fd, self), "ioreg")
            os.close(self.fd)
    def enable(self):
        self.enabled = True
        get_io_manager().enable(self)
    def disable(self):
        self.enabled = False
        get_io_manager().enable(self)
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
        self.is_running = True
        self.recursion = False
        self.exception = None
        IOHandler.__init__(self, fd, borrowed, usage)

    def destroy(self):
        self.is_running = False
        IOHandler.destroy(self)

    def handle_event(self, event):
        if self.recursion:
            raise RecursiveEvent
        self.recursion = True
        try:
            return self.handle_event_non_recursive(event)
        finally:
            self.recursion = False

    def handle_event_non_recursive(self, event):
        try:
            val = self.iter.next()
            if val is not None:
                os.write(self.fd, val)
        except StopIteration:
            self.destroy()
            return True
        except Exception, e:
            self.exception = e
            self.destroy()
            return True

    def _repr_args(self):
        args = IOHandler._repr_args(self)
        if not self.is_running:
            args.append("stopped")
        if self.recursion:
            args.append("recursion")
        return args


class LineOutputHandler(OutputHandler):
    def handle_event_non_recursive(self, event):
        try:
            val = self.iter.next()
            if val is not None:
                os.write(self.fd, val + "\n")
            log.log("WRITE %s, %s" % (self.fd, repr(val)), "io")
        except StopIteration:
            log.log("STOP ITERATION %s" % self.fd, "ioevent")
            self.destroy()
            return True
        except Exception, e:
            self.exception = e
            self.destroy()
            return True

class InputHandler(IOHandler):
    events = select.POLLIN | select.POLLHUP | select.POLLERR
    
    def __init__(self, fd, borrowed = False, usage = None):
        self.buffer = None
        self.eof = False
        IOHandler.__init__(self, fd, borrowed, usage)

    def handle_event(self, event):
        if self.buffer is None:
            self.buffer = os.read(self.fd, 1024)
            if not self.buffer:
                self.eof = True
                self.destroy()
        return True

    def __iter__(self):
        return self

    def next(self):
        while self.buffer is None:
            if self.eof:
                raise StopIteration
            try:
                get_io_manager().handle_io()
            except RecursiveEvent:
                return None
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
    def __init__(self, fd, borrowed = False, usage = None):
        InputHandler.__init__(self, fd, borrowed, usage)
        self.buffer = ""

    def handle_event(self, event):
        if '\n' not in self.buffer:
            read_data = os.read(self.fd, 1024)
            self.buffer += read_data
            if not read_data:
                self.eof = True
                self.destroy()
        return True

    def next(self):
        while not self.eof and '\n' not in self.buffer:
            try:
                get_io_manager().handle_io()
            except RecursiveEvent:
                return None
        if not self.buffer:
            assert self.eof
            raise StopIteration
        if '\n' not in self.buffer:
            self.buffer += '\n' # No newline at end of file...
        ret, self.buffer = self.buffer.split("\n", 1)
        return ret

ALL_SIGNALS = set(getattr(signal, name) for name in dir(signal) if name.startswith("SIG") and '_' not in name)

class SignalManager(IOHandler):
    events = select.POLLIN
    
    def __init__(self, mask = [signal.SIGCHLD]):
        self.mask = mask
        self.signal_handlers = {}
        IOHandler.__init__(self, signalfd.signalfd(-1, mask, signalfd.SFD_CLOEXEC | signalfd.SFD_NONBLOCK), usage="SignalManager")
        signalfd.sigprocmask(signalfd.SIG_BLOCK, mask)

    def filter_to_key(self, flt):
        key = flt.items()
        key.sort(lambda item: item[0])
        return tuple(key)

    def register(self, signal_handler):
        flt = signal_handler.filter.items()

        key = self.filter_to_key(signal_handler.filter)
        self.signal_handlers[key] = signal_handler
        log.log("REGISTER %s, %s" % (key, signal_handler), "signalreg")

    def deregister(self, signal_handler):
        key = self.filter_to_key(signal_handler.filter)
        del self.signal_handlers[key]
        log.log("DEREGISTER %s, %s" % (key, signal_handler), "signalreg")

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
                if log.debug["signal"]:
                    log.log("Signal", "signal")
                    for key, val in siginfo_to_names(siginfo).iteritems():
                        log.log("    %s: %s" % (key, val), "signal")

                for key, signal_handler in self.signal_handlers.items():
                    if self.match_signal(siginfo, signal_handler.filter):
                        sighandlerres = signal_handler.handle_event(siginfo)
                        res = res or sighandlerres
        return res

    def _repr_args(self):
        args = IOHandler._repr_args(self)
        args.append(repr(self.mask))
        args.append(repr(self.signal_handlers))
        return args

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
    return siginfo

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
        log.log("CLOSE DESTROY %s, %s" % (self.filter, self), "signalreg")
    
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
        log.log("Process event %s" % self.pid, "signal")
        self.last_event = event
        if event["ssi_code"] == CLD_EXITED:
            log.log("EXIT %s" % self.pid, "signal")
            self.is_running = False
            self.destroy()
            return True

# Generate an io-manager, hopefully for the main thread
# If we don't have one in the main thread, signal handling won't work.
get_io_manager()
