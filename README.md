# About

Pieshell is a Python shell environment that combines the
expressiveness of shell pipelines with the prower of python iterators.

It can be used in two major ways:

* As an interactive shell replacing e.g. bash
* As an ordinary python module replacing e.g. subprocess.Popen

# As a shell

## Executing basic commands

To start pieshell in interactive mode, just run the command pieshell:

    $ pieshell

The interactive pieshell environment supports all normal python syntax.

    140:/home/redhog/Projects/beta/pieshell >>> print 3+4
    7

In addition, you can run programs just like in any shell by writing their names

    140:/home/redhog/Projects/beta/pieshell >>> ls
    build  deps  dist  LICENSE.txt	pieshell  pieshell.egg-info  README.md	setup.py

Parameters to programs however have to be given as proper python strings
within parenthesis, like a python function call

    140:/home/redhog/Projects/beta/pieshell >>> ls("-a")
    .  ..  build  deps  dist  .git	.gitignore  LICENSE.txt  pieshell  pieshell.egg-info  .#README.md  README.md  setup.py

Piping the standard output of one command to the standard input of
another works just like in bash

    140:/home/redhog/Projects/beta/pieshell >>> ls("-a") | grep("-e", ".py")
    setup.py

Changing directory is done using the command cd just like in any shell

    140:/home/redhog/Projects/beta/pieshell >>> cd("..")
    140:/home/redhog/Projects/beta >>> 

## Interfacing between python functions and shell commands

Shell commands are first class python objects, and their input and
output can be interacted with easily from python in the form of
iterators. Iterating over a shell command iterates over the lines of
its standard out

    140:/home/redhog/Projects/beta/pieshell >>> list(ls("-a"))
    ['.', '..', 'build', 'deps', 'dist', '.git', '.gitignore', 'LICENSE.txt', 'pieshell', 'pieshell.egg-info', '.#README.md', 'README.md', 'setup.py']
    140:/home/redhog/Projects/beta/pieshell >>> for x in ls("-a"):
    ...   if x.endswith('.py'):
    ...      print x
    ... 
    setup.py

Piping an iterator into a shell command, sends its items as lines to
the standard in of the shell command

    140:/home/redhog/Projects/beta/pieshell >>> list(["foo", "bar.py", "fie.py"] | grep("-e", ".py"))
    ['bar.py', 'fie.py']
    140:/home/redhog/Projects/beta/pieshell >>> def foo():
    ...     yield "hello"
    ...     yield "world"
    140:/home/redhog/Projects/beta/pieshell >>> foo() | cat
    hello
    world

In addtion, iterators and pipelines may be used as arguments to
commands and will be seen by the command as a filename, which when
opened and read from will produce the output of that iterator as
lines, or the standard output of the pipeline.

    140:/home/redhog/Projects/beta/pieshell >>> list(cat(["foo", "bar"]))
    ['foo', 'bar']
    140:/home/redhog/Projects/beta/pieshell >>> list(cat(["foo", "bar"] | cat))
    ['foo', 'bar']


# As a python module

    >>> from pieshell import *

All functionality available in the interactive shell is available when
using pieshell as an ordinary python module. However, a slighly more
cumbersome syntax is required.

In particular, shell commands can not be run just by writing their
names. Instead, they have to be accessed as members of the "env"
object:

    >>> list(env.ls("-a") | env.grep("-e", "io"))
    ["iterio.py", "iterio.pyc"]

Commands are also not run with standard out to the screen when simply
printed using the repr() function but must instead be used as
iterators as is done above using the list() function.

The env object holds the current working directory, which can be changed with

    >>> env.cd("..")    

You can also create multiple environments and use them
siumultaneously, even within the same pipeline

    >>> env2 = env()
    >>> env2.cd("somedir")

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
