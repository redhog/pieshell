from .running import *
from .base import *
from .command import *
from .function import *
from .builtins import *
from .pipe import *
from .redirect import *

# class Group(base.Pipeline):
#     def __init__(self, env, first, second):
#         base.Pipeline.__init__(self, env)
#         self.first = first
#         self.second = second
#     def thread_main(self, stdin = None, stdout = None, stderr = None, *arg, **kw):
#         for item in [self.first, self.second]:
#             item.run(stdin=stdin, stdout=stdout, stderr=stderr, **kw).join()
#     def _repr(self):
#         return u"%s + %s" % (repr(self.first), repr(self.second))
