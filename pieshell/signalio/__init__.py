try:
    import signalfd
    from .signalfd import *
except:
    print("No signalfd support")
    pass
