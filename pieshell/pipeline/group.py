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

class Group(base.Pipeline):
    """Runs two pipelines in parallel"""
    def __init__(self, env, a, b):
        base.Pipeline.__init__(self, env)
        self.a = a
        self.b = b
    def __deepcopy__(self, memo = {}):
        return type(self)(self._env, copy.deepcopy(self.a), copy.deepcopy(self.b))
    def _repr(self):
        return u"%s + %s" % (repr(self.a), repr(self.b))
    def _run(self, redirects, sess, indentation = ""):
        base.Pipeline._run(self, redirects, sess, indentation)

        child_redirects = redir.Redirects(redirects)
        child_redirects.borrow()

        log.log(indentation + "Running %s with %s" % (repr(self), repr(redirects)), "cmd")
        a = self.a._run(child_redirects, sess, indentation + "  ")
        b = self.b._run(child_redirects, sess, indentation + "  ")

        self._redirects = self.a._redirects.merge(self.b._redirects)

        redirects.close_source_fds()

        return a + b
    def __dir__(self):
        return ["a", "b"]
