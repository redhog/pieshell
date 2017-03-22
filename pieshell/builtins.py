import os
import os.path

from . import pipeline
from . import log

class CdBuiltin(pipeline.Builtin):
    """Change directory to the supplied path.
    """
    name = "cd"

    @property
    def _path(self):
        pth = "~"
        if self._arg[1:]:
            pth = os.path.join(*self._arg[1:])
        return pth

    def _run(self, redirects, sess, indentation = ""):
        self.env._cd(self._path)
        return []

    def __dir__(self):
        if self._arg[1:]:
            pth = self.env._expand_path(self._path)
        else:
            pth = "."
        try:
            return [name for name in os.listdir(pth)
                    if os.path.isdir(os.path.join(pth, name))]
        except:
            return []


pipeline.BuiltinRegistry.register(CdBuiltin)

class ClearDirCacheBuiltin(pipeline.Builtin):
    """Clear the tab completion cache
    """
    name = "clear_dir_cache"

    def _run(self, redirects, sess, indentation = ""):
        self.env._clear_dir_cache()
        return []

    def __dir__(self):
        if self._arg[1:]:
            pth = self.env._expand_path(self._path)
        else:
            pth = "."
        try:
            return [name for name in os.listdir(pth)
                    if os.path.isdir(os.path.join(pth, name))]
        except:
            return []

pipeline.BuiltinRegistry.register(ClearDirCacheBuiltin)


class BashSource(pipeline.Builtin):
    """Runs a bash script and imports all environment variables at the
    end of the script.
    """

    name = "bashsource"

    def _run(self, redirects, sess, indentation = ""):
        self._cmd = self._env.bash(
            "-l", "-i", "-c",
            "source '%s'; echo foo; declare -x > $0; echo bar; declare -f > $1; echo fie" % self._arg[1],
            self.parse_exports,
            self.store_functions)
        return self._cmd._run(redirects, sess, indentation)

    def store_functions(self, stdin):
        # Save functions
        self.func_decls = []
        for idx, decl in enumerate(stdin):
            if idx % 1000 == 0: log.log("STORE FUNCTIONS: %s" % idx, "test")
            if decl is None:
                yield; continue
            self.func_decls.append(decl)
        log.log("ALL FUNCTIONS LOADED", "test")
        self._env._exports["bash_functions"] = "\n".join(self.func_decls)
        yield

    def parse_exports(self, stdin):
        # Parse and load environment variables from bash
        for idx, decl in enumerate(stdin):
            if idx % 1000 == 0: log.log("STORE EXPORTS: %s" % idx, "test")
            if decl is None:
                yield; continue
            if "=" not in decl: continue
            name, value = decl[len("declare -x "):].split("=", 1)    
            self._env._exports[name] = value.strip("\"")
        log.log("ALL EXPORTS LOADED", "test")
        yield

pipeline.BuiltinRegistry.register(BashSource)
