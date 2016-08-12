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
        if self.arg[1:]:
            pth = os.path.join(*self.arg[1:])
        return pth

    def _run(self, redirects, sess, indentation = ""):
        self.env._cd(self._path)
        return []

    def __dir__(self):
        if self.arg[1:]:
            pth = self.env._expand_path(self._path)
        else:
            pth = "."
        try:
            return [name for name in os.listdir(pth)
                    if os.path.isdir(os.path.join(pth, name))]
        except:
            return []

pipeline.Builtin.register(CdBuiltin)


class BashSource(pipeline.Builtin):
    """Runs a bash script and imports all environment variables at the
    end of the script.
    """

    name = "bashsource"

    def _run(self, redirects, sess, indentation = ""):
        self.cmd = self.env.bash(
            "-l", "-i", "-c",
            "source '%s'; declare -x > $0" % self.arg[1],
            self.parse_decls)
        return self.cmd._run(redirects, sess, indentation)

    def parse_decls(self, stdin):
        # Parse and load environment variables from bash
        for decls in stdin:
            if "=" not in decl: continue
            name, value = decl[len("declare -x "):].split("=", 1)    
            self.env.env[name] = value.strip("\"")

pipeline.Builtin.register(BashSource)
