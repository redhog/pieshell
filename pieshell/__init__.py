import pkg_resources

from .iterio import *
from .signalio import *
from .redir import *
from .pipeline import *
from .environ import *
from .shell import *
from .module import *
from .utils import *
from .version import *
import builtins as __pieshell_builtins

name = "PieShell %s <)" % (version,)

with pkg_resources.resource_stream("pieshell", "README.md") as f:
    __doc__ = "%s\n\n%s" % (name, f.read().decode("utf-8"))

banner = """%s
Python %s
Type help(pieshell) for more information.""" % (name, sys.version.replace("\n", " "),)
