import os
import sys

debug = {
    "all": False,
    "error": True,
    "fd": False,
    "cmd": False,
    "ioreg": False,
    "ioevent": False,
    "io": False,
    "signalreg": False,
    "signal": False,
    "test": False
    }

outfd = None
if hasattr(sys.stdout, "fileno"):
    outfd = sys.stdout.fileno()
elif hasattr(sys.stderr, "fileno"):
    outfd = sys.stderr.fileno()
else:
    outfd = 1
logfd = 1023
os.dup2(outfd, logfd)
def log(msg, category="misc"):
    if not debug.get(category, False) and not debug.get("all", False): return
    os.write(logfd, "%s: %s\n" % (os.getpid(), msg))
