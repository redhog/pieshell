import os
import sys
import traceback
import glob
import code
import contextlib
import pkg_resources

from . import pipeline
from . import redir
from . import utils
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

    def __init__(self, cwd = None, exports = None, interactive = False, redirects = None):
        """Creates a new environment from scratch. Takes the same
        arguments as __call__."""
        self._exports = exports
        self._interactive = interactive
        self._bashfunctions = {}
        self._scope = None
        self._cwd = os.getcwd()
        if cwd is not None:
            self._cd(cwd)
        if redirects is None:
            redirects = redir.Redirects()
            redirects.redirect(0, 0, borrowed=True)
            redirects.redirect(1, 1, borrowed=True)
            redirects.redirect(2, redir.STRING)
        self._redirects = redirects
        self._clear_dir_cache()
        self.running_pipelines = utils.LineList()
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
        if ("*" not in arg) and ("?" not in arg) and ("[" not in arg):
            return [arg]
        res = glob.glob(self._expand_path(arg))
        if not res: return [arg]
        if self._cwd != "/":
            for idx in range(0, len(res)):
                if res[idx].startswith(self._cwd + "/"):
                    res[idx] = "./" + res[idx][len(self._cwd + "/"):]
        return res
    def _cd(self, cwd):
        cwd = self._expand_path(cwd)
        if not os.path.exists(cwd):
            raise IOError("Path does not exist: %s" % cwd)
        self._cwd = cwd
        if self._interactive:
            os.chdir(cwd)
        return self
    def __call__(self, cwd = None, exports = None, interactive = None, redirects = None):
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
        if redirects is None:
            redirects = self._redirects
        res = type(self)(cwd = self._cwd, exports = exports, interactive = interactive, redirects = redirects)
        if cwd is not None:
            res._cd(cwd)
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
    def _coerce(self, thing, direction):
        if thing is None:
            thing = "/dev/null"
        if isinstance(thing, (str, unicode)):
            thing = redir.Redirect(direction, thing)
        if isinstance(thing, redir.Redirect):
            thing = redir.Redirects(thing, defaults=False)
        if not isinstance(thing, redir.Redirect):
            raise ValueError(type(thing))
        return thing
    def __ror__(self, other):
        """Sets default redirects."""
        self._redirects.register(self._redirects._coerce(other, 'stdin'))
    def __or__(self, other):
        """Sets default redirects."""
        self._redirects.register(self._redirects._coerce(other, 'stdout'))
    def __repr__(self):
        return "[%s:%s]" % (str(id(self))[:3], self._cwd)
    def __str__(self):
        """Prints the current prompt"""
        if self._interactive:
            return "%s:%s >>> " % (str(id(self))[:3], self._cwd)
        else:
            return "[%s:%s]" % (str(id(self))[:3], self._cwd)
    def _clear_dir_cache(self):
        self._dir_cache = None
    def __dir__(self):
        if self._dir_cache is None:
            e = self._exports
            self._dir_cache = []
            paths = e["PATH"].split(":")
            for pth in paths:
                if not pth.startswith("/"):
                    pth = os.path.join(self._cwd, pth)
                self._dir_cache.extend(os.listdir(os.path.abspath(pth)))
            self._dir_cache.extend(pipeline.BuiltinRegistry.builtins.keys())
            self._dir_cache.sort()
        return self._dir_cache
    @contextlib.contextmanager
    def temporary_env(self, env):
        self._scope["env"] = env
        try:
            yield
        finally:
            self._scope["env"] = self
            
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
        if filename.startswith("resource://"):
            path = filename.split("://")[1]
            pkg, path = path.split("/", 1)
            f = pkg_resources.resource_stream(pkg, path)
        else:
            f = open(filename)
        with f as f:
            content = f.read()
        code.InteractiveConsole(locals=self).runsource(content, filename, "exec")

    def execute_expr(self, expr):
        exec(expr, self)

    def _copy_resource(self, resource, dst):
        dstdir = os.path.dirname(dst)
        if not os.path.exists(dstdir):
            os.makedirs(dstdir)
        path = resource.split("://")[1]
        pkg, path = path.split("/", 1)
        with pkg_resources.resource_stream(pkg, path) as inf:
            with open(dst, "wb") as outf:
                outf.write(inf.read())

        
    def execute_startup(self):
        env = self["env"]
        self["R"] = R
        self["Redirect"] = redir.Redirect
        self["TMP"] = redir.TMP
        self["STRING"] = redir.STRING
        self["PIPE"] = redir.PIPE
        self["PipelineError"] = pipeline.running.PipelineError
        self["PipelineInterrupted"] = pipeline.running.PipelineInterrupted
        self["PipelineSuspended"] = pipeline.running.PipelineSuspended
        self["pieshell"] = pieshell
        
        # self.execute_expr("from pieshell import *")
        self["env"] = env
        conf = os.path.expanduser('~/.config/pieshell')
        conf_resource = "resource://pieshell/resources/default_config.pysh"
        try:
            if not os.path.exists(conf):
                self._copy_resource(conf_resource, conf)
        except PermissionError:
            self.execute_file(conf_resource)
        else:
            if os.path.exists(conf):
                self.execute_file(conf)

    def __enter__(self):
        self.ps1 = getattr(sys, "ps1", None)
        sys.ps1 = self

    def __exit__(self, *args, **kw):
        sys.ps1 = self.ps1
    
envScope = EnvScope(env = env(interactive=True))
