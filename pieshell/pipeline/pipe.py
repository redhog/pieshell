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
from . import running
from . import base
from . import command
from . import function
from . import builtins

class Pipe(base.Pipeline):
    """Pipes the standard out of a source pipeline into the standard
    in of a destination pipeline."""
    def __init__(self, env, src, dst):
        base.Pipeline.__init__(self, env)
        self.src = src
        self.dst = dst
    def __deepcopy__(self, memo = {}):
        return type(self)(self._env, copy.deepcopy(self.src), copy.deepcopy(self.dst))
    def _repr(self):
        return u"%s | %s" % (repr(self.src), repr(self.dst))
    def _run(self, redirects, sess, indentation = ""):
        base.Pipeline._run(self, redirects, sess, indentation)

        child_redirects = redir.Redirects(redirects)
        child_redirects.borrow()

        log.log(indentation + "Running %s with %s" % (repr(self), repr(redirects)), "cmd")
        src = self.src._run(redir.Redirects(child_redirects).redirect("stdout", redir.PIPE), sess, indentation + "  ")
        dst = self.dst._run(redir.Redirects(child_redirects).redirect("stdin", self.src._redirects.stdout.pipe), sess, indentation + "  ")

        self._redirects = self.src._redirects.merge(self.dst._redirects)
        self._redirects.register(redir.Redirect(self.src._redirects.stdin))
        self._redirects.register(redir.Redirect(self.dst._redirects.stdout))

        redirects.close_source_fds()

        return src + dst
    def __dir__(self):
        return ["src", "dst"]
