import subprocess
import threading
import os
import fcntl
import types
import iterio
import pipe

class ShellScript(object):
    pass

class Environment(ShellScript):
    def __init__(self):
        self.cwd = None
        self.env = None
    def __getattr__(self, name):
        return Command(self, name)
    def __repr__(self):
        return str(id(self))

env = Environment()

class RunningPipeline(object):
    def __init__(self, processes):
        self.processes = processes
    def __iter__(self):
        return iterio.LineInputHandler(self.processes[-1].pipes['stdout'])
    def join(self):
        last = self.processes[-1]
        last.wait()

class Pipeline(ShellScript):
    def setup_run_pipes(self, stdin = None, stdout = None, stderr = None, *arg, **kw):
        inputs = {'stdin': stdin,
                  'stdout': stdout,
                  'stderr': stderr}
        pipes = {}
        for key in ('stdin', 'stdout', 'stderr'):
            if inputs[key] is subprocess.PIPE:
                r, w = pipe.pipe_cloexec()
                if key == 'stdin':
                    pipes[key], inputs[key] = w, r
                else:
                    inputs[key], pipes[key] = w, r
        return arg, kw, inputs, pipes
    def _coerce(self, thing):
        if isinstance(thing, Pipeline):
            return thing
        elif isinstance(thing, types.FunctionType) or hasattr(thing, "__iter__") or hasattr(thing, "next"):
            return Function(thing)
        else:
            raise ValueError(type(thing))
    def __ror__(self, other):
        return Pipe(self._coerce(other), self)
    def __or__(self, other):
        return Pipe(self, self._coerce(other))
    def __gt__(self, file):
        return Redirect(self, file, "stdout")
    def __lt__(self, file):
        return Redirect(self, file, "stdin")
    def __add__(self, other):
        return Group(self, other)
    def run(self, stdin = None, stdout = subprocess.PIPE, stderr = None, **kw):
        return RunningPipeline(self._run(stdin = stdin, stdout = stdout, stderr = stderr, **kw))
    def __iter__(self):
        return iter(self.run(stdout=subprocess.PIPE))
    def __unicode__(self):
        return "\n".join(iter(self(stdout=subprocess.PIPE)))

class Command(Pipeline):
    def __init__(self, env, name, arg = None, kw = None):
        self.env = env
        self.name = name
        self.arg = arg
        self.kw = kw
    def __call__(self, *arg, **kw):
        return type(self)(self.env, self.name, arg, kw)
    def __repr__(self):
        args = []
        if self.arg:
            args += [repr(arg) for arg in self.arg]
        if self.kw:
            args += ["%s=%s" % (key, repr(value)) for (key, value) in self.kw.iteritems()]
        return u"%s.%s(%s)" % (self.env, self.name, ', '.join(args))
    def _run(self, *args, **kw):
        _, kw, inputs, pipes = self.setup_run_pipes(*args, **kw)
        kw.update(inputs)

        args = [self.name]
        if self.arg:
            args += list(self.arg)
        if self.kw:
            args += ["--%s=%s" % (name, value) for (name, value) in self.kw.iteritems()]

        res = subprocess.Popen(args, cwd=env.cwd, env=env.env, **kw)
        for fd in inputs.itervalues():
            if isinstance(fd, int):
                os.close(fd)
        res.pipes = pipes

        return [res]

class Function(Pipeline):
    def __init__(self, function, *arg, **kw):
        self.function = function
        self.arg = arg
        self.kw = kw

    def __repr__(self):
        args = []
        if self.arg:
            args += [repr(arg) for arg in self.arg]
        if self.kw:
            args += ["%s=%s" % (key, repr(value)) for (key, value) in self.kw.iteritems()]
        return u"%s.%s.%s(%s)" % (self.function.__module__, self.function.func_name, ','.join(args))

    def _run(self, *arg, **kw):
        arg, kw, inputs, pipes = self.setup_run_pipes(*arg, **kw)

        def convert(x):
            if isinstance(x, str):
                return x
            elif isinstance(x, unicode):
                return x.encode("utf-8")
            else:
                return unicode(x).encode("utf-8")

        thing = self.function
        if isinstance(thing, types.FunctionType):
            thing = thing(
                iterio.LineInputHandler(inputs['stdin']),
                *self.arg, **self.kw)
        if hasattr(thing, "__iter__"):
            thing = iter(thing)

        res = iterio.LineOutputHandler(
            inputs['stdout'],
            (convert(x) for x in thing))

        res.pipes = pipes

        return [res]
        

class Pipe(Pipeline):
    def __init__(self, src, dst):
        self.src = src
        self.dst = dst
    def __repr__(self):
        return u"%s | %s" % (self.src, self.dst)
    def _run(self, stdin = None, stdout = None, stderr = None, **kw):
        src = self.src._run(stdin=stdin, stdout=subprocess.PIPE, stderr=stderr, **kw)
        dst = self.dst._run(stdin=src[-1].pipes['stdout'], stdout=stdout, stderr=stderr, **kw)
        return src + dst

# class Group(Pipeline):
#     def __init__(self, first, second):
#         self.first = first
#         self.second = second
#     def thread_main(self, stdin = None, stdout = None, stderr = None, *arg, **kw):
#         for item in [self.first, self.second]:
#             item.run(stdin=stdin, stdout=stdout, stderr=stderr, **kw).join()
#     def  __repr__(self):
#         return u"%s + %s" % (self.first, self.second)

class Redirect(Pipeline):
    def __init__(self, pipeline, file, filedescr):
        self.pipeline = pipeline
        self.file = file
        self.filedescr = filedescr
    def  __repr__(self):
        if self.filedescr == 'stdin':
            sep = "<"
        elif self.filedescr == 'stdout':
            sep = ">"
        return u"%s %s %s" % (self.first, sep, self.second)
    def _run(self, stdin = None, stdout = None, stderr = None, **kw):
        if self.filedescr == 'stdin':
            stdin = self.file
        elif self.filedescr == 'stdout':
            stdout = self.file
        return self.pipeline._run(stdin=stdin, stdout=stdout, stderr=stderr, **kw)

# Example usage
# for line in env.find(".", name='foo*', type='f') | env.grep("bar.*"):
#    print line

if __name__ == '__main__':
    try:
        e = env
        print "===={test one}===="
        for x in e.ls | e.grep(".py$") | e.sed("s+shell+nanan+g"):
            print x

        print "===={test two}===="
        def somefn():
            yield "foo bar fien\n"
            yield "foo naja hehe\n"
            yield "bar naja fie\n"

        for x in somefn() | e.grep("foo"):
            print x


        print "===={test three}===="
        data = [
            "foo bar fien\n",
            "foo naja hehe\n",
            "bar naja fie\n"
            ]

        print list(data | e.grep("foo"))

        # print "===={test four}===="

        # for x in ((e.echo("hejjo") | e.sed("s+o+FLUFF+g"))
        #            + e.echo("hopp")
        #          ) | e.sed("s+h+nan+g"):
        #     print x
    except:
        import sys, pdb
        sys.last_traceback = sys.exc_info()[2]
        pdb.pm()
