import os
import fcntl
import types
import sys
import tempfile
import uuid
import code
import threading

from . import pipe
from . import log

try:
    MAXFD = os.sysconf("SC_OPEN_MAX")
except:
    MAXFD = 256

class PIPE(object): pass

class Redirect(object):
    fd_names = {"stdin": 0, "stdout": 1, "stderr": 2}
    fd_flags = {
        0: os.O_RDONLY,
        1: os.O_WRONLY | os.O_CREAT,
        2: os.O_WRONLY | os.O_CREAT
        }
    def __init__(self, fd, source = None, flag = None, mode = 0777, pipe=None):
        if isinstance(fd, Redirect):
            fd, source, flag, mode, pipe = fd.fd, fd.source, fd.flag, fd.mode, fd.pipe
        if not isinstance(fd, int):
            fd = self.fd_names[fd]
        if flag is None:
            flag = self.fd_flags[fd]
        self.fd = fd
        self.source = source
        self.flag = flag
        self.mode = mode
        self.pipe = pipe
    def open(self):
        source = self.source
        if not isinstance(source, int):
            log.log("Opening %s in %s for %s" % (self.source, self.flag, self.fd), "fd")
            source = os.open(source, self.flag, self.mode)
            log.log("Done opening %s in %s for %s" % (self.source, self.flag, self.fd), "fd")
        return source
    def close_source_fd(self):
        # FIXME: Only close source fds that come from pipes instead of this hack...
        if isinstance(self.source, int) and self.source > 2:
            os.close(self.source)
    def perform(self):
        source = self.open()
        assert source != self.fd
        log.log("perform dup2(%s, %s)" % (source, self.fd), "fd")
        os.dup2(source, self.fd)
        log.log("perform close(%s)" % (source), "fd")
        os.close(source)
    def move(self, fd):
        self = Redirect(self)
        if isinstance(self.source, int):
            log.log("move dup2(%s, %s)" % (self.source, fd), "fd")
            os.dup2(self.source, fd)
            log.log("move close(%s)" % (self.source), "fd")
            os.close(self.source)
            self.source = fd
        return self
    def make_pipe(self):
        if self.source is not PIPE: return self
        rfd, wfd = pipe.pipe_cloexec()
        if self.flag & os.O_RDONLY:
            pipefd, sourcefd = wfd, rfd
        else:
            sourcefd, pipefd = wfd, rfd
        return type(self)(self.fd, sourcefd, self.flag, self.mode, pipefd)
    def __repr__(self):
        flagmode = []
        if self.flag not in (os.O_RDONLY, os.O_WRONLY):
            flagmode.append("f=%s" % self.flag)
        if self.mode != 0777:
            flagmode.append("m=%s" % self.mode)
        if flagmode:
            flagmode = "[" + ",".join(flagmode) + "]"
        else:
            flagmode = ""
        if self.flag & os.O_RDONLY:
            arrow = "<-%s-" % flagmode
        else:
            arrow = "-%s->" % flagmode
        items = [str(self.fd), arrow, str(self.source)]
        if self.pipe is not None:
            items.append("pipe=%s" % self.pipe)
        return " ".join(items)

class Redirects(object):
    def __init__(self, *redirects, **kw):
        self.redirects = {}
        if redirects and isinstance(redirects[0], Redirects):
            for redirect in redirects[0].redirects.values():
                self.register(Redirect(redirect))
        else:
            if kw.get("defaults", True):
                self.redirect(0, 0)
                self.redirect(1, 1)
                self.redirect(2, 2)
            for redirect in redirects:
                self.register(redirect)
    def register(self, redirect):
        if not isinstance(redirect, Redirect):
            redirect = Redirect(redirect)
        if redirect.source is None:
            del self.redirects[redirect.fd]
        else:
            self.redirects[redirect.fd] = redirect
        return self
    def redirect(self, *arg, **kw):
        self.register(Redirect(*arg, **kw))
        return self
    def merge(self, other):
        self = Redirects(self)
        for redirect in other.redirects.itervalues():
            self.register(redirect)
        return self
    def find_free_fd(self):
        return max([redirect.fd
                    for redirect in self.redirects.itervalues()]
                   + [redirect.source
                      for redirect in self.redirects.itervalues()
                      if isinstance(redirect.source, int)]
                   + [2]) + 1
    def make_pipes(self):
        return type(self)(*[redirect.make_pipe()
                            for redirect in self.redirects.itervalues()])
    def move_existing_fds(self):
        new_fd = self.find_free_fd()
        redirects = []
        for redirect in self.redirects.itervalues():
            redirects.append(redirect.move(new_fd))
            new_fd += 1
        log.log("After move: %s" % repr(Redirects(*redirects, defaults=False)), "fd")
        return redirects
    def perform(self):
        try:
            for redirect in self.move_existing_fds():
                redirect.perform()
            self.close_other_fds()
        except Exception, e:
            import traceback
            log.log(e, "fd")
            log.log(traceback.format_exc(), "fd")
    def close_other_fds(self):
        # FIXME: Use os.closerange if available
        for i in xrange(0, MAXFD):
            if i in self.redirects: continue
            if i == log.logfd: continue
            try:
                os.close(i)
            except:
                pass
    def close_source_fds(self):
        for redirect in self.redirects.itervalues():
            redirect.close_source_fd()
    def __getattr__(self, name):
        return self.redirects[Redirect.fd_names[name]]
    def __repr__(self):
        redirects = self.redirects.values()
        redirects.sort(lambda a, b: cmp(a.fd, b.fd))
        return ", ".join(repr(redirect) for redirect in redirects)
