# Minimal reimplementation of copy.deepcopy that happily copies
# objects inheriting from type...
import threading
import contextlib

copy_state = threading.local()

@contextlib.contextmanager
def copy_session(sess = None):
    old_memo = getattr(copy_state, "memo", None)
    if sess:
        copy_state.memo = sess
    else:
        copy_state.memo = old_memo or {}
    try:
        yield copy_state.memo
    finally:
        copy_state.memo = old_memo

def deepcopy(obj):
    with copy_session() as memo:
        key = id(obj)
        if key not in memo:
            if isinstance(obj, (list, tuple)):
                memo[key] = type(obj)(deepcopy(item) for item in obj)
            elif isinstance(obj, dict):
                memo[key] = type(obj)({deepcopy(key):deepcopy(value) for key, value in obj.iteritems()})
            elif isinstance(obj, str):
                memo[key] = str(obj)
            elif isinstance(obj, unicode):
                memo[key] = unicode(obj)
            elif hasattr(obj, "__deepcopy__"):
                memo[key] = obj.__deepcopy__()
            else:
                memo[key] = obj
        return memo[key]
