import os
import select
import signal
import errno
from .. import log
import asyncio
from . import signalutils

class SignalManager(object):
    def __init__(self, mask = [signal.SIGCHLD, signal.SIGTSTP]):
        self.mask = mask
        self.signal_handlers = {}
        for signo in mask:
            asyncio.get_event_loop().add_signal_handler(signo, lambda: self.handle_event(signo))
        
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

    def handle_event(self, signo):
        siginfo = {
            "ssi_signo": signo, # Signal number
            "ssi_errno": 0,     # Error number (unused)
            "ssi_code": 0,      # Signal code
            "ssi_pid": 0,       # PID of sender
            "ssi_uid": 0,       # Real UID of sender
            "ssi_fd": 0,        # File descriptor (SIGIO)
            "ssi_tid": 0,       # Kernel timer ID (POSIX timers)
            "ssi_band": 0,      # Band event (SIGIO)
            "ssi_overrun": 0,   # POSIX timer overrun count
            "ssi_trapno": 0,    # Trap number that caused signal
            "ssi_status": 0,    # Exit status or signal (SIGCHLD)
            "ssi_int": 0,       # Integer sent by sigqueue(3)
            "ssi_ptr": 0,       # Pointer sent by sigqueue(3)
            "ssi_utime": 0,     # User CPU time consumed (SIGCHLD)
            "ssi_stime": 0,     # System CPU time consumed (SIGCHLD)
            "ssi_addr": 0,      # Address that generated signal (for hardware-generated signals)
        }
        
        # Handle multiple simultaneously delivered SIGCHLD which
        # gets squashed into just one delivered signal event by
        # Linux...
        siginfos = [siginfo]
        if siginfo["ssi_signo"] == signal.SIGCHLD or siginfo["ssi_signo"] == signal.SIGTSTP:
            siginfos = signalutils.get_sigchlds()

        for siginfo in siginfos:
            class SignalFormatter(object):
                def __init__(self, siginfo):
                    self.siginfo = siginfo
                def __str__(self):
                    return "Signal\n%s" % ("".join("    %s: %s\n" % (key, val)
                                                   for key, val in signalutils.siginfo_to_names(siginfo).items()),)
            log.log(SignalFormatter(siginfo), "signal")

            for key, signal_handler in list(self.signal_handlers.items()):
                if self.match_signal(siginfo, signal_handler.filter):
                    signal_handler.handle_event(siginfo)

signal_manager = None
def get_signal_manager():
    global signal_manager
    if signal_manager is None:
        signal_manager = SignalManager()
    return signal_manager
