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
import builtins        
import functools

from .. import iterio

class RunningPipeline(object):
    def __init__(self, processes, pipeline):
        self.processes = processes
        self.pipeline = pipeline
    def __iter__(self):
        return iterio.LineInputHandler(self.pipeline._redirects.stdout.pipe)
    def wait(self):
        while functools.reduce(operator.__or__, (proc.is_running for proc in self.processes), False):
            iterio.get_io_manager().handle_io()

    def __repr__(self):
        return repr(self.pipeline)

class RunningItem(object):
    def __init__(self, cmd, iohandler):
        self.cmd = cmd
        self.iohandler = iohandler
    def __getattr__(self, name):
        return getattr(self.iohandler, name)

class RunningFunction(RunningItem):
    def __repr__(self):
        return '%s(%s)' % (self.cmd._function_name(), ",".join(self.iohandler._repr_args()))

class RunningProcess(RunningItem):
    def __init__(self, cmd, pid):
        RunningItem.__init__(self, cmd, iterio.ProcessSignalHandler(pid))
    def __repr__(self):
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
        if status:
            status = ' (' + ', '.join(status) + ')'
        else:
            status = ''
        return '%s%s' % (self.iohandler.pid, status)
