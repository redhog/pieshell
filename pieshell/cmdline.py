#! /usr/bin/env python

import os
import fcntl
import types
import sys
import tempfile
import uuid
import code
import threading

from . import iterio
from . import redir
from . import log

try:
    MAXFD = os.sysconf("SC_OPEN_MAX")
except:
    MAXFD = 256

class Environment(object):
    """An environment within which a command or pipeline can run. The
    environment consists of a current working directory and a set of
    environment variables and other configuration.

    Commands within the environment can be convienently created using
    the

        env.COMMAND_NAME

    as a short hand for

        Command(env, "COMMAND_NAME")
    """

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

# help() doesn't let you override help on objects, only on classes, so
# make everything a class...
class DescribableObject(type):
    def __new__(cls, *arg, **kw):
        return type.__new__(cls, "", (type,), {})
    def __init__(self, *arg, **kw):
        pass

class Pipeline(DescribableObject):
    """Abstract base class for all pipelines"""

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
        """Pipes the standard out of a pipeline into the standrad in
        of this pipeline."""
        return Pipe(self.env, self._coerce(other), self)
    def __or__(self, other):
        """Pipes the standard out of the pipeline into the standrad in
        of another pipeline."""
        return Pipe(self.env, self, self._coerce(other))
    def __gt__(self, file):
        """Redirects the standard out of the pipeline to a file."""
        return CmdRedirect(self.env, self, file, "stdout")
    def __lt__(self, file):
        """Redirects the standard in of the pipeline from a file."""
        return CmdRedirect(self.env, self, file, "stdin")
    def __add__(self, other):
        return Group(self.env, self, other)
    def run(self, redirects = []):
        """Runs the pipelines with the specified redirects and returns
        a RunningPipeline instance."""
        if not isinstance(redirects, redir.Redirects):
            redirects = redir.Redirects(*redirects)
        return RunningPipeline(self._run(redirects))
    def __iter__(self):
        """Runs the pipeline and iterates over its standrad output lines."""
        return iter(self.run([redir.Redirect("stdout", redir.PIPE)]))
    def __unicode__(self):
        """Runs the pipeline and returns its standrad out output as a string"""
        return "\n".join(iter(self.run([redir.Redirect("stdout", redir.PIPE)])))
    @classmethod
    def repr(cls, obj):
        """Returns a string representation of the pipeline"""
        cls.interactive_state.repr = True
        try:
            return repr(obj)
        finally:
            cls.interactive_state.repr = False
    def __repr__(self):
        """Runs the command if the environment has interactive=True,
        sending the output to standard out. If the environment is
        non-interactive, returns a string representation of the
        pipeline without running it."""

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

    @property
    def __bases__(self):
        return []

    @property
    def __name__(self):
        return Pipeline.repr(self)

    @property
    def __doc__(self):
        return ""

class Command(Pipeline):
    """Runs an external program with the specified arguments.
    Arguments can be sent in either list or dictionary form.
    Dictionary arguments are converted into --key=value. Note that
    this short hand syntax might not work for all programs, as some
    expect "--key value", or even "-key=value" (e.g. find).
    """
    def __init__(self, env, name, arg = None, kw = None):
        self.env = env
        self.name = name
        self.arg = arg or []
        self.kw = kw or {}
    def __call__(self, *arg, **kw):
        """Appends a set of arguments to the argument list

            env.mycommand("input_filename", verbose='3', destination="output")

        is equivalent to

            Command(env, "mycommand", ["input_filename", "--verbose=3", "--destination=output"])
        """
        nkw = dict(self.kw)
        nkw.update(kw)
        return type(self)(self.env, self.name, self.arg + list(arg), nkw)
    def __getattr__(self, name):
        """Append a name to the argument list, such that e.g.

            env.git.status("--help")

        is equivalent to

            env.git("status", "--help")
        """
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
      
        arg_pipe = thing._run(redir.Redirects(redir.Redirect(direction, redir.PIPE)), indentation + "  ")

        fd = redirects.find_free_fd()
        redirects.redirect(
            fd,
            getattr(arg_pipe[-1].redirects, direction).pipe,
            {"stdin": os.O_WRONLY, "stdout": os.O_RDONLY}[direction])

        return "/dev/fd/%s" % fd

    def _run(self, redirects, indentation = ""):
        redirects = redirects.make_pipes()
        log.log(indentation + "Running %s with %s" % (Pipeline.repr(self), repr(redirects)), "cmd")

        args = [self.name]
        if self.arg:
            args += [self.handle_arg_pipes(item, redirects, indentation) for item in self.arg]
        if self.kw:
            args += ["--%s=%s" % (name, self.handle_arg_pipes(value, redirects, indentation))
                     for (name, value) in self.kw.iteritems()]

        log.log(indentation + "  Command line %s witth %s" % (' '.join(repr(arg) for arg in args), repr(redirects)), "cmd")

        pid = os.fork()
        if pid == 0:
            self._child(redirects, args)
            # If we ever get to here, all is lost...
            sys._exit(-1)

        res = RunningProcess(pid)

        redirects.close_source_fds()

        res.redirects = redirects

        return [res]

    @property
    def __doc__(self):
        return "\n".join(self("--help"))

class Function(Pipeline):
    """Encapsulates a function or iterator so that it can be used
    inside a pipeline. An iterator can only have its output piped into
    something. A function can have its output piped into something by
    yeilding values, and can take input in the form of an iterator as
    a sole argument."""

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
        log.log(indentation + "Running %s with %s" % (Pipeline.repr(self), repr(redirects)), "cmd")

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
    """Pipes the standard out of a source pipeline into the standard
    in of a destination pipeline."""
    def __init__(self, env, src, dst):
        self.env = env
        self.src = src
        self.dst = dst
    def _repr(self):
        return u"%s | %s" % (repr(self.src), repr(self.dst))
    def _run(self, redirects, indentation = ""):
        log.log(indentation + "Running %s with %s" % (Pipeline.repr(self), repr(redirects)), "cmd")
        src = self.src._run(redir.Redirects(redirects).redirect("stdout", redir.PIPE), indentation + "  ")
        dst = self.dst._run(redir.Redirects(redirects).redirect("stdin", src[-1].redirects.stdout.pipe), indentation + "  ")
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
        log.log(indentation + "Running %s with %s and %s=%s" % (Pipeline.repr(self), repr(redirects), self.filedescr, repr(self.file)), "cmd")
        redirects = redir.Redirects(redirects)
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

