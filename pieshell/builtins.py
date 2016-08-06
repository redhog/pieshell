import os
import os.path

from . import pipeline

class CdBuiltin(pipeline.Builtin):
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
