import os
import fcntl
import select

def _set_cloexec_flag(fd, cloexec=True):
    try:
        cloexec_flag = fcntl.FD_CLOEXEC
    except AttributeError:
        cloexec_flag = 1

    old = fcntl.fcntl(fd, fcntl.F_GETFD)
    if cloexec:
        fcntl.fcntl(fd, fcntl.F_SETFD, old | cloexec_flag)
    else:
        fcntl.fcntl(fd, fcntl.F_SETFD, old & ~cloexec_flag)

def pipe_cloexec():
    """Create a pipe with FDs set CLOEXEC."""
    # Pipes' FDs are set CLOEXEC by default because we don't want them
    # to be inherited by other subprocesses: the CLOEXEC flag is removed
    # from the child's FDs by _dup2(), between fork() and exec().
    # This is not atomic: we would need the pipe2() syscall for that.
    r, w = os.pipe()
    _set_cloexec_flag(r)
    _set_cloexec_flag(w)
    return r, w
