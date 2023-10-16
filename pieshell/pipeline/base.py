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
from ..utils.asyncutils import asyncitertoiter
from .. import redir
from .. import log
from . import running

repr_state = threading.local()
standard_repr = builtins.repr
def pipeline_repr(obj):
    """Returns a string representation of an object, including pieshell
    pipelines."""

    if not hasattr(repr_state, 'in_repr'):
        repr_state.in_repr = 0
    repr_state.in_repr += 1
    try:
        return standard_repr(obj)
    except:
        return "<Failed to print: " + standard_repr(type(obj)) + " @ " + str(id(obj)) + ">"
    finally:
        repr_state.in_repr -= 1
builtins.repr = pipeline_repr

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
        self.__module__ = None
    def __deepcopy__(self, memo = {}):
        return type(self)(self._env)
    def _coerce(self, thing, direction):
        from . import function
        if thing is None:
            thing = "/dev/null"
        if isinstance(thing, (str, bytes)):
            thing = redir.Redirect(direction, thing)
        if isinstance(thing, redir.Redirect):
            thing = redir.Redirects(thing, defaults=False)
        if not isinstance(thing, Pipeline) and (isinstance(thing, (types.FunctionType, types.MethodType))
                                                or hasattr(thing, "__iter__")
                                                or hasattr(thing, "__next__")):
            thing = function.Function(self._env, thing)
        if not isinstance(thing, (Pipeline, redir.Redirects)):
            raise ValueError(type(thing))
        return thing
    def __ror__(self, other):
        """Pipes the standard out of a pipeline into the standrad in
        of this pipeline."""
        from . import redirect
        from . import pipe
        other = self._coerce(other, 'stdin')
        if isinstance(other, redir.Redirects):
            return redirect.CmdRedirect(self._env, self, other)
        else:
            return pipe.Pipe(self._env, other, self)
    def __or__(self, other):
        """Pipes the standard out of the pipeline into the standrad in
        of another pipeline."""
        from . import redirect
        from . import pipe
        if other is True:
            return self
        other = self._coerce(other, 'stdout')
        if isinstance(other, redir.Redirects):
            return redirect.CmdRedirect(self._env, self, other)
        else:
            return pipe.Pipe(self._env, self, other)
    def __and__(self, other):
        self = self | other
        return self.run()
    def __gt__(self, file):
        """Redirects the standard out of the pipeline to a file."""
        return self | file
    def __lt__(self, file):
        """Redirects the standard in of the pipeline from a file."""
        return file | self
    def __add__(self, other):
        from . import group
        return group.Group(self._env, self, other)

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
        pipeline = running.RunningPipeline(processes, self)
        self._env.last_pipeline = pipeline
        self._env.running_pipelines.append(pipeline)
        return pipeline
    
    async def async_run_interactive(self):
        pipeline = self.run()
        await pipeline.wait()
        return pipeline
    
    def run_interactive(self):
        return asyncio.get_event_loop().run_until_complete(self.async_run_interactive())
        
    def __pos__(self):
        return self.run_interactive()

    def __await__(self):
        return self.async_run_interactive().__await__()
    
    async def __aiter__(self):
        """Runs the pipeline and iterates over its standrad output lines."""
        return await self.run([redir.Redirect("stdout", redir.PIPE)]).__aiter__()

    def __iter__(self):
        return asyncitertoiter(self.__aiter__())
    
    def __str__(self):
        # FIXME: Should use locale, but python's locale module is broken and ignores LC_* by default
        return bytes(self).decode("utf-8")
    def __bytes__(self):
        """Runs the pipeline and returns its standrad out output as a string"""
        return b"".join(asyncitertoiter(self.run([redir.Redirect("stdout", redir.PIPE)]).iterbytes()))
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
            except KeyboardInterrupt as e:
                log.log("Canceled:\n%s" % (e,), "error")
            except running.PipelineInterrupted as e:
                log.log("Canceled:\n%s" % (e,), "error")
            except running.PipelineSuspended as e:
                log.log("Suspended:\n%s" % (e,), "error")
            return ''
        else:
            current_env = getattr(Pipeline._print_state, 'env', None)
            Pipeline._print_state.env = self._env
            try:
                if current_env is not self._env:
                    return "%s in %s" % (self._repr(), repr(self._env))
                return self._repr()
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

    @property
    def __signature__(self):
        return None
