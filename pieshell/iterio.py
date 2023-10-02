import os
import select
import signal
import errno
from . import log
import signalfd
import asyncio

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
        self.enable()
    def handle_event(self, event):
        pass
    def destroy(self):
        if self.enabled:
            self.disable()
        if self.borrowed:
            log.log("HAND BACK %s, %s" % (self.fd, self), "ioreg")
        else:
            log.log("CLOSE DESTROY %s, %s" % (self.fd, self), "ioreg")
            os.close(self.fd)
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
        self.is_running = True
        self.exception = None
        IOHandler.__init__(self, fd, borrowed, usage)

    def destroy(self):
        self.is_running = False
        IOHandler.destroy(self)

    def handle_event(self, event):
        try:
            val = next(self.iter)
            if val is not None:
                os.write(self.fd, val)
        except StopIteration:
            self.destroy()
            return True
        except Exception as e:
            self.exception = e
            self.destroy()
            return True

    def _repr_args(self):
        args = IOHandler._repr_args(self)
        if not self.is_running:
            args.append("stopped")
        return args


class LineOutputHandler(OutputHandler):
    def handle_event(self, event):
        try:
            val = next(self.iter)
            if val is not None:
                os.write(self.fd, val + b"\n")
            log.log("WRITE %s, %s" % (self.fd, repr(val)), "io")
        except StopIteration:
            log.log("STOP ITERATION %s" % self.fd, "ioevent")
            self.destroy()
            return True
        except Exception as e:
            self.exception = e
            self.destroy()
            return True

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

    async def __aiter__(self):
        return self
    
    async def __anext__(self):
        if self.buffer is None:
            if self.eof:
                if self.at_eof: self.at_eof()
                raise StopAsyncIteration
            self.future = asyncio.get_event_loop().create_future()
            await self.future
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

    async def __aiter__(self):
        return self
    
    async def __anext__(self):
        while not self.eof and b'\n' not in self.buffer:
            self.future = asyncio.get_event_loop().create_future()
            await self.future
        if not self.buffer:
            assert self.eof
            if self.at_eof: self.at_eof()
            raise StopAsyncIteration
        if b'\n' not in self.buffer:
            self.buffer += b'\n' # No newline at end of file...
        ret, self.buffer = self.buffer.split(b"\n", 1)
        return ret.decode("utf-8")

ALL_SIGNALS = set(getattr(signal, name) for name in dir(signal) if name.startswith("SIG") and '_' not in name)

class SignalManager(IOHandler):
    events = select.POLLIN
    
    def __init__(self, mask = [signal.SIGCHLD, signal.SIGTSTP]):
        self.mask = mask
        self.signal_handlers = {}
        IOHandler.__init__(self, signalfd.signalfd(-1, mask, signalfd.SFD_CLOEXEC | signalfd.SFD_NONBLOCK), usage="SignalManager")
        signalfd.sigprocmask(signalfd.SIG_BLOCK, mask)

    def filter_to_key(self, flt):
        key = sorted(flt.items(), key=lambda item: item[0])
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
        for key, value in flt.items():
            if siginfo[key] != value:
                return False
        return True

    def handle_event(self, event):
        while True:
            try:
                siginfo = signalfd.read_siginfo(self.fd)
            except (OSError, IOError) as e:
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
                class SignalFormatter(object):
                    def __init__(self, siginfo):
                        self.siginfo = siginfo
                    def __str__(self):
                        return "Signal\n%s" % ("".join("    %s: %s\n" % (key, val)
                                                       for key, val in siginfo_to_names(siginfo).items()),)
                log.log(SignalFormatter(siginfo), "signal")

                for key, signal_handler in list(self.signal_handlers.items()):
                    if self.match_signal(siginfo, signal_handler.filter):
                        signal_handler.handle_event(siginfo)

    def _repr_args(self):
        args = IOHandler._repr_args(self)
        args.append(repr(self.mask))
        args.append(repr(self.signal_handlers))
        return args

signal_manager = None
def get_signal_manager():
    global signal_manager
    if signal_manager is None:
        signal_manager = SignalManager()
    return signal_manager

CLD_EXITED = 1    # Child has exited.
CLD_KILLED = 2    # Child was killed.
CLD_DUMPED = 3    # Child terminated abnormally.
CLD_TRAPPED = 4   # Traced child has trapped.
CLD_STOPPED = 5   # Child has stopped.
CLD_CONTINUED = 6 # Stopped child has continued.

signals_by_value = {
    value: name
    for name, value in ((name, getattr(signal, name)) for name in dir(signal))
    if isinstance(value, int)                    
}

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
            val = signals_by_value.get(val, val)
        siginfo[key] = val
    return siginfo

def get_sigchlds():
    try:
        while True:
            (pid, status) = os.waitpid(-1, os.WUNTRACED | os.WCONTINUED | os.WNOHANG)
            if pid == 0:
                return

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
        return

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
