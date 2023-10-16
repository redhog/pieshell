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
import operator
import re
import builtins        
import functools

from ..utils import copy
from .. import iterio
from .. import redir
from .. import log
from .. import environ
from . import running
from . import base
from . import command

class BaseCommand(base.Pipeline):
    """This class is an abstract base class for all commands. It can
    however be instantiated, and will then return an instance of
    either Command or one of the Builtin classes.

    Command arguments are sent in as a list of strings and dictionaries.
    Elements of dictionary arguments are converted into --key=value
    pairs. Note that this short hand syntax might not work for all
    programs, as some expect "--key value", or even "-key=value" (e.g.
    find).

    You can work around this limitation by registering Command
    subclasses that specialcases this handling with the
    BuiltinRegistry.
    """
    def __new__(cls, env, arg = None):
        from . import builtin
        if cls is BaseCommand:
            if arg:
                builtin_cls = builtin.BuiltinRegistry.get_by_name(arg[0])
                if builtin_cls:
                    cls = builtin_cls
                else:
                    cls = Command
        return base.Pipeline.__new__(cls, env, arg)

    def __init__(self, env, arg = None):
        base.Pipeline.__init__(self, env)
        self._arg = arg and list(arg) or []
        self._running_process = None

    def __deepcopy__(self, memo = {}):
        return type(self)(self._env, copy.deepcopy(self._arg))

    def __sub__(self, other):
        return self(-other)

    def __neg__(self):
        assert len(self._arg) == 1, "-a(b) does not make sense syntacticaly"
        return "-" + self._arg[0]
    
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

        for prefix_idx in range(0, len(args) + 1):
            if prefix_idx == len(args):
                break
            if not isinstance(args[prefix_idx], (bytes, str)) or not re.match(r"^[a-zA-Z]*$", args[prefix_idx]):
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
        orig_redirects = redir.Redirects(redirects) if redirects is not None else redir.Redirects()
        orig_redirects.borrow()
        def handle_arg_pipes(item):
            if isinstance(item, (str, environ.R)):
                return item
            elif redirects is not None:
                return self._handle_arg_pipes(item, orig_redirects, redirects, sess, indentation)
            else:
                return "/dev/fd/X"
        args = []
        if self._arg:
            for arg in self._arg:
                if isinstance(arg, dict):
                    for name, value in arg.items():
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


class Command(command.BaseCommand):
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

    def _handle_arg_pipes(self, thing, orig_redirects, redirects, sess, indentation):
        from . import function
        if isinstance(thing, str):
            return thing
        elif isinstance(thing, base.Pipeline):
            direction = "stdout"
        elif isinstance(thing, (types.FunctionType, types.MethodType)):
            thing = function.Function(self._env, thing)
            direction = "stdin"
        elif hasattr(thing, "__iter__") or hasattr(thing, "__next__"):
            thing = function.Function(self._env, thing)
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
        base.Pipeline._run(self, redirects, sess, indentation)

        self._running_processes = []

        redirects = redirects.make_pipes()
        log.log(indentation + "Running %s with %s" % (repr(self), repr(redirects)), "cmd")

        args = self._arg_list(redirects, sess, indentation)
        log.log(indentation + "222Running %s with %s" % (repr(self), repr(redirects)), "cmd")

        pid = os.fork()
        if pid == 0:
            ecode = -1
            try:
                self._child(redirects, args)
            except Exception as e:
                sys.stderr.write("Unable to execute %s: %s\n" % (repr(self), e))
                ecode = getattr(e, "errno", ecode)
            # If we ever get to here, all is lost...
            os._exit(ecode)

        log.log(indentation + "  %s: Command line %s with %s" % (pid, ' '.join(repr(arg) for arg in args), repr(redirects)), "cmd")

        self._running_process = running.RunningProcess(self, pid)
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
        except Exception as e:
            traceback.print_exc()
            return ["<%s>" % e]

    @property
    def __doc__(self):
        return "\n".join(self("--help"))
