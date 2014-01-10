import subprocess
import threading
import os
import fcntl
import types

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
        return self
    def next(self):
        try:
            return self.processes[-1].stdout.next()
        except StopIteration, e:
            self.processes[-1].stdout.close()
            raise

class Pipeline(ShellScript):
    def _coerce(self, thing):
        if isinstance(thing, Pipeline):
            return thing
        elif isinstance(thing, types.FunctionType):
            return Function(thing)
        elif hasattr(thing, "next"):
            return Function(lambda stdin, stdout, stderr: thing)
        elif hasattr(thing, "__iter__"):
            return Function(lambda stdin, stdout, stderr: iter(thing))
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
    def run(self, stdin = None, stdout = None, stderr = None, **kw):
        return RunningPipeline(self._run(stdin = stdin, stdout = stdout, stderr = stderr, **kw))
    def __call__(self, stdin = None, stdout = subprocess.PIPE, stderr = None, **kw):
        return self.run(stdin=stdin, stdout=stdout, stderr=stderr, **kw)
    def __iter__(self):
        return self.run(stdout=subprocess.PIPE)

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
    def _run(self, stdin = None, stdout = None, stderr = None, **kw):
        args = [self.name]
        if self.arg:
            args += list(self.arg)
        if self.kw:
            args += ["--%s=%s" % (name, value) for (name, value) in self.kw.iteritems()]
        return [subprocess.Popen(args, stdin=stdin, stdout=stdout, stderr=stderr, cwd=env.cwd, env=env.env, **kw)]

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
        return u"%s.%s.%s(%s)" % (self.function.__module__, self.function.func_name, ', '.join(args))
    def _set_cloexec_flag(self, fd, cloexec=True):
        try:
            cloexec_flag = fcntl.FD_CLOEXEC
        except AttributeError:
            cloexec_flag = 1

        old = fcntl.fcntl(fd, fcntl.F_GETFD)
        if cloexec:
            fcntl.fcntl(fd, fcntl.F_SETFD, old | cloexec_flag)
        else:
            fcntl.fcntl(fd, fcntl.F_SETFD, old & ~cloexec_flag)
    def pipe_cloexec(self):
        """Create a pipe with FDs set CLOEXEC."""
        # Pipes' FDs are set CLOEXEC by default because we don't want them
        # to be inherited by other subprocesses: the CLOEXEC flag is removed
        # from the child's FDs by _dup2(), between fork() and exec().
        # This is not atomic: we would need the pipe2() syscall for that.
        r, w = os.pipe()
        self._set_cloexec_flag(r)
        self._set_cloexec_flag(w)
        return r, w
    def _run(self, stdin = None, stdout = None, stderr = None, **kw):
        thkw = dict(self.kw)
        thkw.update(kw)
        thkw['stdin'] = stdin
        thkw['stdout'] = stdout
        thkw['stderr'] = stderr
        pipes = {}
        for key in ('stdin', 'stdout', 'stderr'):
            if thkw[key] is subprocess.PIPE:
                r, w = self.pipe_cloexec()
                if key == 'stdin':
                    pipes[key], thkw[key] = w, os.fdopen(r, "r")
                else:
                    thkw[key], pipes[key] = os.fdopen(w, "w"), r
        def fnwrapper(stdin, stdout, stderr, *arg, **kw):
            res = self.function(stdin=stdin, stdout=stdout, stderr=stderr, *arg, **kw)
            # Handle iterators:
            if hasattr(res, "next"):
                for x in res:
                    if isinstance(x, str):
                        stdout.write(x)
                    elif isinstance(x, unicode):
                        stdout.write(x.encode("utf-8"))
                    else:
                        stdout.write((unicode(x) + "\n").encode("utf-8"))
        th = threading.Thread(target=fnwrapper, args=self.arg, kwargs=thkw)
        th.start()
        for key, value in pipes.iteritems():
            setattr(th, key, value)
        return [th]

class Pipe(Pipeline):
    def __init__(self, src, dst):
        self.src = src
        self.dst = dst
    def __repr__(self):
        return u"%s | %s" % (self.src, self.dst)
    def _run(self, stdin = None, stdout = None, stderr = None, **kw):
        src = self.src._run(stdin=stdin, stdout=subprocess.PIPE, stderr=stderr, **kw)
        dst = self.dst._run(stdin=src[-1].stdout, stdout=stdout, stderr=stderr, **kw)
        return src + dst

class Group(Pipeline):
    def __init__(self, first, second):
        self.first = first
        self.second = second
    def  __repr__(self):
        return u"%s + %s" % (self.first, self.second)

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
