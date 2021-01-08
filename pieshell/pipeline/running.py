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

class PipelineFailed(Exception):
    def __init__(self, pipeline):
        self.pipeline = pipeline
    def __str__(self):
        return "%s failed:\n%s" % (
            self.pipeline,
            "\n\n================================\n\n".join(
                [proc.__repr__(display_tmp_content=True)
                 for proc in self.pipeline.failed_processes]))

class RunningPipeline(object):
    def __init__(self, processes, pipeline):
        self.processes = processes
        self.pipeline = pipeline
    def __iter__(self):
        return iterio.LineInputHandler(self.pipeline._redirects.stdout.pipe)
    def wait(self):
        while functools.reduce(operator.__or__, (proc.is_running for proc in self.processes), False):
            iterio.get_io_manager().handle_io()
        if self.failed_processes:
            exc = PipelineFailed(self)
            for proc in self.processes:
                proc.load_output_files()
            raise exc
    @property
    def failed_processes(self):
        return [proc
                for proc in self.processes
                if (not proc.iohandler.is_running
                    and proc.iohandler.last_event["ssi_status"] != 0)]
    def remove_output_files(self):
        for proc in self.pipeline.processes:
            proc.remove_output_files()
    def __repr__(self):
        return repr(self.pipeline)

class RunningItem(object):
    def __init__(self, cmd, iohandler):
        self.cmd = cmd
        self.iohandler = iohandler
    @property
    def output_files(self):
        return {fd: redirect.pipe
                for fd, redirect in self.cmd._redirects.redirects.iteritems()
                if isinstance(redirect.pipe, (str, unicode))}
    def remove_output_files(self):
        for fd, name in self.output_files.iteritems():
            os.unlink(name)
    def load_output_files(self):
        if self.output_content is not None: return
        self.output_content = {}
        for fd, name in self.output_files.iteritems():
            with open(name) as f:
                self.output_content[fd] = f.read()
        self.remove_output_files()
    def __getattr__(self, name):
        return getattr(self.iohandler, name)

class RunningFunction(RunningItem):
    def __repr__(self):
        return '%s(%s)' % (self.cmd._function_name(), ",".join(self.iohandler._repr_args()))

class RunningProcess(RunningItem):
    def __init__(self, cmd, pid):
        RunningItem.__init__(self, cmd, iterio.ProcessSignalHandler(pid))
        self.output_content = None
    def __repr__(self, display_tmp_content=False):
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
        if display_tmp_content:
            self.load_output_files()
            res += "\n"
            for fd, value in self.output_content.iteritems():
                res += "%s content:\n%s\n" % (fd, value) 
        return res
