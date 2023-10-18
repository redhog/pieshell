![Python application](https://github.com/redhog/pieshell/workflows/Python%20application/badge.svg)

# About

Pieshell is a Python shell environment that combines the
expressiveness of shell pipelines with the power of python iterators.

It can be used in two major ways:

* As an interactive shell replacing e.g. bash
* As an ordinary python module replacing e.g. subprocess.Popen

# Table of contents

* [Installation](#installation)
* [As a shell](#as-a-shell)
  * [Executing basic commands](#executing-basic-commands)
  * [Full syntax for command lines](#full-syntax-for-command-lines)
  * [Redirects](#redirects)
  * [Interfacing between python functions and shell
    commands](#interfacing-between-python-functions-and-shell-commands)
  * [Environment variables](#environment-variables)
  * [Argument expansion](#argument-expansion)
  * [Processes](#processes)
  * [Job control](#job-control)
  * [Error handling](#error-handling)
  * [Bashsource](#bashsource)
  * [Asynchronous IO](#asynchronous-io)
* [As a python module](#as-a-python-module)
  * [Environment variables](#environment-variables-1)
  * [Argument expansion](#argument-expansion-1)
  * [Pysh modules](#pysh-modules)
  * [Pysh functions](#pysh-functions)
  * [Eval and exec](#eval-and-exec)
* [Configuration](#configuration)
  * [Changing the prompt](#changing-the-prompt)
* [Builtins](#builtins)
* [External tools](#external-tools)
* [Unit tests](#unit-tests)
* [Copyright](#copyright)


# Installation

    $ pip install pieshell


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

## Full syntax for command lines

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

In addition to these two generic syntaxes, there are two more
specialized syntaxes for options:

The function call syntax also supports named parameters, which are
converted into "--name=value" pairs. Note that the order can not be
guaranteed as named parameters are sent around as dictionaries inside
python:

    git.diff(unified=4)

Short options, like `-U` above do not actually need quotes, and can be
specified inside or outside the function call syntax:

    git.diff(-U, -w)
    git.diff-U-w

Notes for programs with wierd parameter syntax, like `find`: `find`
does not use the standard double minus (`--`) before long options, and
takes the option value as a separate argument, rather than separating
the name and value with `=` like most programs. The above special
syntax for short options actually cover this use case too:

    find(".", -name, "*.py")

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

`fd` can be either an int, or one of `"stdin"`, `"stdout"` and `"stderr"`.

`source` is either a string filename, an int file descriptor or one of
the special values `PIPE`, `TMP` and `STRING`. `PIPE` create a new
pipe which you are required to connect up manually. `TMP` generates a
temporary named file. The filename is available in
`RunningPipeline.processes[].output_files[filedescriptornr].path`.
`STRING` generates a temporary named file, but reads and deletes it
when the pipeline exists, putting its content in
`RunningPipeline.processes[].output_content[filedescriptornr]`.

`flag` and `mode` have the same semantics as for `os.open()`. Flags do
not have to be given for `stdin`, `stdout` and `stderr` / fd `0`, `1`
and `2` and defaults to `os.O_RDONLY` or `os.O_RDONLY | os.O_CREAT`.

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
wrapped in a call to R(), e.g. R("my * string * here").

  * "~" and "~username" are expanded using os.path.expanduser()

  * Variable expansion is done using the python % operator on python
    variables as well as environment variables.

  * Pattern matching is done using glob.glob()

## Processes

A running pipeline is represented by a RunningPipeline instance. This
object is returned by the Pipeline.run() and
Pipeline.run_interactive() methods. In interactive shell mode the
RunningPipeline instance for the last executed pipeline is available
in the last_pipeline variable.

A RunningPipeline instance can be used to extract events and statuses
of the processes involved in the pipeline:

* RunningPipeline.processes is a list of RunningItem instances, each
  representing an external process or a python function.

* RunningPipeline.failed_processes is a list of RunningItem instances
  for those processes in the pipeline that have failed (returned a
  non-zero exit status).

* RunningPipeline.pipeline is a (deep) copy of the original pipeline
  object, with additional run status added, e.g. links to processes,
  exit status etc.

* RunningPipeline.wait() waits for all processes in the pipeline to
  terminate.

A RunningItem instance represents an external process or a python
function:

* RunningItem.cmd points to the part of the
  RunningPipeline.pipeline structure that gave rise to this process.

* RunningItem.is_running is True if the process is still
  running.

* RunningItem.is_failed is True if the process has failed somehow
  (process with non-zero exit status, function threw an exception).

* RunningItem.output_content contains a dictionary of the output of
  any STRING redirection for the process with the file descriptors as
  keys.

* RunningProcess.iohandler.last_event contains a dictionary of the
  members of the last event from the process. The members have the
  same names and meaning as the members of the signalfd_siginfo
  struct, see "man signalfd" for details.

* If `psutil` is installed, a `psutil.Process()` instance is available
  as `RunningProcess.details`, and most of its members and methods are
  available directly as members and methods on the `RunningProcess`
  instance, e.g. `RunningProcess.environ()`, `RunningProcess.exe()`.
 
## Job control

A pipeline can be started in the background by appending `&True`, or
`&None` to do the same and also redirect stdout to /dev/null.

`last_pipeline` can be used to access the backgrounded pipeline.

A running pipeline can be stopped by hitting `CTRL-Z`. A stopped
pipeline can be restarted in the background with any of

    bg
    bg(last_pipeline)
    last_pipeline.restart()

or in the foreground with

   fg
   fg(last_pipeline)
   last_pipeline.wait()

## Error handling

When a pipeline fails, e.g. by one of the involved processes exiting
with a non-zero status, RunningPipeline.wait() and
Pipeline.run_interactive() will throw a PipelineFailed exception after
all processes have exited.

* PipelineFailed.pipeline holds a reference to the RunningPipeline
  instance that generated the exception.

If a pipeline is interrupted with CTRL-C, a PipelineInterrupted is
raised.

* PipelineInterrupted.pipeline holds a reference to the
  RunningPipeline instance.

If you want to catch errors in a script, you can use normal Python
exception handling:

    try:
    except PipelineFailed as e:
        e.pipeline.failed_processes[0].pipeline

## Bashsource

Bash provides the command `source` to run the content of a bash script inside the current shell,
effectively letting an external script update the environment variables of the running shell.
This functionality is often used for setting up local development environments, like `virtualenv`.

Pieshell provides a builtin to emulate this functionality, with bash scripts:

    >>> bashsource("myscript.sh")

will run `myscript.sh` in a bash shell followed by `declare -x`. It parses the output of
`declare -x` and updates `exports` accordingly. As a special case

    >>> bashsource()

will do the same, but without running any script first, esentially
just using whatever variables are set up by your `.bashrc` or
`.profile`.

## Asynchronous IO

All constructs described above to use iterators, can equally well be
used as / with async iterators. Pipelines can be awaited, which runs
them and waits for them to exit. RunningPipelines can be awaited,
which just waits for them to exit.

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

A pipeline can be run in the background (with input/output to the screen) using

    >>>> status = ~(env.ls("-a") | env.grep("-e", "io"))

or in the forground (waiting until it exists)

    >>>> status = +(env.ls("-a") | env.grep("-e", "io"))


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

## Pysh modules

In addition to being able to use pieshell code in ordinary python
modules using this slightly more verbose syntax, pieshell supports
importing modules named modulename.pysh rather than modulename.py.
Pysh modules support the full syntax of the interactive pieshell
console. Pysh modules can be imported using the standard import syntax
as soon as pieshell itself has been imported, and from the interactive
pieshell.

Be aware that you won't get a `NameError` for misspelled variable
names in pyshmodules, but instead a
`pieshell.pipeline.running.PipelineFailed` error, or if not used in a
way that will cause it to run, just a pipeline object stored somewhere
it shouldn't.

## Pysh functions

Sometimes you don't want to extract a bunch of functions to a separate
pysh module, but you'd still like to be able to use the simpler syntax
in them. That's still possible usig the `@pyshfunction` decorator:

    >>> @pieshell.env.pyshfunction
    >>> def foo():
    ...    return list(echo("hello"))

You can use any environment for this, not only the default one like in
the example above.

## Eval and exec

By giving an instance of `pieshell.environ.EnvScope` with an environment
set to interactive as `globals` argument to either `eval` or `exec`, the
full syntax of Pieshell can be used in the string to evaluate/execute.

    >>> scope = pieshell.environ.EnvScope(env=pieshell.env(interactive=True))
    >>> eval("ls()", scope)
    build deps dist LICENSE.txt pieshell pieshell.egg-info README.md
    setup.py

# Configuration

When running pieshell in interactive mode it executes
`~/.config/pieshell` at startup if it exists. This file can be used to
configure the interactive environment the same way `~/.bashrc` can be
used to configure the bash shell. For example it can be used to load
python modules, execute shell pipelines or set environment variables.
An example config file is supplied in
`pieshell/resources/default_config.pysh`.

## Changing the prompt

The prompt that Pieshell uses is generated by the method
`pieshell.Environment.__str__`. This method can be overridden by
assigning a new function to it:

    def prompt(self):
        return "Pieshell> "

Be careful if you run pipelines or other code inside the prompt that
might call repr() as that might lead to an infinite loop of prompt
printing. To solve this, use a thread local variable as a flag to
catch and break any recursion.

# Builtins

While pieshell lets you pipe to and from ordinary python functions,
they don't offer the same syntax and tab-completion as external
commands (e.g. 'myfunction.arg1.arg2(name=value)'), they can't modify
the environment or do fancy redirects. Builtin commands provide all of
this, at the cost of a slightly clumsier syntax:

    class MyMagicBuiltin(pieshell.Builtin):
        """More magic to the people
        """
        name = "magic"

        def _run(self, redirects, sess, indentation = ""):
            # redirects is an instance of pieshell.Redirects
            #
            # sess is an opaque data structure that must be passed to
            # any call to _run() you do yourself from this method (or
            # any function it calls).
            #
            # indentation is a string containing only whitespace, to
            # be prepended to any debug printing lines you print.
            #
            # Returns a list of instances of some pieshell.RunningItem
            # subclass

            self._cmd = self._env.find(
                ".", "-name", "%s.txt" % self._arg[1]) | self._env.tac
            return self._cmd._run(redirects, sess, indentation)


        # Optional for tab completion
        def __dir__(self):
            return ["light", "dark"]
    pipeline.BuiltinRegistry.register(CdBuiltin)

# External tools

A short list of tools that might be usefull together with this project:

* [psutil](http://pythonhosted.org/psutil) - python api for getting ps / top style information about a process
* [ReRedirect](https://github.com/jerome-pouiller/reredirect) - redirect io for an already running process
* [Reptyr](https://github.com/nelhage/reptyr) - move a running process to a new controlling terminal
* [Deptyr](https://github.com/antifuchs/deptyr) - forward output for a new process to another controlling terminal

# Unit tests

To run the unit- and integration tests

    pip install nose2
    nose2 -s tests

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
