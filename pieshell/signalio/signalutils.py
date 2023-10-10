import os
import signal
import errno

ALL_SIGNALS = set(getattr(signal, name) for name in dir(signal) if name.startswith("SIG") and '_' not in name)

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
