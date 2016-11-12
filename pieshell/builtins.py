import os
import os.path

from . import pipeline

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
            "source '%s'; declare -x > $0; declare -f > $1" % self._arg[1],
            self.parse_exports,
            self.store_functions)
        return self._cmd._run(redirects, sess, indentation)

    def store_functions(self, stdin):
        # Save functions
        func_decls = []
        for decl in stdin:
            if decl is None:
                yield; continue
            func_decls.append(decl)
        self._env._exports["bash_functions"] = "\n".join(func_decls)
        yield

    def parse_exports(self, stdin):
        # Parse and load environment variables from bash
        for decl in stdin:
            if decl is None:
                yield; continue
            if "=" not in decl: continue
            name, value = decl[len("declare -x "):].split("=", 1)    
            self._env._exports[name] = value.strip("\"")
        yield

pipeline.BuiltinRegistry.register(BashSource)
