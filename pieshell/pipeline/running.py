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
import asyncio

from .. import iterio
from .. import redir

try:
    import psutil
except:
    psutil = None

class StopSignalHandler(iterio.SignalHandler):
    def __init__(self):
        self.current_pipeline = None
        iterio.SignalHandler.__init__(self, {"ssi_signo": signal.SIGTSTP})
    def handle_event(self, event):
        if self.current_pipeline is not None:
            self.current_pipeline.pipeline_suspended = True
        return True
stop_signal_handler = StopSignalHandler()
    
class PipelineError(Exception):
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
class PipelineSuspended(PipelineError): description = "Pipeline suspended"

class RunningPipeline(object):
    def __init__(self, processes, pipeline):
        self.finish_future = None
        self.processes = processes
        self.pipeline = pipeline
        self.pipeline_suspended = False
        for process in processes:
            process.running_pipeline = self
        # Just in case all the processes have already terminated...
        # They could have been blindingly fast after all :)
        self.handle_finish()
    async def __aiter__(self):
        return await iterio.LineInputHandler(self.pipeline._redirects.stdout.pipe, usage=self, at_eof=self.wait).__aiter__()
    async def iterbytes(self):
        return await iterio.InputHandler(self.pipeline._redirects.stdout.pipe, usage=self, at_eof=self.wait).__aiter__()
    def restart(self):
        self.pipeline_suspended = False
        for process in self.processes:
            process.restart()
    def suspend(self):
        self.pipeline_suspended = True
        for process in self.processes:
            process.suspend()
    async def wait(self):
        try:
            if self.pipeline._env._interactive:
                stop_signal_handler.current_pipeline = self
            try:
                self.restart()
                while not self.pipeline_suspended and self.is_running:
                    future = self.finish_future = asyncio.get_event_loop().create_future()
                    await future
            except KeyboardInterrupt as e:
                raise PipelineInterrupted(self)
            if self.pipeline_suspended:
                self.suspend()
                raise PipelineSuspended(self)
            if self.failed_processes:
                raise PipelineFailed(self)
        finally:
            stop_signal_handler.current_pipeline = None
    def handle_finish(self):
        if not self.is_running:
            for proc in self.processes:
                proc.handle_pipeline_finish()
            for proc in self.processes:
                proc.handle_pipeline_finish_destructive()
            if self in self.pipeline._env.running_pipelines:
                self.pipeline._env.running_pipelines.remove(self)
        if self.finish_future is not None:
            self.finish_future.set_result(None)
            self.finish_future = None
                
    def remove_output_files(self):
        for proc in self.processes:
            proc.remove_output_files()
    @property
    def failed_processes(self):
        return [proc
                for proc in self.processes
                if not proc.is_running and proc.is_failed]
    @property
    def running_processes(self):
        return [proc
                for proc in self.processes
                if proc.is_running]
    def __repr__(self):
        return repr(self.pipeline)
    @property
    def is_running(self):
        return not not self.running_processes
    @property
    def is_failed(self):
        return not not self.failed_processes
    @property
    def exit_code(self):
        return self.processes[-1].exit_code
    
class RunningItem(object):
    def __init__(self, cmd, iohandler):
        self.cmd = cmd
        self.iohandler = iohandler
        self.output_content = {}
    @property
    def is_running(self):
        return self.iohandler.is_running
    def handle_finish(self):
        for fd, redirect in self.cmd._redirects.redirects.items():
            if not isinstance(redirect.pipe, redir.STRING): continue
            with open(redirect.pipe.path) as f:
                self.output_content[fd] = f.read()
        self.running_pipeline.handle_finish()
    @property
    def output_files(self):
        if self.output_content is not None: return {}
        return {fd: redirect.pipe
                for fd, redirect in self.cmd._redirects.redirects.items()
                if isinstance(redirect.pipe, redir.TMP) and not isinstance(redirect.pipe, redir.STRING)}
    def handle_pipeline_finish(self):
        for fd, redirect in self.cmd._redirects.redirects.items():
            if not isinstance(redirect.pipe, redir.STRING): continue
            # Yes, reread the STRING pipe, it can have been modified
            # by another part of the pipeline since we finished.
            with open(redirect.pipe.path) as f:
                self.output_content[fd] = f.read()
    def handle_pipeline_finish_destructive(self):
        for fd, redirect in self.cmd._redirects.redirects.items():
            if not isinstance(redirect.pipe, redir.STRING): continue
            try:
                os.unlink(redirect.pipe.path)
            except FileNotFoundError:
                pass
    def remove_output_files(self):
        for fd, name in self.output_files.items():
            os.unlink(name)
    def restart(self):
        pass
    def suspend(self):
        pass
    def __getattr__(self, name):
        return getattr(self.iohandler, name)

class RunningFunction(RunningItem):
    @property
    def is_failed(self):
        return self.iohandler.exception is not None
    def __repr__(self, display_output=False):
        status = list(self.iohandler._repr_args())
        if status:
            status = ' (' + ', '.join(status) + ')'
        else:
            status = ''
        status = '%s%s' % (self.cmd._function_name(), status)
        if self.iohandler.exception is not None:
            status += "\n" + "".join(traceback.format_exception(
                type(self.iohandler.exception),
                self.iohandler.exception,
                self.iohandler.exception.__traceback__))
        return status

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
    def restart(self):
        try:
            os.kill(self.iohandler.pid, signal.SIGCONT)
        except ProcessLookupError:
            pass
    def suspend(self):
        try:
            os.kill(self.iohandler.pid, signal.SIGSTOP)
        except ProcessLookupError:
            pass
    @property
    def pid(self):
        return self.iohandler.pid
    @property
    def is_failed(self):
        return self.exit_code != 0
    @property
    def exit_code(self):
        return self.iohandler.last_event["ssi_status"]
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
                for fd, output_file in self.output_files.items():
                    status.append("%s=%s" % (fd, output_file))
        if status:
            status = ' (' + ', '.join(status) + ')'
        else:
            status = ''
        res = '%s%s' % (self.iohandler.pid, status)
        if display_output:
            res += "\n"
            for fd, value in self.output_content.items():
                fd = redir.Redirect.names_to_fd.get(fd, fd)
                res += "%s content:\n%s\n" % (fd, value) 
        return res
    @property
    def details(self):
        if psutil is None: return None
        return psutil.Process(self.pid)
    def __getattr__(self, name):
        if psutil is None:
            raise AttributeError(name)
        return getattr(self.details, name)
