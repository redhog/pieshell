# About

Pieshell is a Python shell environment and library that combines the
expressiveness of shell pipelines with the prower of python iterators.

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

# Copyright

Pieshell copyright 2016 Egil Möller <egil.moller@piratpartiet.se>

Pieshell is free software: you can redistribute it and/or modify it
under the terms of the GNU Lesser General Public License as published
by the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU Lesser General Public
License along with this program. If not, see
<http://www.gnu.org/licenses/>.
