import os
import sys

debug = {
    "all": False,
    "fd": False,
    "cmd": True,
    "ioreg": True,
    "ioevent": True,
    "io": False,
    "signalreg": False,
    "signal": False
    }

logfd = 1023
os.dup2(sys.stdout.fileno(), logfd)
def log(msg, category="misc"):
    if not debug.get(category, False) and not debug.get("all", False): return
    os.write(logfd, "%s: %s\n" % (os.getpid(), msg))
