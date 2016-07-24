#! /usr/bin/env python

import os
import fcntl
import types
import iterio
import pipe
import sys
import tempfile
import uuid
import code
import threading

try:
    MAXFD = os.sysconf("SC_OPEN_MAX")
except:
    MAXFD = 256

debug = {
    "all": False,
    "fd": False,
    "cmd": False
    }

logfd = 1023
os.dup2(sys.stdout.fileno(), logfd)
def log(msg, category="misc"):
    if not debug.get(category, False) and not debug.get("all", False): return
    os.write(logfd, "%s: %s\n" % (os.getpid(), msg))

class Environment(object):
    def __init__(self, cwd = None, env = None, interactive = False):
        self.cwd = os.getcwd()
        if cwd is not None:
            self.cd(cwd)
        self.env = env
        self.interactive = interactive
    def cd(self, cwd):
        if not cwd.startswith("/") and not cwd.startswith("~"):
            cwd = os.path.join(self.cwd, cwd)
        cwd = os.path.expanduser(cwd)
        cwd = os.path.abspath(cwd)
        if not os.path.exists(cwd):
            raise IOError("Path does not exist: %s" % cwd)
        self.cwd = cwd
        return self
    def __call__(self, cwd = None, env = None, interactive = None):
        if env is None:
            env = self.env
        if interactive is None:
            interactive = self.interactive
        res = type(self)(cwd = self.cwd, env = env, interactive = interactive)
        if cwd is not None:
            res.cd(cwd)
        return res
    def __getitem__(self, name):
        return self(name)
    def __getattr__(self, name):
        return Command(self, name)
    def __repr__(self):
        if self.interactive:
            return "%s:%s >>> " % (str(id(self))[:3], self.cwd)
        else:
            return "[%s:%s]" % (str(id(self))[:3], self.cwd)

env = Environment()

class RunningPipeline(object):
    def __init__(self, processes):
        self.processes = processes
    def __iter__(self):
        return iterio.LineInputHandler(self.processes[-1].redirects.stdout.pipe)
    def join(self):
        last = self.processes[-1]
        last.wait()

class RunningProcess(object):
    def __init__(self, pid):
        self.pid = pid
    def wait(self):
        os.waitpid(self.pid, 0)


class PIPE(object): pass

class Redirect(object):
    fd_names = {"stdin": 0, "stdout": 1, "stderr": 2}
    fd_flags = {0: os.O_RDONLY, 1: os.O_WRONLY, 2: os.O_WRONLY}
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
            log("Opening %s in %s for %s" % (self.source, self.flag, self.fd), "fd")
            source = os.open(source, self.flag, self.mode)
            log("Done opening %s in %s for %s" % (self.source, self.flag, self.fd), "fd")
        return source
    def close_source_fd(self):
        # FIXME: Only close source fds that come from pipes instead of this hack...
        if isinstance(self.source, int) and self.source > 2:
            os.close(self.source)
    def perform(self):
        source = self.open()
        assert source != self.fd
        log("perform dup2(%s, %s)" % (source, self.fd), "fd")
        os.dup2(source, self.fd)
        log("perform close(%s)" % (source), "fd")
        os.close(source)
    def move(self, fd):
        self = Redirect(self)
        if isinstance(self.source, int):
            log("move dup2(%s, %s)" % (self.source, fd), "fd")
            os.dup2(self.source, fd)
            log("move close(%s)" % (self.source), "fd")
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
        log("After move: %s" % repr(Redirects(*redirects, defaults=False)), "fd")
        return redirects
    def perform(self):
        try:
            for redirect in self.move_existing_fds():
                redirect.perform()
            self.close_other_fds()
        except Exception, e:
            import traceback
            log(e, "fd")
            log(traceback.format_exc(), "fd")
    def close_other_fds(self):
        # FIXME: Use os.closerange if available
        for i in xrange(0, MAXFD):
            if i in self.redirects: continue
            if i == logfd: continue
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

class Pipeline(object):
    interactive_state = threading.local()
    def __init__(self, env):
        self.env = env
    def _coerce(self, thing):
        if isinstance(thing, Pipeline):
            return thing
        elif isinstance(thing, types.FunctionType) or hasattr(thing, "__iter__") or hasattr(thing, "next"):
            return Function(self.env, thing)
        else:
            raise ValueError(type(thing))
    def __ror__(self, other):
        return Pipe(self.env, self._coerce(other), self)
    def __or__(self, other):
        return Pipe(self.env, self, self._coerce(other))
    def __gt__(self, file):
        return CmdRedirect(self.env, self, file, "stdout")
    def __lt__(self, file):
        return CmdRedirect(self.env, self, file, "stdin")
    def __add__(self, other):
        return Group(self.env, self, other)
    def run(self, redirects = []):
        if not isinstance(redirects, Redirects):
            redirects = Redirects(*redirects)
        return RunningPipeline(self._run(redirects))
    def __iter__(self):
        return iter(self.run([Redirect("stdout", PIPE)]))
    def __unicode__(self):
        return "\n".join(iter(self.run([Redirect("stdout", PIPE)])))
    @classmethod
    def repr(cls, obj):
        cls.interactive_state.repr = True
        try:
            return repr(obj)
        finally:
            cls.interactive_state.repr = False
    def __repr__(self):
        if self.env.interactive and not getattr(self.interactive_state, "repr", False):
            pipeline = self.run()
            try:
                iterio.IOHandlers.delay_cleanup()
                try:
                    iterio.IOHandlers.handleIo()
                    pipeline.join()
                finally:
                    iterio.IOHandlers.perform_cleanup()
            except:
                sys.last_traceback = sys.exc_info()[2]
                import pdb
                pdb.pm()
            return ""
        else:
            return self._repr()

class Command(Pipeline):
    def __init__(self, env, name, arg = None, kw = None):
        self.env = env
        self.name = name
        self.arg = arg or []
        self.kw = kw or {}
    def __call__(self, *arg, **kw):
        nkw = dict(self.kw)
        nkw.update(kw)
        return type(self)(self.env, self.name, self.arg + list(arg), nkw)
    def __getattr__(self, name):
        return type(self)(self.env, self.name, self.arg + [name], self.kw)
    def _repr(self):
        args = []
        if self.arg:
            args += [repr(arg) for arg in self.arg]
        if self.kw:
            args += ["%s=%s" % (key, repr(value)) for (key, value) in self.kw.iteritems()]
        return u"%s.%s(%s)" % (self.env, self.name, ', '.join(args))
    def _close_fds(self):
        if hasattr(os, 'closerange'):
            os.closerange(3, MAXFD)
        else:
            for i in xrange(3, MAXFD):
                try:
                    os.close(i)
                except:
                    pass
    def _child(self, redirects, args):
        redirects.perform()
        os.chdir(self.env.cwd)
        os.execvpe(args[0], args, self.env.env)
        os._exit(-1)

    def handle_arg_pipes(self, thing, redirects, indentation):
        if isinstance(thing, Pipeline):
            direction = "stdout"
        elif isinstance(thing, types.FunctionType):
            thing = Function(thing)
            direction = "stdin"
        elif hasattr(thing, "__iter__") or hasattr(thing, "next"):
            thing = Function(self.env, thing)
            direction = "stdout"
        else:
            # Not a named pipe item, just a string
            return thing
      
        arg_pipe = thing._run(Redirects(Redirect(direction, PIPE)), indentation + "  ")

        fd = redirects.find_free_fd()
        redirects.redirect(
            fd,
            getattr(arg_pipe[-1].redirects, direction).pipe,
            {"stdin": os.O_WRONLY, "stdout": os.O_RDONLY}[direction])

        return "/dev/fd/%s" % fd

    def _run(self, redirects, indentation = ""):
        redirects = redirects.make_pipes()
        log(indentation + "Running %s with %s" % (Pipeline.repr(self), repr(redirects)), "cmd")

        args = [self.name]
        if self.arg:
            args += [self.handle_arg_pipes(item, redirects, indentation) for item in self.arg]
        if self.kw:
            args += ["--%s=%s" % (name, self.handle_arg_pipes(value, redirects, indentation))
                     for (name, value) in self.kw.iteritems()]

        log(indentation + "  Command line %s witth %s" % (' '.join(repr(arg) for arg in args), repr(redirects)), "cmd")

        pid = os.fork()
        if pid == 0:
            self._child(redirects, args)
            # If we ever get to here, all is lost...
            sys._exit(-1)

        res = RunningProcess(pid)

        redirects.close_source_fds()

        res.redirects = redirects

        return [res]

class Function(Pipeline):
    def __init__(self, env, function, *arg, **kw):
        self.env = env
        self.function = function
        self.arg = arg
        self.kw = kw

    def _repr(self):
        thing = self.function
        if isinstance(thing, types.FunctionType):
            args = []
            if self.arg:
                args += [repr(arg) for arg in self.arg]
            if self.kw:
                args += ["%s=%s" % (key, repr(value)) for (key, value) in self.kw.iteritems()]
            return u"%s.%s.%s(%s)" % (self.function.__module__, self.function.func_name, ','.join(args))
        else:
            return repr(thing)

    def _run(self, redirects, indentation = ""):
        redirects = redirects.make_pipes()
        log(indentation + "Running %s with %s" % (Pipeline.repr(self), repr(redirects)), "cmd")

        def convert(x):
            if isinstance(x, str):
                return x
            elif isinstance(x, unicode):
                return x.encode("utf-8")
            else:
                return unicode(x).encode("utf-8")

        thing = self.function
        if isinstance(thing, types.FunctionType):
            thing = thing(
                iterio.LineInputHandler(redirects.stdin.open()),
                *self.arg, **self.kw)
        if hasattr(thing, "__iter__"):
            thing = iter(thing)

        res = iterio.LineOutputHandler(
            redirects.stdout.open(),
            (convert(x) for x in thing))

        res.redirects = redirects

        return [res]
        

class Pipe(Pipeline):
    def __init__(self, env, src, dst):
        self.env = env
        self.src = src
        self.dst = dst
    def _repr(self):
        return u"%s | %s" % (repr(self.src), repr(self.dst))
    def _run(self, redirects, indentation = ""):
        log(indentation + "Running %s with %s" % (Pipeline.repr(self), repr(redirects)), "cmd")
        src = self.src._run(Redirects(redirects).redirect("stdout", PIPE), indentation + "  ")
        dst = self.dst._run(Redirects(redirects).redirect("stdin", src[-1].redirects.stdout.pipe), indentation + "  ")
        return src + dst

# class Group(Pipeline):
#     def __init__(self, env, first, second):
#         self.env = env
#         self.first = first
#         self.second = second
#     def thread_main(self, stdin = None, stdout = None, stderr = None, *arg, **kw):
#         for item in [self.first, self.second]:
#             item.run(stdin=stdin, stdout=stdout, stderr=stderr, **kw).join()
#     def _repr(self):
#         return u"%s + %s" % (repr(self.first), repr(self.second))

class CmdRedirect(Pipeline):
    def __init__(self, env, pipeline, file, filedescr):
        self.env = env
        self.pipeline = pipeline
        self.file = file
        self.filedescr = filedescr
    def _repr(self):
        if self.filedescr == 'stdin':
            sep = "<"
        elif self.filedescr == 'stdout':
            sep = ">"
        return u"%s %s %s" % (repr(self.pipeline), sep, self.file)
    def _run(self, redirects, indentation = ""):
        log(indentation + "Running %s with %s and %s=%s" % (Pipeline.repr(self), repr(redirects), self.filedescr, repr(self.file)), "cmd")
        redirects = Redirects(redirects)
        redirects.redirect(self.filedescr, self.file)
        return self.pipeline._run(redirects, indentation + "  ")

class EnvScope(dict):
    def __getitem__(self, name):
        try:
            return dict.__getitem__(self, name)
        except KeyError:
            if name in __builtins__:
                raise
            return getattr(dict.__getitem__(self, 'env'), name)

    def __str__(self):
        return str(dict.__getitem__(self, 'env'))

class InteractiveConsole(object):
    def __enter__(self):
        e = env(interactive=True)
        self.ps1 = getattr(sys, "ps1", None)
        scope = EnvScope(globals(), env = e)
        sys.ps1 = scope
        return code.InteractiveConsole(locals=scope)

    def __exit__(self, *args, **kw):
        sys.ps1 = self.ps1

