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
from . import copy

try:
    MAXFD = os.sysconf("SC_OPEN_MAX")
except:
    MAXFD = 256

class SpecialRedirect(object):
    class __metaclass__(type):
        def __str__(self):
            return repr(self)
        def __repr__(self):
            return self.__name__
    def __init__(self, **kws):
        object.__setattr__(self, "kws", kws)
    def __getattr__(self, name):
        return self.kws[name]
    def __setattr__(self, name):
        self.kws[name] = value
    def __str__(self):
        return repr(self)
    def __repr__(self):
        return "%s(%s)" % (
            type(self),
            ",".join(("%s=%s" % (name, value)
                      for name, value in self.kws.items())))

class PIPE(SpecialRedirect): pass
class TMP(SpecialRedirect): pass
class STRING(TMP): pass

def flags_to_string(flags):
    return ",".join([name[2:]
                     for name in dir(os)
                     if name.startswith("O_") and flags & getattr(os, name)])

class Redirect(object):
    fd_names = {"stdin": 0, "stdout": 1, "stderr": 2}
    names_to_fd = {value: key for key, value in fd_names.items()}
    fd_flags = {
        0: os.O_RDONLY,
        1: os.O_WRONLY | os.O_CREAT,
        2: os.O_WRONLY | os.O_CREAT
        }
    def __init__(self, fd, source = None, flag = None, mode = 0o777, pipe=None, borrowed=False):
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
        self.borrowed = borrowed
    def __deepcopy__(self, memo = {}):
        return type(self)(self.fd, copy.deepcopy(self.source), self.flag, self.mode, self.pipe, self.borrowed)

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
        if isinstance(self.source, type) and issubclass(self.source, PIPE):
            rfd, wfd = pipe.pipe_cloexec()
            if self.flag & os.O_WRONLY:
                sourcefd, pipefd = wfd, rfd
            else:
                pipefd, sourcefd = wfd, rfd
            return type(self)(self.fd, sourcefd, self.flag, self.mode, pipefd)
        elif isinstance(self.source, type) and issubclass(self.source, (TMP, STRING)):
            if not (self.flag & os.O_WRONLY):
                raise Exception("Invalid flag for %s redirect - must be O_WRONLY" % self.source)
            sourcefd, pipefd = tempfile.mkstemp()
            return type(self)(self.fd, sourcefd, self.flag, self.mode, self.source(path=pipefd))
        else:
            return self

    def __repr__(self):
        flagmode = []
        if self.flag != self.fd_flags.get(self.fd, None):
            flagmode.append(flags_to_string(self.flag))
        if self.mode != 0o777:
            flagmode.append("m=%s" % self.mode)
        if flagmode:
            flagmode = "[" + ",".join(flagmode) + "]"
        else:
            flagmode = ""
        if self.flag & os.O_WRONLY:
            arrow = "-%s->" % flagmode
        else:
            arrow = "<-%s-" % flagmode
        items = [str(self.fd), arrow, str(self.source)]
        if self.pipe is not None:
            items.append("pipe=%s" % self.pipe)
        return " ".join(items)

class Redirects(object):
    def __init__(self, *redirects, **kw):
        self.redirects = {}
        for redirect in redirects:
            self.register(redirect)
    def register(self, redirect):
        if isinstance(redirect, Redirects):
            for item in redirect.redirects.values():
                self.register(item)
        else:
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
        self.register(other)
        return self
    def find_free_fd(self):
        return max([redirect.fd
                    for redirect in self.redirects.values()]
                   + [redirect.source
                      for redirect in self.redirects.values()
                      if isinstance(redirect.source, int)]
                   + [2]) + 1
    def make_pipes(self):
        return type(self)(*[redirect.make_pipe()
                            for redirect in self.redirects.values()])
    def move_existing_fds(self):
        new_fd = self.find_free_fd()
        redirects = []
        for redirect in self.redirects.values():
            redirects.append(redirect.move(new_fd))
            new_fd += 1
        log.log("After move: %s" % repr(Redirects(*redirects)), "fd")
        return redirects
    def perform(self):
        try:
            for redirect in self.move_existing_fds():
                redirect.perform()
            self.close_other_fds()
        except Exception as e:
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
        for redirect in self.redirects.values():
            redirect.close_source_fd()
    def __getattr__(self, name):
        try:
            return self.redirects[Redirect.fd_names[name]]
        except KeyError:
            raise AttributeError(name)
    @classmethod
    def _coerce(cls, thing, direction):
        if thing is None:
            thing = "/dev/null"
        if isinstance(thing, (str, unicode)):
            thing = Redirect(direction, thing)
        if isinstance(thing, Redirect):
            thing = Redirects(thing)
        if not isinstance(thing, Redirects):
            raise ValueError(type(thing))
        return thing
    def __repr__(self):
        redirects = sorted(self.redirects.values(), key = lambda a: a.fd)
        return ", ".join(repr(redirect) for redirect in redirects)
