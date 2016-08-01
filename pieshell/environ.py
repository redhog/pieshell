import os
import sys

from . import pipeline
import traceback
import pieshell

class Environment(object):
    """An environment within which a command or pipeline can run. The
    environment consists of a current working directory and a set of
    environment variables and other configuration.

    Commands within the environment can be convienently created using
    the

        env.COMMAND_NAME

    as a short hand for

        Command(env, "COMMAND_NAME")
    """

    def __init__(self, cwd = None, env = None, interactive = False):
        """Creates a new environment from scratch. Takes the same
        arguments as __call__."""
        self.cwd = os.getcwd()
        if cwd is not None:
            self.cd(cwd)
        self.env = env
        self.interactive = interactive
    def cd(self, cwd):
        if not cwd.startswith("/") and not cwd.startswith("~"):
            cwd = os.path.join(self.cwd, cwd)
        cwd = os.path.expanduser(cwd)
        cwd = os.path.abspath(cwd)
        if not os.path.exists(cwd):
            raise IOError("Path does not exist: %s" % cwd)
        self.cwd = cwd
        if self.interactive:
            os.chdir(cwd)
        return self
    def __call__(self, cwd = None, env = None, interactive = None):
        """Creates a new environment based on the current ones. All
        configuration is copied, unless specifically overridden.

        cwd: Path to current working directory
        env: Dictionary of environment variables
        interactive: Boolean. If true:
            * Changing the current working directory of this
              environment changes the real working directory of the
              current python process using os.chdir().
            * repr() of a pipeline will run the pipeline with
              stdin/stdout/stderr connected to the current terminal,
              and wait until the pipeline terminates.
        """
        if env is None:
            env = self.env
        if interactive is None:
            interactive = self.interactive
        res = type(self)(cwd = self.cwd, env = env, interactive = interactive)
        if cwd is not None:
            res.cd(cwd)
        return res
    def __getitem__(self, name):
        """env[path] is equivalent to env(path)"""
        return self(name)
    def __getattr__(self, name):
        """Creates a pipeline of one command in the current
        environment."""
        return pipeline.Command(self, name)
    def __repr__(self):
        """Prints the current prompt"""
        if self.interactive:
            return "%s:%s >>> " % (str(id(self))[:3], self.cwd)
        else:
            return "[%s:%s]" % (str(id(self))[:3], self.cwd)
    def keys(self):
        e = self.env or os.environ
        res = []
        paths = e["PATH"].split(":")
        for pth in paths:
            if not pth.startswith("/"):
                pth = os.path.join(self.cwd, pth)
            res.extend(os.listdir(os.path.abspath(pth)))
        res.sort()
        return res

env = Environment()

class EnvScope(dict):
    """EnvScope can be used instead of a globals() dictionary to allow
    global lookup of command names, without the env.COMMAND
    prefixing."""
    def __getitem__(self, name):
        try:
            return dict.__getitem__(self, name)
        except KeyError:
            if name in __builtins__:
                raise
            return getattr(dict.__getitem__(self, 'env'), name)

    def keys(self):
        return dict.keys(self) + dict.__getitem__(self, 'env').keys()

    def __str__(self):
        return unicode(self).encode('utf-8')

    def __unicode__(self):
        try:
            return unicode(dict.__getitem__(self, 'env'))
        except Exception, e:
            traceback.print_exc()
            return u'<%s>' % e

    def execute_file(self, filename):
        with open(filename) as f:
            content = f.read()
        exec content in self

    def execute_expr(self, expr):
        exec expr in self

    def execute_startup(self):
        env = self["env"]
        self.execute_expr("from pieshell import *")
        self["env"] = env
        self.execute_expr("import readline")
        conf = os.path.expanduser('~/.config/pieshell')
        if os.path.exists(conf):
            self.execute_file(conf)

    def __enter__(self):
        self.ps1 = getattr(sys, "ps1", None)
        sys.ps1 = self

    def __exit__(self, *args, **kw):
        sys.ps1 = self.ps1

envScope = EnvScope(env = env(interactive=True))
