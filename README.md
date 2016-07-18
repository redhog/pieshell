# Examples

    >>> from pieshell import *

Piping in and out of iterators and between commands:

    >>> env.ls("-a") | env.grep("-e", "io")
    iterio.py
    iterio.pyc
    >>>

    >>> ["foo", "fio", "biob"] | env.grep("-e", "io")
    fio
    biob
    >>>

    >>> for x in ["foo", "fio", "biob"] | env.grep("-e", "io"):
    ...   print 'a' + x
    ... 
    afio
    abiob
    >>> 

Useless use of cat:

    >>> ["foo", "fio", "biob"] | env.grep("-e", "io") | env.cat()
    fio
    biob
    >>>

Changing directory

    >>> env
    140:/home/redhog/Projects/beta/pieshell >>>
    >>> env.cd('..')
    140:/home/redhog/Projects/beta >>>
    >>> env.cd('pieshell/.git')
    140:/home/redhog/Projects/beta/pieshell/.git >>>
    >>> env.ls
    branches
    COMMIT_EDITMSG
    config
    description
    HEAD
    hooks
    index
    info
    logs
    objects
    ORIG_HEAD
    refs
    >>> 
