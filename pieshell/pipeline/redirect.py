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
from . import pipe

class CmdRedirect(base.Pipeline):
    def __init__(self, env, pipeline, redirects):
        base.Pipeline.__init__(self, env)
        self.pipeline = pipeline
        self.cmd_redirects = redirects
    def __deepcopy__(self, memo = {}):
        return type(self)(self._env, copy.deepcopy(self.pipeline), copy.deepcopy(self.cmd_redirects))
    def _repr(self):
        return u"%s with %s" % (repr(self.pipeline), repr(self.cmd_redirects))
    def _run(self, redirects, sess, indentation = ""):
        base.Pipeline._run(self, redirects, sess, indentation)

        log.log(indentation + "Running [%s] with %s" % (repr(self), repr(redirects)), "cmd")

        res = self.pipeline._run(redirects.merge(self.cmd_redirects), indentation + "  ")
        self._redirects = self.pipeline._redirects
        return res
