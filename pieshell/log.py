import os
import sys
import logging
import resource

class PieshellLogFDHandler(logging.StreamHandler):
    def emit(self, record):
        msg = self.format(record)
        os.write(logfd, ("%s\n" % (msg,)).encode("utf-8"))

pieshell_log_fd_handler = PieshellLogFDHandler()
pieshell_log_fd_handler.setFormatter(logging.Formatter("%(process)d:" + logging.BASIC_FORMAT))
logging.getLogger().addHandler(pieshell_log_fd_handler)

logging.getLogger("error").setLevel(logging.INFO)
logging.getLogger("io").setLevel(logging.CRITICAL)
logging.getLogger("ioevent").setLevel(logging.CRITICAL)
logging.getLogger("ioreg").setLevel(logging.CRITICAL)
logging.getLogger("fd").setLevel(logging.CRITICAL)
logging.getLogger("cmd").setLevel(logging.CRITICAL)
logging.getLogger("signalreg").setLevel(logging.CRITICAL)
logging.getLogger("signal").setLevel(logging.CRITICAL)
logging.getLogger("test").setLevel(logging.CRITICAL)

outfd = None
if hasattr(sys.stdout, "fileno"):
    outfd = sys.stdout.fileno()
elif hasattr(sys.stderr, "fileno"):
    outfd = sys.stderr.fileno()
else:
    outfd = 1
logfd = resource.getrlimit(resource.RLIMIT_NOFILE)[0] - 1
os.dup2(outfd, logfd)
def log(msg, category="misc"):
    logging.getLogger(category).error(msg)
