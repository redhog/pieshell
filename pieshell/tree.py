import slugify

class TreeGroup(object):
    def __init__(self, children, level=0):
        procs = {}
        for child in children:
            key = child._getkey(level)
            key = slugify.slugify(key, separator="_")            
            if key not in procs: procs[key] = {}
            procs[key][child._getkey(None)] = child
        self.children = {}
        for key, value in procs.items():
            if len(value) == 1:
                self.children[key] = next(iter(value.values()))
            else:
                self.children[key] = TreeGroup(value.values(), level+1)        
    def __dir__(self):
        return self.children.keys()
    def __getattr__(self, key):
        return self.children[key]
