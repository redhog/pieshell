import psutil
import slugify

class PstreeGroup(object):
    def __init__(self, children, attr):
        procs = {}
        for child in children:
            key = self._getkey(child.details, attr)
            if isinstance(key, int):
                key = attr + "_" + str(key)
            elif isinstance(key, list):
                key = " ".join(key)
            key = slugify.slugify(key, separator="_")
            if key not in procs: procs[key] = {}
            procs[key][str(child.details.pid)] = child
        self.children = {}
        for key, value in procs.items():
            if len(value) == 1:
                self.children[key] = next(iter(value.values()))
            else:
                self.children[key] = PstreeGroup(value.values(), self._nextkey(attr))
    def _getkey(self, proc, attr):
        realattr = attr
        if attr == "name":
            attr = "exe"
        try:
            key = getattr(proc, attr)
            if attr != "pid":
                key = key()
        except psutil.AccessDenied:
            key = self._getkey(proc, self._nextkey(attr))
            if attr == "exe" and isinstance(key, list):
                return key[0]
            return key
        if realattr == "name":
            key = key.split("/")[-1]
        return key
        
    def __dir__(self):
        return self.children.keys()
    def __getattr__(self, key):
        return self.children[key]
    def _nextkey(self, key):
        keys = ["name", "exe", "cmdline", "pid"]
        return keys[keys.index(key) + 1]

class PstreeProcess(object):
    def __init__(self, pid):
        if isinstance(pid, int):
            self.details = psutil.Process(pid)
        else:
            self.details = pid
    @property
    def _children(self):
        try:
            children = self.details.children()
            children = [PstreeProcess(proc) for proc in children]
            return PstreeGroup(children, "name")
        except Exception as e:
            print(e)
            import traceback
            traceback.print_exc()
            import pdb, sys
            sys.last_traceback = sys.exc_info()[2]
            pdb.pm()
        return None
    def __dir__(self):
        return dir(self._children)
    def __getattr__(self, key):
        assert key != "_children"
        return getattr(self._children, key)
    def __repr__(self):
        return " ".join(self.details.cmdline())
        
init = PstreeProcess(1)
