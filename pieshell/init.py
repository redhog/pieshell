init_functions = []

def initialize():
    for fn in init_functions:
        fn()

def register(fn):
    init_functions.append(fn)
