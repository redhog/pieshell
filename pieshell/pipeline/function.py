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
import asyncio

from ..utils import copy
from ..utils.asyncutils import asyncmap, itertoasync
from .. import iterio
from .. import redir
from .. import log
from . import running
from . import base
from . import command
import types

    
class Function(base.Pipeline):
    """Encapsulates a function or iterator so that it can be used
    inside a pipeline. An iterator can only have its output piped into
    something. A function can have its output piped into something by
    yeilding values, and can take input in the form of an iterator as
    a sole argument."""

    def __init__(self, env, function, *arg, **kw):
        base.Pipeline.__init__(self, env)
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
                func = "%s.%s" % (type(thing.__self__).__name__, thing.__name__)
            else:
                func = thing.__name__

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
                args += ["%s=%s" % (key, repr(value)) for (key, value) in self._kw.items()]
            return u"%s(%s)" % (self._function_name(), ','.join(args))
        else:
            return repr(thing)

    def _run(self, redirects, sess, indentation = ""):
        base.Pipeline._run(self, redirects, sess, indentation)
        
        redirects = redirects.make_pipes()
        log.log(indentation + "Running %s with %s" % (repr(self), repr(redirects)), "cmd")

        @asyncmap
        def convert(x):
            if x is None:
                return x
            elif isinstance(x, bytes):
                return x
            elif isinstance(x, str):
                return x.encode("utf-8")
            else:
                return str(x).encode("utf-8")

        thing = self.__dict__["function"] # Don't wrap functions as instance methods
        if isinstance(thing, (types.FunctionType, types.MethodType)):
            thing = thing(
                iterio.LineInputHandler(redirects.stdin.open(False), usage=self),
                *self._arg, **self._kw)

        if not hasattr(thing, "__iter__") and not hasattr(thing, "__aiter__"):
            if isinstance(thing, types.CoroutineType):
                unwrapped = thing
                async def wrapper():
                    th = await unwrapped
                    yield th
                thing = wrapper()
            else:
                thing = [thing]
        if hasattr(thing, "__iter__"):
            thing = itertoasync(thing)
        thing = convert(thing)
            
        self._running_process = running.RunningFunction(
            self,
            iterio.LineOutputHandler(
                redirects.stdout.open(False),
                thing,
                usage=self))
        self._running_processes = [self._running_process]
        self._redirects = self._running_process.redirects = redirects

        redirects.close_source_fds()

        return self._running_processes
