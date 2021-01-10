from . import command

class BuiltinRegistry(object):
    builtins = {}

    @classmethod
    def register(cls, builtin_cls):
        cls.builtins[builtin_cls.name] = builtin_cls

    @classmethod
    def get_by_name(cls, name):
        if name not in cls.builtins:
            return None
        return cls.builtins[name]

class Builtin(command.BaseCommand):
    def _run(self, redirects, sess, indentation = ""):
        raise NotImplemented
