import psutil
import slugify
import os

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

class PstreeGroup(object):
    def __init__(self, children, level=0):
        procs = {}
        for child in children:
            key = child._getkey(level)
            key = slugify.slugify(key, separator="_")            
            if key not in procs: procs[key] = {}
            procs[key][str(child.INFO.pid)] = child
        self.children = {}
        for key, value in procs.items():
            if len(value) == 1:
                self.children[key] = next(iter(value.values()))
            else:
                self.children[key] = PstreeGroup(value.values(), level+1)        
    def __dir__(self):
        return self.children.keys()
    def __getattr__(self, key):
        return self.children[key]

class PstreeProcess(object):
    _keys = ["name", "exe", "cmdline", "pid"]
    
    def __init__(self, pid):
        if isinstance(pid, int):
            self.INFO = psutil.Process(pid)
        else:
            self.INFO = pid

    def _getkey(self, level):
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
            return PstreeGroup(children)
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
        return getattr(self._children, key)
    def __repr__(self):
        return "%s [%s]" % (cmdline2pieshell(self.INFO.cmdline()), self.INFO.pid)

CURRENT = PstreeProcess(psutil.Process())
INIT = PstreeProcess(1)


