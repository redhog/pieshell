import os
import sys
import traceback
import glob

from . import pipeline
import pieshell


class R(object):
    """Wraps a string and protects it from path expansions"""
    def __init__(self, str):
        self.str = str
    def __getattr__(self, name):
        return getattr(self.str, name)
    def __iter__(self):
        return iter(self.str)
    def __repr__(self):
        return "R(%s)" % (repr(self.str),)

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

    def __init__(self, cwd = None, exports = None, interactive = False):
        """Creates a new environment from scratch. Takes the same
        arguments as __call__."""
        self._cwd = os.getcwd()
        if cwd is not None:
            self._cd(cwd)
        self._exports = exports
        self._interactive = interactive
        self._scope = None
    @property
    def _exports(self):
        return self._exports_value or os.environ
    @_exports.setter
    def _exports(self, exports):
        self._exports_value = exports
    @_exports.deleter
    def _exports(self):
        self._exports_value = None
    def _expand_path(self, pth):
        if not pth.startswith("/") and not pth.startswith("~"):
            pth = os.path.join(self._cwd, pth)
        pth = os.path.expanduser(pth)
        pth = os.path.abspath(pth)
        return pth
    def _expand_argument(self, arg):
        """Performs argument glob expansion on an argument string.
        Returns a list of strings.
        """
        if isinstance(arg, R): return [arg.str]
        scope = self._scope or self._exports
        arg = arg % scope
        arg = os.path.expanduser(arg)
        relative = not arg.startswith("/")
        res = glob.glob(self._expand_path(arg))
        if not res: res = [arg]
        if self._cwd != "/":
            for idx in range(0, len(res)):
                if res[idx].startswith(self._cwd + "/"):
                    res[idx] = res[idx][len(self._cwd + "/"):]
        return res
    def _cd(self, cwd):
        cwd = self._expand_path(cwd)
        if not os.path.exists(cwd):
            raise IOError("Path does not exist: %s" % cwd)
        self._cwd = cwd
        if self._interactive:
            os.chdir(cwd)
        return self
    def __call__(self, cwd = None, exports = None, interactive = None):
        """Creates a new environment based on the current ones. All
        configuration is copied, unless specifically overridden.

        cwd: Path to current working directory
        exports: Dictionary of environment variables
        interactive: Boolean. If true:
            * Changing the current working directory of this
              environment changes the real working directory of the
              current python process using os.chdir().
            * repr() of a pipeline will run the pipeline with
              stdin/stdout/stderr connected to the current terminal,
              and wait until the pipeline terminates.
        """
        if exports is None:
            exports = self._exports
        if interactive is None:
            interactive = self._interactive
        res = type(self)(cwd = self._cwd, exports = exports, interactive = interactive)
        if cwd is not None:
            res.cd(cwd)
        return res
    def __getitem__(self, name):
        """env[path] is equivalent to env(path)"""
        return self(name)
    def __getattr__(self, name):
        """Creates a pipeline of one command in the current
        environment."""
        if name == "_":
            return pipeline.command.BaseCommand(self)
        else:
            return pipeline.command.BaseCommand(self, [name])
    def __repr__(self):
        """Prints the current prompt"""
        if self._interactive:
            return "%s:%s >>> " % (str(id(self))[:3], self._cwd)
        else:
            return "[%s:%s]" % (str(id(self))[:3], self._cwd)
    def __dir__(self):
        e = self._exports
        res = []
        paths = e["PATH"].split(":")
        for pth in paths:
            if not pth.startswith("/"):
                pth = os.path.join(self._cwd, pth)
            res.extend(os.listdir(os.path.abspath(pth)))
        res.sort()
        return res

env = Environment()

class EnvScope(dict):
    """EnvScope can be used instead of a globals() dictionary to allow
    global lookup of command names, without the env.COMMAND
    prefixing."""
    def __setitem__(self, name, value):
        # Hack for ptpython
        if name == "_":
            name = "last_statement"
        if name == "env":
            value._scope = self
        env = dict.__getitem__(self, 'env')
        if name in env._exports:
            env._exports[name] = value
        else:
            dict.__setitem__(self, name, value)
    def __getitem__(self, name):
        try:
            return dict.__getitem__(self, name)
        except KeyError:
            pass
        env = dict.__getitem__(self, 'env')
        if name != "_":
            if name == "exports":
                return env._exports
            if name in env._exports:
                return env._exports[name]
            if name in __builtins__:
                raise KeyError(name)
        return getattr(env, name)

    def keys(self):
        return dict.keys(self) + dir(dict.__getitem__(self, 'env'))

    def __bytes__(self):
        return str(self).encode("utf-8")
    
    def __str__(self):
        try:
            return str(dict.__getitem__(self, 'env'))
        except Exception as e:
            traceback.print_exc()
            return '<%s>' % e

    def execute_file(self, filename):
        with open(filename) as f:
            content = f.read()
        exec(content, self)

    def execute_expr(self, expr):
        exec(expr, self)

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
