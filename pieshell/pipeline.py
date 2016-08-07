#! /usr/bin/env python

import os
import fcntl
import types
import sys
import tempfile
import uuid
import code
import traceback
import threading
import signal
import signalfd
import operator
import re

from . import copy
from . import iterio
from . import redir
from . import log

class RunningPipeline(object):
    def __init__(self, processes, pipeline):
        self.processes = processes
        self.pipeline = pipeline
    def __iter__(self):
        return iterio.LineInputHandler(self.pipeline.redirects.stdout.pipe)
    def wait(self):
        while reduce(operator.__or__, (proc.is_running for proc in self.processes), False):
            iterio.get_io_manager().handle_io()

    def __repr__(self):
        return repr(self.pipeline)

class RunningProcess(iterio.ProcessSignalHandler):
    def __repr__(self):
        status = []
        last_event = self.last_event
        if last_event:
            last_event = iterio.siginfo_to_names(last_event)
        if self.is_running:
            if last_event and last_event["ssi_code"] != 'CLD_CONTINUED':
                status.append("status=%s" % self.last_event["ssi_code"])
                status.append("signal=%s" % self.last_event["ssi_status"])
        else:
            status.append("exit_code=%s" % self.last_event["ssi_status"])
        if status:
            status = ' (' + ', '.join(status) + ')'
        else:
            status = ''
        return '%s%s' % (self.pid, status)

# help() doesn't let you override help on objects, only on classes, so
# make everything a class...
class DescribableObject(type):
    def __new__(cls, *arg, **kw):
        return type.__new__(cls, "", (type,), {})
    def __init__(self, *arg, **kw):
        pass

class Pipeline(DescribableObject):
    """Abstract base class for all pipelines"""

    print_state = threading.local()
    def __init__(self, env):
        self.env = env
        self.started = False
    def __deepcopy__(self, memo = {}):
        return type(self)(self.env)
    def _coerce(self, thing, direction):
        if thing is None:
            thing = "/dev/null"
        if isinstance(thing, (str, unicode)):
            thing = redir.Redirect(direction, thing)
        if isinstance(thing, redir.Redirect):
            thing = redir.Redirects(thing, defaults=False)
        if not isinstance(thing, Pipeline) and (isinstance(thing, types.FunctionType) or hasattr(thing, "__iter__") or hasattr(thing, "next")):
            thing = Function(self.env, thing)
        if not isinstance(thing, (Pipeline, redir.Redirects)):
            raise ValueError(type(thing))
        return thing
    def __ror__(self, other):
        """Pipes the standard out of a pipeline into the standrad in
        of this pipeline."""
        other = self._coerce(other, 'stdin')
        if isinstance(other, redir.Redirects):
            return CmdRedirect(self.env, self, other)
        else:
            return Pipe(self.env, other, self)
    def __or__(self, other):
        """Pipes the standard out of the pipeline into the standrad in
        of another pipeline."""
        other = self._coerce(other, 'stdout')
        if isinstance(other, redir.Redirects):
            return CmdRedirect(self.env, self, other)
        else:
            return Pipe(self.env, self, other)
    def __gt__(self, file):
        """Redirects the standard out of the pipeline to a file."""
        return self | file
    def __lt__(self, file):
        """Redirects the standard in of the pipeline from a file."""
        return file | self
    def __add__(self, other):
        return Group(self.env, self, other)

    def _run(self, redirects, sess, indentation = ""):
        self.started = True

    def run(self, redirects = []):
        """Runs the pipelines with the specified redirects and returns
        a RunningPipeline instance."""
        if not isinstance(redirects, redir.Redirects):
            redirects = redir.Redirects(*redirects)
        with copy.copy_session() as sess:
            self = copy.deepcopy(self)
            processes = self._run(redirects, sess)
        pipeline = RunningPipeline(processes, self)
        self.env.last_pipeline = pipeline
        return pipeline

    def run_interactive(self):
        try:
            pipeline = self.run()
            pipeline.wait()
        except Exception, e:
            print e
            sys.last_traceback = sys.exc_info()[2]
            import pdb
            pdb.pm()
        return ""

    def __iter__(self):
        """Runs the pipeline and iterates over its standrad output lines."""
        return iter(self.run([redir.Redirect("stdout", redir.PIPE)]))
    def __unicode__(self):
        # FIXME: Should use locale, but python's locale module is broken and ignores LC_* by default
        return str(self).decode("utf-8")
    def __str__(self):
        """Runs the pipeline and returns its standrad out output as a string"""
        return "\n".join(iter(self.run([redir.Redirect("stdout", redir.PIPE)])))
    def __invert__(self):
        """Start a pipeline in the background"""
        return self.run()


    @classmethod
    def repr(cls, obj):
        """Returns a string representation of the pipeline"""
        if not hasattr(Pipeline.print_state, 'in_repr'):
            Pipeline.print_state.in_repr = 0
        Pipeline.print_state.in_repr += 1
        try:
            return repr(obj)
        finally:
            Pipeline.print_state.in_repr -= 1
    def __repr__(self):
        """Runs the command if the environment has interactive=True,
        sending the output to standard out. If the environment is
        non-interactive, returns a string representation of the
        pipeline without running it."""

        if not self.started and self.env.interactive and getattr(Pipeline.print_state, "in_repr", 0) < 1:
            self.run_interactive()
            return ''
        else:
            current_env = getattr(Pipeline.print_state, 'env', None)
            Pipeline.print_state.env = self.env
            try:
                envstr = ''
                if current_env is not self.env:
                    envstr = repr(self.env)
                return "%s%s" % (envstr, self._repr())
            finally:
                Pipeline.print_state.env = current_env

    def __dir__(self):
        return []

    @property
    def __bases__(self):
        return []

    @property
    def __name__(self):
        current_env = getattr(Pipeline.print_state, 'env', None)
        Pipeline.print_state.env = self.env
        try:
            return Pipeline.repr(self)
        finally:
            Pipeline.print_state.env = current_env

    @property
    def __doc__(self):
        return ""

class BaseCommand(Pipeline):
    """Runs an external program with the specified arguments.
    Arguments are sent in as a list of strings and dictionaries.
    Elements of dictionary arguments are converted into --key=value
    pairs. Note that this short hand syntax might not work for all
    programs, as some expect "--key value", or even "-key=value" (e.g.
    find). """
    def __new__(cls, env, arg = None):
        if cls is BaseCommand:
            if arg:
                builtin = Builtin.get_by_name(arg[0])
                if builtin:
                    cls = builtin
                else:
                    cls = Command
        return Pipeline.__new__(cls, env, arg)

    def __init__(self, env, arg = None):
        Pipeline.__init__(self, env)
        self.arg = arg and list(arg) or []
        self.running_process = None

    def __deepcopy__(self, memo = {}):
        return type(self)(self.env, copy.deepcopy(self.arg))

    def __call__(self, *arg, **kw):
        """Appends a set of arguments to the argument list

            env.mycommand("input_filename", verbose='3', destination="output")

        is equivalent to

            Command(env, ["mycommand", "input_filename", "--verbose=3", "--destination=output"])
        """
        arg = list(arg)
        if kw:
            arg += [kw]
        return type(self)(self.env, self.arg + arg)

    def __getattr__(self, name):
        """Append a name to the argument list, such that e.g.

            env.git.status("--help")

        is equivalent to

            env.git("status", "--help")
        """
        return type(self)(self.env, self.arg + [name])

    def _repr(self):
        args = self.arg or []

        for prefix_idx in xrange(0, len(args) + 1):
            if prefix_idx == len(args):
                break
            if not isinstance(args[prefix_idx], (str, unicode)) or not re.match(r"^[a-zA-Z]*$", args[prefix_idx]):
                break

        if prefix_idx:
            prefix = '.'.join(args[:prefix_idx])
        else:
            prefix = "_"
        args = args[prefix_idx:]

        args = [repr(arg) for arg in args]

        running_process = ''
        if self.running_process:
            running_process = ' as ' + repr(self.running_process)

        return u"%s(%s)%s" % (prefix, ', '.join(args), running_process)

    def arg_list(self, redirects = None, sess = None, indentation = ""):
        def handle_arg_pipes(item):
            if redirects is not None:
                return self.handle_arg_pipes(item, redirects, sess, indentation)
            else:
                return "/dev/fd/X"
        args = []
        if self.arg:
            for arg in self.arg:
                if isinstance(arg, dict):
                    for name, value in arg.iteritems():
                        args.append("--%s=%s" % (name, handle_arg_pipes(value)))
                else:
                    args.append(handle_arg_pipes(arg))
        return args

    def arg_list_sh(self, *arg, **kw):
        def quote_arg(arg):
            arg = str(arg)
            if " " in arg:
                arg = repr(arg)
            return arg
        return ' '.join(quote_arg(arg) for arg in self.arg_list(*arg, **kw))

    def _run(self, redirects, sess, indentation = ""):
        raise NotImplemented

class Builtin(BaseCommand):
    builtins = {}

    @classmethod
    def register(cls, builtin_cls):
        cls.builtins[builtin_cls.name] = builtin_cls

    @classmethod
    def get_by_name(cls, name):
        if name not in cls.builtins:
            return None
        return cls.builtins[name]

    def _run(self, redirects, sess, indentation = ""):
        raise NotImplemented

class Command(BaseCommand):
    """Runs an external program with the specified arguments.
    Arguments are sent in as a list of strings and dictionaries.
    Elements of dictionary arguments are converted into --key=value
    pairs. Note that this short hand syntax might not work for all
    programs, as some expect "--key value", or even "-key=value" (e.g.
    find). """

    def _child(self, redirects, args):
        redirects.perform()
        os.chdir(self.env.cwd)
        os.execvpe(args[0], args, self.env.env)
        os._exit(-1)

    def handle_arg_pipes(self, thing, redirects, sess, indentation):
        if isinstance(thing, Pipeline):
            direction = "stdout"
        elif isinstance(thing, types.FunctionType):
            thing = Function(self.env, thing)
            direction = "stdin"
        elif hasattr(thing, "__iter__") or hasattr(thing, "next"):
            thing = Function(self.env, thing)
            direction = "stdout"
        else:
            # Not a named pipe item, just a string
            return thing
      
        # FIXME: Thing needs copying
        arg_pipe = thing._run(redir.Redirects(redir.Redirect(direction, redir.PIPE)), sess, indentation + "  ")

        fd = redirects.find_free_fd()
        redirects.redirect(
            fd,
            getattr(arg_pipe[-1].redirects, direction).pipe,
            {"stdin": os.O_WRONLY, "stdout": os.O_RDONLY}[direction])

        return "/dev/fd/%s" % fd

    def _run(self, redirects, sess, indentation = ""):
        Pipeline._run(self, redirects, sess, indentation)

        redirects = redirects.make_pipes()
        log.log(indentation + "Running %s with %s" % (Pipeline.repr(self), repr(redirects)), "cmd")

        args = self.arg_list(redirects, sess, indentation)

        log.log(indentation + "  Command line %s witth %s" % (' '.join(repr(arg) for arg in args), repr(redirects)), "cmd")

        pid = os.fork()
        if pid == 0:
            self._child(redirects, args)
            # If we ever get to here, all is lost...
            sys._exit(-1)

        self.running_process = RunningProcess(pid)

        redirects.close_source_fds()

        self.pid = pid
        self.redirects = self.running_process.redirects = redirects

        return [self.running_process]

    def complete(self):
        cmd = self.arg_list_sh() + " "
        return (item.strip() for item in self.env.get_completions(cmd))

    def __dir__(self):
        try:
            return list(self.complete())
        except Exception, e:
            traceback.print_exc()
            return ["<%s>" % e]

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
        Pipeline.__init__(self, env)
        self.function = function
        self.arg = arg
        self.kw = kw
    def __deepcopy__(self, memo = {}):
        return type(self)(self.env, self.__dict__["function"], *copy.deepcopy(self.arg), **copy.deepcopy(self.kw))
    def _repr(self):
        thing = self.__dict__["function"] # Don't wrap functions as instance methods
        if isinstance(thing, types.FunctionType):
            args = []
            if self.arg:
                args += [repr(arg) for arg in self.arg]
            if self.kw:
                args += ["%s=%s" % (key, repr(value)) for (key, value) in self.kw.iteritems()]
            mod = thing.__module__ or ''
            if mod:
                mod = mod + '.'
            return u"%s%s(%s)" % (mod, thing.func_name, ','.join(args))
        else:
            return repr(thing)

    def _run(self, redirects, sess, indentation = ""):
        Pipeline._run(self, redirects, sess, indentation)

        redirects = redirects.make_pipes()
        log.log(indentation + "Running %s with %s" % (Pipeline.repr(self), repr(redirects)), "cmd")

        def convert(x):
            if isinstance(x, str):
                return x
            elif isinstance(x, unicode):
                return x.encode("utf-8")
            else:
                return unicode(x).encode("utf-8")

        thing = self.__dict__["function"] # Don't wrap functions as instance methods
        if isinstance(thing, types.FunctionType):
            thing = thing(
                iterio.LineInputHandler(redirects.stdin.open()),
                *self.arg, **self.kw)
        if hasattr(thing, "__iter__"):
            thing = iter(thing)

        self.running_process = iterio.LineOutputHandler(
            redirects.stdout.open(),
            (convert(x) for x in thing))
        
        self.redirects = self.running_process.redirects = redirects

        return [self.running_process]
        

class Pipe(Pipeline):
    """Pipes the standard out of a source pipeline into the standard
    in of a destination pipeline."""
    def __init__(self, env, src, dst):
        Pipeline.__init__(self, env)
        self.src = src
        self.dst = dst
    def __deepcopy__(self, memo = {}):
        return type(self)(self.env, copy.deepcopy(self.src), copy.deepcopy(self.dst))
    def _repr(self):
        return u"%s | %s" % (repr(self.src), repr(self.dst))
    def _run(self, redirects, sess, indentation = ""):
        Pipeline._run(self, redirects, sess, indentation)

        log.log(indentation + "Running %s with %s" % (Pipeline.repr(self), repr(redirects)), "cmd")
        src = self.src._run(redir.Redirects(redirects).redirect("stdout", redir.PIPE), sess, indentation + "  ")
        dst = self.dst._run(redir.Redirects(redirects).redirect("stdin", src[-1].redirects.stdout.pipe), sess, indentation + "  ")

        self.redirects = self.src.redirects.merge(self.dst.redirects)
        self.redirects.register(redir.Redirect(self.src.redirects.stdin))
        self.redirects.register(redir.Redirect(self.dst.redirects.stdout))

        return src + dst
    def __dir__(self):
        return ["src", "dst"]

# class Group(Pipeline):
#     def __init__(self, env, first, second):
#         Pipeline.__init__(self, env)
#         self.first = first
#         self.second = second
#     def thread_main(self, stdin = None, stdout = None, stderr = None, *arg, **kw):
#         for item in [self.first, self.second]:
#             item.run(stdin=stdin, stdout=stdout, stderr=stderr, **kw).join()
#     def _repr(self):
#         return u"%s + %s" % (repr(self.first), repr(self.second))

class CmdRedirect(Pipeline):
    def __init__(self, env, pipeline, redirects):
        self.env = env
        self.pipeline = pipeline
        self.cmd_redirects = redirects
    def __deepcopy__(self, memo = {}):
        return type(self)(self.env, copy.deepcopy(self.pipeline), copy.deepcopy(self.cmd_redirects))
    def _repr(self):
        return u"%s with %s" % (Pipeline.repr(self.pipeline), repr(self.cmd_redirects))
    def _run(self, redirects, sess, indentation = ""):
        Pipeline._run(self, redirects, sess, indentation)

        log.log(indentation + "Running [%s] with %s" % (Pipeline.repr(self), repr(redirects)), "cmd")

        res = self.pipeline._run(redirects.merge(self.cmd_redirects), indentation + "  ")
        self.redirects = self.pipeline.redirects
        return res
        
