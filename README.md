# About

Pieshell is a Python shell environment that combines the
expressiveness of shell pipelines with the prower of python iterators.

It can be used in two major ways:

* As an interactive shell replacing e.g. bash
* As an ordinary python module replacing e.g. subprocess.Popen

# Table of contents

* [As a shell](#as-a-shell)
  * [Executing basic commands](#executing-basic-commands)
  * [Full syntsax for command lines](#full-syntsax-for-command-lines)
  * [Redirects](#redirects)
  * [Interfacing between python functions and shell
    commands](#interfacing-between-python-functions-and-shell-commands)
  * [Environment variables](#environment-variables)
  * [Argument expansion](#argument-expansion)
* [As a python module](#as-a-python-module)
  * [Environment variables](#environment-variables-1)
  * [Argument expansion](#argument-expansion-1)
* [Configuration](#configuration)
* [Copyright](#copyright)


# As a shell

## Executing basic commands

To start pieshell in interactive mode, just run the command pieshell:

    $ pieshell

The interactive pieshell environment supports all normal python syntax.

    140:/home/redhog/Projects/beta/pieshell >>> print 3+4
    7

In addition, you can run programs just like in any shell by writing
their names

    140:/home/redhog/Projects/beta/pieshell >>> ls
    build deps dist LICENSE.txt pieshell pieshell.egg-info README.md
    setup.py

Parameters to programs however have to be given as proper python strings
within parenthesis, like a python function call

    140:/home/redhog/Projects/beta/pieshell >>> ls("-a")
    . .. build deps dist .git .gitignore LICENSE.txt pieshell
    pieshell.egg-info .#README.md README.md setup.py

Piping the standard output of one command to the standard input of
another works just like in bash

    140:/home/redhog/Projects/beta/pieshell >>> ls("-a") | grep("-e", ".py")
    setup.py

Changing directory is done using the command cd:

    140:/home/redhog/Projects/beta/pieshell >>> cd("..")
    140:/home/redhog/Projects/beta >>> 

## Full syntsax for command lines

To execute commands that require a path, for example ones in the
current directory, or commands with a dot in their names

    140:/home/redhog/Projects/beta/pieshell >>> _("./setup.py", "--help")
    Common commands: (see '--help-commands' for more)
    ...

The underscore represents the virtual root command that has no
parameters, not even a command name. In general, there are two
equivalent syntaxes for parameters: as function parameter strings, and
as attribute names. The two syntaxes can be mixed freely. All of the
following are equivalent:

    _("foo", "bar", "fie")
    _.foo("bar", "fie")
    _.foo.bar.fie()
    foo.bar.fie()
    foo.bar.fie

Example usage:

    git.diff("-U")

In addition to these two generic syntaxes, the function call syntax
also supports named parameters, which are converted into
"--name=value" pairs. Note that the order can not be guaranteed as
named parameters are sent around as dictionaries inside python:

    git.diff(unified=4)

## Redirects

Standard out and standard in of a pipeline can be redirected to a file
by piping to or from a string (the filename). As a special case, None
is a short hand for "/dev/null"

    140:/home/redhog/Projects/beta/pieshell >>> ls | "foo"

    140:/home/redhog/Projects/beta/pieshell >>> "foo" | cat
    bar
    build
    deps
    dist
    foo
    LICENSE.txt
    pieshell
    pieshell.egg-info
    README.md
    setup.py

    140:/home/redhog/Projects/beta/pieshell >>> ls | None

Redirects can also be made with a more explicit syntax that allows
redirecting other file descriptors than stdin and stdout:

    139:/home/redhog/Projects/beta/pieshell >>> cat |
      Redirect("stdin", "foo") | Redirect("stdout", "bar")

The constructor for redirect takes the following arguments:

    Redirect(fd, source, flag=None, mode=0777)

fd can be either an int, or one of "stdin", "stdout" and "stderr.
source is either a string filename, or an int file descriptor. flag
and mode have the same semantics as for os.open(). Flags do not have
to be given for stdin, stdout and stderr / fd 0, 1 and 2 and defaults
to os.O_RDONLY or os.O_RDONLY | os.O_CREAT.

## Interfacing between python functions and shell commands

Shell commands are first class python objects, and their input and
output can be interacted with easily from python in the form of
iterators. Iterating over a shell command iterates over the lines of
its standard out

    140:/home/redhog/Projects/beta/pieshell >>> list(ls("-a"))
    ['.', '..', 'build', 'deps', 'dist', '.git', '.gitignore',
     'LICENSE.txt', 'pieshell', 'pieshell.egg-info', '.#README.md',
     'README.md', 'setup.py']
    140:/home/redhog/Projects/beta/pieshell >>> for x in ls("-a"):
    ...   if x.endswith('.py'):
    ...      print x
    ... 
    setup.py

Piping an iterator into a shell command, sends its items as lines to
the standard in of the shell command

    140:/home/redhog/Projects/beta/pieshell >>> list(["foo", "bar.py", "fie.py"] |
      grep("-e", ".py"))
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

## Environment variables

Environment variables are available directly in the shell as
variables, together with any local python variables. In addition, they
are available in the dictionary exports.

    140:/home/redhog/Projects/beta/pieshell >>> LANG
    'en_US.UTF-8'

Assigning to the name of an already exported environment variable
updates the value of that variable.

    140:/home/redhog/Projects/beta/pieshell >>> LANG = "sv_SE.UTF-8"
    140:/home/redhog/Projects/beta/pieshell >>> exports["LANG"]
    'sv_SE.UTF-8'

Assigning to a variable name not already used as an environment
variable creates a local python variable.

    140:/home/redhog/Projects/beta/pieshell >>> foo = "hello"
    140:/home/redhog/Projects/beta/pieshell >>> "foo" in exports
    False
    140:/home/redhog/Projects/beta/pieshell >>> foo
    'hello'

To export a new variable, you have to assign it in the exports
dictionary.

    140:/home/redhog/Projects/beta/pieshell >>> exports["bar"] = "world"
    140:/home/redhog/Projects/beta/pieshell >>> bar
    'world'

## Argument expansion

All parameter strings in commands are subject to expansion unless
wrapped in a call to R(), e.g. R("my * string * here")ñ.

  * "~" and "~username" are expanded using os.path.expanduser()

  * Variable expansion is done using the python % operator on python
    variables as well as environment variables.

  * Pattern matching is done using glob.glob()


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

## Environment variables

Environment variables are available as a dictionary in env._exports.

## Argument expansion

Variable expansion is only done on environment variables, as there is
no way for pieshell to find out about the right scope to do variable
lookups in in any given situation.

# Configuration

When running pieshell in interactive mode it executes
~/.config/pieshell at startup if it exists. This file can be used to
configure the interactive environment the same way ~/.bashrc can be
used to configure the bash shell. For example it can be used to load
python modules, execute shell pipelines or set environment variables.
An example config file is supplied in contrib/cofig.

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
