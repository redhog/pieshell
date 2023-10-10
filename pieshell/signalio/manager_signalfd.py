import os
import select
import signal
import errno
from .. import log
import signalfd
import asyncio

from ..iterio import IOHandler
from . import signalutils

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
