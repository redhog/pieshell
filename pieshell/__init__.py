import pkg_resources

from .iterio import *
from .redir import *
from .pipeline import *
from .environ import *
from .shell import *

with pkg_resources.resource_stream("pieshell", "README.md") as f:
    __doc__ = f.read().decode("utf-8")
    
