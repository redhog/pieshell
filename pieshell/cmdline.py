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

debug = False

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
            source = os.open(source, self.flag, self.mode)
        return source
    def close_source_fd(self):
        # FIXME: Only close source fds that come from pipes instead of this hack...
        if isinstance(self.source, int) and self.source > 2:
            os.close(self.source)
    def perform(self):
        source = self.open()
        if source != self.fd:
            os.dup2(source, self.fd)
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
    def __init__(self, *redirects):
        self.redirects = {}
        if redirects and isinstance(redirects[0], Redirects):
            for redirect in redirects[0].redirects.values():
                self.register(Redirect(redirect))
        else:
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
    def make_pipes(self):
        return type(self)(*[redirect.make_pipe()
                            for redirect in self.redirects.itervalues()])
    def perform(self):
        for redirect in self.redirects.itervalues():
            redirect.perform()
        self.close_other_fds()
    def close_other_fds(self):
        # FIXME: Use os.closerange if available
        for i in xrange(0, MAXFD):
            if i in self.redirects: continue
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

    def _run(self, redirects):
        redirects = redirects.make_pipes()
        if debug: print "Running %s with %s" % (Pipeline.repr(self), repr(redirects))

        named_pipes = {}
        def handle_named_pipe(thing):
            if isinstance(thing, Pipeline):
                direction = "w"
            elif isinstance(thing, types.FunctionType):
                thing = Function(thing)
                direction = "r"
            elif hasattr(thing, "__iter__") or hasattr(thing, "next"):
                thing = Function(self.env, thing)
                direction = "w"
            else:
                return thing
            name = os.path.join(tempfile.gettempdir(), str(uuid.uuid4()))
            os.mkfifo(name)

            named_pipes[name] = (direction, thing)
            
            def clean_named_pipe():
                os.unlink(name)

            iterio.IOHandlers.register_cleanup(clean_named_pipe)

            return name

        args = [self.name]
        if self.arg:
            args += [handle_named_pipe(item) for item in self.arg]
        if self.kw:
            args += ["--%s=%s" % (name, handle_named_pipe(value))
                     for (name, value) in self.kw.iteritems()]

        pid = os.fork()
        if pid == 0:
            self._child(redirects, args)

        class Proc(object):
            def __init__(self, pid):
                self.pid = pid
            def wait(self):
                os.waitpid(self.pid, 0)
        res = Proc(pid)

        redirects.close_source_fds()

        for name, (direction, thing) in named_pipes.iteritems():
            if direction == 'w':
                thing._run([Redirect("stdout", name)])
            else:
                thing._run([Redirect("stdin", name)])

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

    def _run(self, redirects):
        redirects = redirects.make_pipes()
        if debug: print "Running %s with %s" % (Pipeline.repr(self), repr(redirects))

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
    def _run(self, redirects):
        if debug: print "Running %s with %s" % (Pipeline.repr(self), repr(redirects))
        src = self.src._run(Redirects(redirects).redirect("stdout", PIPE))
        dst = self.dst._run(Redirects(redirects).redirect("stdin", src[-1].redirects.stdout.pipe))
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
    def _run(self, *arg, **kw):
        if debug: print "Running %s with %s=%s, %s, %s" % (Pipeline.repr(self), self.filedescr, Pipeline.repr(arg), Pipeline.repr(kw))
        if self.filedescr == 'stdin':
            stdin = fd = os.open(self.file, os.O_RDONLY)
        elif self.filedescr == 'stdout':
            stdout = fd = os.open(self.file, os.O_WRONLY | os.O_CREAT)
        else:
            assert False
        return self.pipeline._run(stdin=stdin, stdout=stdout, stderr=stderr, **kw)

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

