import sys
import os
import types
import environ

class Module(types.ModuleType):
    def __init__(self, scope, name, doc = None):
        types.ModuleType.__setattr__(self, "_scope", scope)
        super(Module, self).__init__(name, doc)
    def __getattr__(self, name):
        return self._scope[name]
    def __setattr__(self, name, value):
        self._scope[name] = value
    def __dir__(self):
        return dict.keys(self._scope)

class Loader(object):
    def __init__(self, path):
        self.path = path
    def load_module(self, fullname):
        if fullname not in sys.modules:
            env = environ.envScope["env"]()
            scope = environ.EnvScope(env=env)
            sys.modules[fullname] = Module(scope, fullname.split(".")[-1])
        sys.modules[fullname]._scope.execute_file(self.path)
        return sys.modules[fullname]

class Finder(object):
    def find_module(self, fullname, path=None):
        filename = fullname.split(".")[-1] + ".pysh"
        paths = sys.path
        if path is not None:
            paths = path
        if not isinstance(paths, (list, tuple)):
            paths = [paths]
        found = None
        for path in paths:
            if path == "": path = "."
            filepath = os.path.join(path, filename)
            if os.path.exists(filepath):
                found = filepath
                break
        if found is None:
            return None
        return Loader(found)

sys.meta_path.append(Finder())
