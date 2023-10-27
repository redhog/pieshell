import pkg_resources
import importlib

from .iterio import *
from .signalio import *
from .redir import *
from .pipeline import *
from .environ import *
from .shell import *
from .module import *
from .utils import *
from .ps import *
from .version import *
import builtins as __pieshell_builtins

name = "PieShell %s <)" % (version,)

with pkg_resources.resource_stream("pieshell", "README.md") as f:
    __doc__ = "%s\n\n%s" % (name, f.read().decode("utf-8"))

banner = """%s
Python %s
Type help(pieshell) for more information.""" % (name, sys.version.replace("\n", " "),)

for entry in importlib.metadata.entry_points()['pieshell.builtin']:
    BuiltinRegistry.register(entry.load(), entry.name)
