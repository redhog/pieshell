#! /usr/bin/env python

import subprocess
import threading
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

class ShellScript(object):
    pass

class Environment(ShellScript):
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
        return iterio.LineInputHandler(self.processes[-1].pipes['stdout'])
    def join(self):
        last = self.processes[-1]
        last.wait()

class Pipeline(ShellScript):
    interactive_state = threading.local()

    def __init__(self, env):
        self.env = env

    def setup_run_pipes(self, stdin = None, stdout = None, stderr = None, *arg, **kw):
        inputs = {'stdin': stdin,
                  'stdout': stdout,
                  'stderr': stderr}
        pipes = {}
        for key in ('stdin', 'stdout', 'stderr'):
            if inputs[key] is subprocess.PIPE:
                r, w = pipe.pipe_cloexec()
                if key == 'stdin':
                    pipes[key], inputs[key] = w, r
                else:
                    inputs[key], pipes[key] = w, r
        return arg, kw, inputs, pipes
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
        return Redirect(self.env, self, file, "stdout")
    def __lt__(self, file):
        return Redirect(self.env, self, file, "stdin")
    def __add__(self, other):
        return Group(self.env, self, other)
    def run(self, stdin = None, stdout = subprocess.PIPE, stderr = None, **kw):
        return RunningPipeline(self._run(stdin = stdin, stdout = stdout, stderr = stderr, **kw))
    def __iter__(self):
        return iter(self.run(stdout=subprocess.PIPE))
    def __unicode__(self):
        return "\n".join(iter(self.run(stdout=subprocess.PIPE)))
    @classmethod
    def repr(cls, obj):
        cls.interactive_state.repr = True
        try:
            return repr(obj)
        finally:
            cls.interactive_state.repr = False
    def __repr__(self):
        if self.env.interactive and not getattr(self.interactive_state, "repr", False):
            pipeline = self.run(stdout=sys.stdout.fileno(), stderr=sys.stderr.fileno())
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
    def _child(self, *args, **kw):
        for key in ("stdin", "stdout", "stderr"):
            fd = kw.get(key, None)
            if fd is not None:
                if not isinstance(fd, int):
                    fd = os.open(fd, {'stdin': os.O_RDONLY,
                                      'stdout': os.O_WRONLY,
                                      'stderr': os.O_WRONLY}[key])
                dst = {"stdin": 0, "stdout": 1, "stderr": 2}[key]
                if fd != dst:
                    os.dup2(fd, dst)
        self._close_fds()

        os.chdir(self.env.cwd)
        os.execvpe(args[0], args, self.env.env)
        os._exit(-1)

    def _run(self, *args, **kw):
        args, kw, inputs, pipes = self.setup_run_pipes(*args, **kw)
        kw.update(inputs)
        print "Running %s with inputs=%s, pipes=%s, %s, %s" % (Pipeline.repr(self), inputs, pipes, Pipeline.repr(args), Pipeline.repr(kw))

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
                print 'REMOVE', name
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
            self._child(*args, **kw)

        class Proc(object):
            def __init__(self, pid):
                self.pid = pid
            def wait(self):
                os.waitpid(self.pid, 0)
        res = Proc(pid)

        for fd in inputs.itervalues():
            if isinstance(fd, int) and fd > 2:
                os.close(fd)

        for name, (direction, thing) in named_pipes.iteritems():
            if direction == 'w':
                thing._run(stdout=name)
            else:
                thing._run(stdin=name)

        res.pipes = pipes
        for fd in pipes.itervalues():
            pass

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

    def _run(self, *arg, **kw):
        arg, kw, inputs, pipes = self.setup_run_pipes(*arg, **kw)
        print "Running %s with inputs=%s, pipes=%s, %s, %s" % (Pipeline.repr(self), inputs, pipes, Pipeline.repr(arg), Pipeline.repr(kw))

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
                iterio.LineInputHandler(inputs['stdin']),
                *self.arg, **self.kw)
        if hasattr(thing, "__iter__"):
            thing = iter(thing)

        res = iterio.LineOutputHandler(
            inputs['stdout'],
            (convert(x) for x in thing))

        res.pipes = pipes

        return [res]
        

class Pipe(Pipeline):
    def __init__(self, env, src, dst):
        self.env = env
        self.src = src
        self.dst = dst
    def _repr(self):
        return u"%s | %s" % (repr(self.src), repr(self.dst))
    def _run(self, stdin = None, stdout = None, stderr = None, *arg, **kw):
        print "Running %s with stdin=%s, stdout=%s, stderr=%s, %s, %s" % (Pipeline.repr(self), stdin, stdout, stderr, Pipeline.repr(arg), Pipeline.repr(kw))
        src = self.src._run(stdin=stdin, stdout=subprocess.PIPE, stderr=stderr, *arg, **kw)
        dst = self.dst._run(stdin=src[-1].pipes['stdout'], stdout=stdout, stderr=stderr, *arg, **kw)
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

class Redirect(Pipeline):
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
        print "Running %s with %s=%s, %s, %s" % (Pipeline.repr(self), self.filedescr, Pipeline.repr(arg), Pipeline.repr(kw))
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

