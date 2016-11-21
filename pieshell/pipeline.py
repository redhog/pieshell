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
import __builtin__        
import exceptions

from . import copy
from . import iterio
from . import redir
from . import log

class ITERPIPE(redir.PIPE): pass

repr_state = threading.local()
standard_repr = __builtin__.repr
def pipeline_repr(obj):
    """Returns a string representation of an object, including pieshell
    pipelines."""

    if not hasattr(repr_state, 'in_repr'):
        repr_state.in_repr = 0
    repr_state.in_repr += 1
    try:
        return standard_repr(obj)
    finally:
        repr_state.in_repr -= 1
__builtin__.repr = pipeline_repr


class PipelineError(exceptions.BaseException):
    description = "Pipeline"
    def __init__(self, pipeline):
        self.pipeline = pipeline
    def __str__(self):
        return "%s: %s:\n\n%s" % (
            self.description,
            self.pipeline,
            "\n\n================================\n\n".join(
                [proc.__repr__(display_output=True)
                 for proc in self.pipeline.failed_processes]))

class PipelineFailed(PipelineError, Exception): description = "Pipeline failed"
class PipelineInterrupted(PipelineError, KeyboardInterrupt): description = "Pipeline canceled"

class RunningPipeline(object):
    def __init__(self, processes, pipeline):
        self.processes = processes
        self.pipeline = pipeline
    def __iter__(self):
        def handle_input():
            for line in iterio.LineInputHandler(self.pipeline._redirects.stdout.pipe, usage=self):
                yield line
            self.wait()
        return iter(handle_input())
    def wait(self):
        while reduce(operator.__or__, (proc.is_running for proc in self.processes), False):
            print "Waiting for", iterio.get_io_manager()
            iterio.get_io_manager().handle_io()
        if self.failed_processes:
            raise PipelineFailed(self)
    @property
    def failed_processes(self):
        return [proc
                for proc in self.processes
                if not proc.is_running and proc.is_failed]
    def remove_output_files(self):
        for proc in self.pipeline.processes:
            proc.remove_output_files()
    def __repr__(self):
        return repr(self.pipeline)

class RunningItem(object):
    def __init__(self, cmd, iohandler):
        self.cmd = cmd
        self.iohandler = iohandler
        self.output_content = {}
    @property
    def is_running(self):
        return self.iohandler.is_running
    def handle_finish(self):
        for fd, redirect in self.cmd._redirects.redirects.iteritems():
            if not isinstance(redirect.pipe, redir.STRING): continue
            with open(redirect.pipe.path) as f:
                self.output_content[fd] = f.read()
            os.unlink(redirect.pipe.path)
    @property
    def output_files(self):
        if self.output_content is not None: return {}
        return {fd: redirect.pipe
                for fd, redirect in self.cmd._redirects.redirects.iteritems()
                if isinstance(redirect.pipe, redir.TMP) and not isinstance(redirect.pipe, redir.STRING)}
    def remove_output_files(self):
        for fd, name in self.output_files.iteritems():
            os.unlink(name)
    def __getattr__(self, name):
        return getattr(self.iohandler, name)

class RunningFunction(RunningItem):
    @property
    def is_failed(self):
        return self.iohandler.exception is not None
    def __repr__(self, display_output=False):
        status = list(self.iohandler._repr_args())
        if self.iohandler.exception is not None:
            status.append(str(self.iohandler.exception))
        if status:
            status = ' (' + ', '.join(status) + ')'
        else:
            status = ''
        return '%s%s' % (self.cmd._function_name(), status)

class RunningProcess(RunningItem):
    class ProcessSignalHandler(iterio.ProcessSignalHandler):
        def __init__(self, process, pid):
            self.process = process
            iterio.ProcessSignalHandler.__init__(self, pid)
        def handle_event(self, event):
            res = iterio.ProcessSignalHandler.handle_event(self, event)
            if not self.is_running:
                self.process.handle_finish()
            return res
    def __init__(self, cmd, pid):
        RunningItem.__init__(self, cmd, self.ProcessSignalHandler(self, pid))
    @property
    def is_failed(self):
        return self.iohandler.last_event["ssi_status"] != 0
    def __repr__(self, display_output=False):
        status = []
        last_event = self.iohandler.last_event
        if last_event:
            last_event = iterio.siginfo_to_names(last_event)
        if self.iohandler.is_running:
            if last_event and last_event["ssi_code"] != 'CLD_CONTINUED':
                status.append("status=%s" % self.iohandler.last_event["ssi_code"])
                status.append("signal=%s" % self.iohandler.last_event["ssi_status"])
        else:
            status.append("exit_code=%s" % self.iohandler.last_event["ssi_status"])
            if len(self.output_files):
                for fd, output_file in self.output_files.iteritems():
                    status.append("%s=%s" % (fd, output_file))
        if status:
            status = ' (' + ', '.join(status) + ')'
        else:
            status = ''
        res = '%s%s' % (self.iohandler.pid, status)
        if display_output:
            res += "\n"
            for fd, value in self.output_content.iteritems():
                fd = redir.Redirect.names_to_fd.get(fd, fd)
                res += "%s content:\n%s\n" % (fd, value) 
        return res

# help() doesn't let you override help on objects, only on classes, so
# make everything a class...
class DescribableObject(type):
    def __new__(cls, *arg, **kw):
        return type.__new__(cls, "", (type,), {})
    def __init__(self, *arg, **kw):
        pass

class Pipeline(DescribableObject):
    """Abstract base class for all pipelines"""

    _print_state = threading.local()
    def __init__(self, env):
        self._env = env
        self._started = False
    def __deepcopy__(self, memo = {}):
        return type(self)(self._env)
    def _coerce(self, thing, direction):
        if thing is None:
            thing = "/dev/null"
        if isinstance(thing, (str, unicode)):
            thing = redir.Redirect(direction, thing)
        if isinstance(thing, redir.Redirect):
            thing = redir.Redirects(thing, defaults=False)
        if not isinstance(thing, Pipeline) and (isinstance(thing, types.FunctionType) or hasattr(thing, "__iter__") or hasattr(thing, "next")):
            thing = Function(self._env, thing)
        if not isinstance(thing, (Pipeline, redir.Redirects)):
            raise ValueError(type(thing))
        return thing
    def __ror__(self, other):
        """Pipes the standard out of a pipeline into the standrad in
        of this pipeline."""
        other = self._coerce(other, 'stdin')
        if isinstance(other, redir.Redirects):
            return CmdRedirect(self._env, self, other)
        else:
            return Pipe(self._env, other, self)
    def __or__(self, other):
        """Pipes the standard out of the pipeline into the standrad in
        of another pipeline."""
        other = self._coerce(other, 'stdout')
        if isinstance(other, redir.Redirects):
            return CmdRedirect(self._env, self, other)
        else:
            return Pipe(self._env, self, other)
    def __gt__(self, file):
        """Redirects the standard out of the pipeline to a file."""
        return self | file
    def __lt__(self, file):
        """Redirects the standard in of the pipeline from a file."""
        return file | self
    def __add__(self, other):
        return Group(self._env, self, other)

    def _run(self, redirects, sess, indentation = ""):
        self._started = True

    def run(self, redirects = []):
        """Runs the pipelines with the specified redirects and returns
        a RunningPipeline instance."""
        if not isinstance(redirects, redir.Redirects):
            redirects = redir.Redirects(self._env._redirects, *redirects)
        with copy.copy_session() as sess:
            self = copy.deepcopy(self)
            processes = self._run(redirects, sess)
        pipeline = RunningPipeline(processes, self)
        self._env.last_pipeline = pipeline
        return pipeline

    def run_interactive(self):
        pipeline = None
        pipeline = self.run()
        try:
            pipeline.wait()
        except KeyboardInterrupt, e:
            raise PipelineInterrupted(pipeline)
        return pipeline

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
    def __repr__(self):
        """Runs the command if the environment has interactive=True,
        sending the output to standard out. If the environment is
        non-interactive, returns a string representation of the
        pipeline without running it."""

        if not self._started and self._env._interactive and getattr(repr_state, "in_repr", 0) < 1:
            try:
                self.run_interactive()
            except KeyboardInterrupt, e:
                log.log("Canceled:\n%s" % (e,), "error")
            except Exception, e:
                log.log("Error:\n%s" % (e,), "error")
                sys.last_traceback = sys.exc_info()[2]
                import pdb
                pdb.pm()
            return ''
        else:
            current_env = getattr(Pipeline._print_state, 'env', None)
            Pipeline._print_state.env = self._env
            try:
                envstr = ''
                if current_env is not self._env:
                    envstr = repr(self._env)
                return "%s%s" % (envstr, self._repr())
            finally:
                Pipeline._print_state.env = current_env

    def __dir__(self):
        return []

    @property
    def __bases__(self):
        return []

    @property
    def __name__(self):
        current_env = getattr(Pipeline._print_state, 'env', None)
        Pipeline._print_state.env = self._env
        try:
            return repr(self)
        finally:
            Pipeline._print_state.env = current_env

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
                builtin = BuiltinRegistry.get_by_name(arg[0])
                if builtin:
                    cls = builtin
                else:
                    cls = Command
        return Pipeline.__new__(cls, env, arg)

    def __init__(self, env, arg = None):
        Pipeline.__init__(self, env)
        self._arg = arg and list(arg) or []
        self._running_process = None

    def __deepcopy__(self, memo = {}):
        return type(self)(self._env, copy.deepcopy(self._arg))

    def __call__(self, *arg, **kw):
        """Appends a set of arguments to the argument list

            env.mycommand("input_filename", verbose='3', destination="output")

        is equivalent to

            Command(env, ["mycommand", "input_filename", "--verbose=3", "--destination=output"])
        """
        arg = list(arg)
        if kw:
            arg += [kw]
        return type(self)(self._env, self._arg + arg)

    def __getattr__(self, name):
        """Append a name to the argument list, such that e.g.

            env.git.status("--help")

        is equivalent to

            env.git("status", "--help")
        """
        return type(self)(self._env, self._arg + [name])

    def _repr(self):
        args = self._arg or []

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
        if self._running_process:
            running_process = ' as ' + repr(self._running_process)

        return u"%s(%s)%s" % (prefix, ', '.join(args), running_process)

    def _arg_list(self, redirects = None, sess = None, indentation = ""):
        orig_redirects = redir.Redirects(redirects)
        orig_redirects.borrow()
        def handle_arg_pipes(item):
            if redirects is not None:
                return self._handle_arg_pipes(item, orig_redirects, redirects, sess, indentation)
            else:
                return "/dev/fd/X"
        args = []
        if self._arg:
            for arg in self._arg:
                if isinstance(arg, dict):
                    for name, value in arg.iteritems():
                        for match in self._env._expand_argument(handle_arg_pipes(value)):
                            args.append("--%s=%s" % (name, match))
                else:
                    for match in self._env._expand_argument(handle_arg_pipes(arg)):
                        args.append(match)
        return args

    def _arg_list_sh(self, *arg, **kw):
        def quote_arg(arg):
            arg = str(arg)
            if " " in arg:
                arg = repr(arg)
            return arg
        return ' '.join(quote_arg(arg) for arg in self._arg_list(*arg, **kw))

    def _run(self, redirects, sess, indentation = ""):
        raise NotImplemented

class BuiltinRegistry(object):
    builtins = {}

    @classmethod
    def register(cls, builtin_cls):
        cls.builtins[builtin_cls.name] = builtin_cls

    @classmethod
    def get_by_name(cls, name):
        if name not in cls.builtins:
            return None
        return cls.builtins[name]

class Builtin(BaseCommand):
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
        os.chdir(self._env._cwd)
        os.execvpe(args[0], args, self._env._exports)
        os._exit(-1)

    def _handle_arg_pipes(self, thing, orig_redirects, redirects, sess, indentation):
        if isinstance(thing, Pipeline):
            direction = "stdout"
        elif isinstance(thing, (types.FunctionType, types.MethodType)):
            thing = Function(self._env, thing)
            direction = "stdin"
        elif hasattr(thing, "__iter__") or hasattr(thing, "next"):
            thing = Function(self._env, thing)
            direction = "stdout"
        else:
            # Not a named pipe item, just a string
            return thing
      
        arg_pipe = thing._run(
            redir.Redirects(
                orig_redirects,
                redir.Redirect(direction, redir.PIPE)),
            sess,
            indentation + "  ")

        fd = redirects.find_free_fd()
        redirects.redirect(
            fd,
            getattr(thing._redirects, direction).pipe,
            {"stdin": os.O_WRONLY, "stdout": os.O_RDONLY}[direction])

        self._running_processes.extend(arg_pipe)

        return "/dev/fd/%s" % fd

    def _run(self, redirects, sess, indentation = ""):
        Pipeline._run(self, redirects, sess, indentation)

        self._running_processes = []

        redirects = redirects.make_pipes()
        log.log(indentation + "Running %s with %s" % (repr(self), repr(redirects)), "cmd")

        args = self._arg_list(redirects, sess, indentation)
        log.log(indentation + "222Running %s with %s" % (repr(self), repr(redirects)), "cmd")

        pid = os.fork()
        if pid == 0:
            self._child(redirects, args)
            # If we ever get to here, all is lost...
            sys._exit(-1)

        log.log(indentation + "  %s: Command line %s with %s" % (pid, ' '.join(repr(arg) for arg in args), repr(redirects)), "cmd")

        self._running_process = RunningProcess(self, pid)
        self._running_processes.append(self._running_process)

        redirects.close_source_fds()

        self._pid = pid
        self._redirects = self._running_process.redirects = redirects

        return self._running_processes

    def _complete(self):
        cmd = self._arg_list_sh() + " "
        return (item.strip() for item in self._env.get_completions(cmd))

    def __dir__(self):
        try:
            return list(self._complete())
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
        self._arg = arg
        self._kw = kw
    def __deepcopy__(self, memo = {}):
        return type(self)(self._env, self.__dict__["function"], *copy.deepcopy(self._arg), **copy.deepcopy(self._kw))
    def _function_name(self):
        thing = self.__dict__["function"] # Don't wrap functions as instance methods
        if isinstance(thing, (types.FunctionType, types.MethodType)):
            mod = thing.__module__ or ''
            if mod:
                mod = mod + '.'
            
            if isinstance(thing, types.MethodType):
                func = "%s.%s" % (thing.im_class.__name__, thing.im_func.func_name)
            else:
                func = thing.func_name

            return u"%s%s" % (mod, func)
        else:
            return repr(thing)
    def _repr(self):
        thing = self.__dict__["function"] # Don't wrap functions as instance methods
        if isinstance(thing, (types.FunctionType, types.MethodType)):
            args = []
            if self._arg:
                args += [repr(arg) for arg in self._arg]
            if self._kw:
                args += ["%s=%s" % (key, repr(value)) for (key, value) in self._kw.iteritems()]
            return u"%s(%s)" % (self._function_name(), ','.join(args))
        else:
            return repr(thing)

    def _run(self, redirects, sess, indentation = ""):
        Pipeline._run(self, redirects, sess, indentation)
        
        output_iterpipe = None
        if (    isinstance(redirects.stdout.source, type)
            and issubclass(redirects.stdout.source, ITERPIPE)):
            output_iterpipe = redirects.stdout.source

        if output_iterpipe:
            redirects.redirect("stdout")

        redirects = redirects.make_pipes()
        log.log(indentation + "Running %s with %s" % (repr(self), repr(redirects)), "cmd")

        def convert(x):
            if x is None:
                return x
            elif isinstance(x, str):
                return x
            elif isinstance(x, unicode):
                return x.encode("utf-8")
            else:
                return unicode(x).encode("utf-8")

        thing = self.__dict__["function"] # Don't wrap functions as instance methods
        if isinstance(thing, (types.FunctionType, types.MethodType)):
            if isinstance(redirects.stdin.source, ITERPIPE):
                thing = thing(redirects.stdin.source.iter, *self._arg, **self._kw)
            else:
                thing = thing(
                    iterio.LineInputHandler(redirects.stdin.open(False), usage=self),
                    *self._arg, **self._kw)
        if hasattr(thing, "__iter__"):
            thing = iter(thing)

        if output_iterpipe:
            self._running_processes = []
            self._redirects = redirects
            self._redirects.redirect(
                "stdout",
                source=output_iterpipe,
                pipe=output_iterpipe(iter=thing))
        else:
            self._running_process = RunningFunction(
                self,
                iterio.LineOutputHandler(
                    redirects.stdout.open(False),
                    (convert(x) for x in thing),
                    usage=self))
            self._running_processes = [self._running_process]
            self._redirects = self._running_process.redirects = redirects

        redirects.close_source_fds()

        return self._running_processes
        

class Pipe(Pipeline):
    """Pipes the standard out of a source pipeline into the standard
    in of a destination pipeline."""
    def __init__(self, env, src, dst):
        Pipeline.__init__(self, env)
        self.src = src
        self.dst = dst
    def __deepcopy__(self, memo = {}):
        return type(self)(self._env, copy.deepcopy(self.src), copy.deepcopy(self.dst))
    def _repr(self):
        return u"%s | %s" % (repr(self.src), repr(self.dst))
    def _run(self, redirects, sess, indentation = ""):
        Pipeline._run(self, redirects, sess, indentation)

        child_redirects = redir.Redirects(redirects)
        child_redirects.borrow()

        log.log(indentation + "Running %s with %s" % (repr(self), repr(redirects)), "cmd")
        src = self.src._run(redir.Redirects(child_redirects).redirect("stdout", ITERPIPE), sess, indentation + "  ")
        dst = self.dst._run(redir.Redirects(child_redirects).redirect("stdin", self.src._redirects.stdout.pipe), sess, indentation + "  ")

        self._redirects = self.src._redirects.merge(self.dst._redirects)
        self._redirects.register(redir.Redirect(self.src._redirects.stdin))
        self._redirects.register(redir.Redirect(self.dst._redirects.stdout))

        redirects.close_source_fds()

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
        Pipeline.__init__(self, env)
        self.pipeline = pipeline
        self.cmd_redirects = redirects
    def __deepcopy__(self, memo = {}):
        return type(self)(self._env, copy.deepcopy(self.pipeline), copy.deepcopy(self.cmd_redirects))
    def _repr(self):
        return u"%s with %s" % (repr(self.pipeline), repr(self.cmd_redirects))
    def _run(self, redirects, sess, indentation = ""):
        Pipeline._run(self, redirects, sess, indentation)

        log.log(indentation + "Running [%s] with %s" % (repr(self), repr(redirects)), "cmd")

        res = self.pipeline._run(redirects.merge(self.cmd_redirects), indentation + "  ")
        self._redirects = self.pipeline._redirects
        return res
