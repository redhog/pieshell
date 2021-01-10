import json

def map(func):
    def apply_map(iter):
        for item in iter:
            if item is None:
                yield None
            else:
                yield func(item)
    apply_map.__name__ = "map(%s)" % (func.__name__,)
    return apply_map

def filter(func):
    def apply_filter(iter):
        for item in iter:
            if item is None:
                yield None
            elif func(item):
                yield item
    apply_map.__name__ = "filter(%s)" % (func.__name__,)
    return apply_filter

from_json = map(json.loads)
to_json = map(json.dumps)
