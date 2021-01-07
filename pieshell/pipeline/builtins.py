import os
import os.path

from . import builtin

class CdBuiltin(builtin.Builtin):
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

builtin.BuiltinRegistry.register(CdBuiltin)


class BashSource(builtin.Builtin):
    """Runs a bash script and imports all environment variables at the
    end of the script.
    """

    name = "bashsource"

    def _run(self, redirects, sess, indentation = ""):
        self._cmd = self._env.bash(
            "-l", "-i", "-c",
            "source '%s'; declare -x > $0" % self._arg[1],
            self.parse_decls)
        return self._cmd._run(redirects, sess, indentation)

    def parse_decls(self, stdin):
        # Parse and load environment variables from bash
        for decl in stdin:
            if decl is None:
                yield; continue
            if "=" not in decl: continue
            name, value = decl[len("declare -x "):].split("=", 1)    
            self._env._exports[name] = value.strip("\"")
        yield

builtin.BuiltinRegistry.register(BashSource)
