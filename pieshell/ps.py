import slugify
import os
from . import tree
try:
    import psutil
except:
    psutil = None

def cmdline2pieshell(cmdline):
    param = False
    names = []
    args = []
    kwargs = {}
    for item in cmdline:
        if slugify.slugify(item, separator="_") != item:
            param = True
        if not param:
            names.append(item)
        elif item.startswith("--") and "=" in item:
            k, v = item[2:].split("=", 1)
            kwargs[k] = v
        elif item.startswith("-") and not item.startswith("--"):
            args.append(item)
        else:
            args.append(repr(item))
    if not len(names):
        names = ["_"]
    res = ".".join(names)
    if args or kwargs:
        res = ".".join(names) + "(" + ", ".join(args + [k + "=" + v for k, v in kwargs.items()]) + ")"
    return res

class PstreeProcess(object):
    _keys = ["name", "exe", "cmdline", "pid"]
    
    def __init__(self, pid):
        if isinstance(pid, int):
            self.INFO = psutil.Process(pid)
        else:
            self.INFO = pid

    def _getkey(self, level):
        if level == None:
            realattr = attr = "pid"
        else:
            realattr = attr = self._keys[level]
        if attr == "name":
            attr = "exe"
        try:
            key = getattr(self.INFO, attr)
            if attr != "pid":
                key = key()
        except psutil.AccessDenied:
            key = self._getkey(level+1)
            if attr == "exe" and isinstance(key, list):
                key = key[0]
        else:
            if realattr == "name":
                key = key.split("/")[-1]            
        if isinstance(key, int):
            key = attr + "_" + str(key)
        elif isinstance(key, list):
            key = " ".join(key)
        return key
    
    @property
    def _children(self):
        try:
            children = self.INFO.children()
            children = [PstreeProcess(proc) for proc in children]
            return tree.TreeGroup(children)
        except Exception as e:
            print(e)
            import traceback
            traceback.print_exc()
            import pdb, sys
            sys.last_traceback = sys.exc_info()[2]
            pdb.pm()
        return None
    @property
    def PARENT(self):
        return PstreeProcess(self.INFO.parent())
    @property
    def GROUP(self):
        return PstreeProcess(os.getpgid(self.INFO.pid))
    @property
    def SESS(self):
        return PstreeProcess(os.getsid(self.INFO.pid))
    def __dir__(self):
        return dir(self._children)
    def __getattr__(self, key):
        assert key != "_children"
        try:
            return getattr(self._children, key)
        except:
            return getattr(self.INFO, key)
    def __len__(self):
        return len(self.INFO.threads())
    def __getitem__(self, idx):
        return self.INFO.threads()[idx]
    def __iter__(self, idx):
        return iter(self.INFO.threads())
    def __repr__(self):
        return "%s as %s" % (cmdline2pieshell(self.INFO.cmdline()), self.INFO.pid)

class PstreeLogin(object):
    def __init__(self, details):
        self.details = details
        self.process = PstreeProcess(details.pid)

    def __dir__(self):
        return dir(self.process)
    
    def __getattr__(self, key):
        try:
            return getattr(self.process, key)
        except:
            return getattr(self.details, key)

    def _getkey(self, level):
        if level == 0:
            return self.details.name
        elif level == 1:
            return self.details.host
        return self.process._getkey(level - 2 if level is not None else None)
        
class PstreeLogins(object):
    @property
    def _children(self):
        return tree.TreeGroup([PstreeLogin(login) for login in psutil.users()])
    def __dir__(self):
        return dir(self._children)
    def __getattr__(self, key):
        assert key != "_children"
        return getattr(self._children, key)

USERS = PstreeLogins()
    
CURRENT = PstreeProcess(psutil.Process())
INIT = PstreeProcess(1)


