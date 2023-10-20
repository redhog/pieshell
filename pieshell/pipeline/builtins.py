import os
import os.path
import shlex
import io
import asyncio

from . import builtin
from . import running

class CdBuiltin(builtin.Builtin):
    """Change directory to the supplied path.
    """
    name = "cd"

    @property
    def _path(self):
        pth = "~"
        if self._arg[1:]:
            pth = os.path.join(*self._arg[1:])
        return pth

    def _run(self, redirects, sess, indentation = ""):
        self._env._cd(self._path)
        return []

    def __dir__(self):
        if self._arg[1:]:
            pth = self._env._expand_path(self._path)
        else:
            pth = "."
        try:
            return [name for name in os.listdir(pth)
                    if os.path.isdir(os.path.join(pth, name))]
        except:
            return []

builtin.BuiltinRegistry.register(CdBuiltin)

class BgBuiltin(builtin.Builtin):
    """Continue running the last pipeline in the background.
    """
    name = "bg"

    def _run(self, redirects, sess, indentation = ""):
        pipeline = self._env.last_pipeline
        if len(self._arg) > 1:
            pipeline = self._arg[1]
        pipeline.restart()
        return []
builtin.BuiltinRegistry.register(BgBuiltin)

class RunnningFg(running.BaseRunningItem):
    def __init__(self, pipeline):
        self.wrapped_pipeline = pipeline
        asyncio.get_event_loop().create_task(self.await_finish())
    @property
    def is_running(self):
        return self.wrapped_pipeline.is_running
    @property
    def is_failed(self):
        return self.wrapped_pipeline.is_failed
    async def await_finish(self):
        await self.wrapped_pipeline.wait()
        self.running_pipeline.handle_finish()
    
class FgBuiltin(builtin.Builtin):
    """Continue running the last pipeline in the background.
    """
    name = "fg"

    def _run(self, redirects, sess, indentation = ""):
        pipeline = self._env.last_pipeline
        if len(self._arg) > 1:
            pipeline = self._arg[1]
        return [RunnningFg(pipeline)]
builtin.BuiltinRegistry.register(FgBuiltin)

class ClearDirCacheBuiltin(builtin.Builtin):
    """Clear the tab completion cache
    """
    name = "clear_dir_cache"

    def _run(self, redirects, sess, indentation = ""):
        self.env._clear_dir_cache()
        return []

    def __dir__(self):
        if self._arg[1:]:
            pth = self.env._expand_path(self._path)
        else:
            pth = "."
        try:
            return [name for name in os.listdir(pth)
                    if os.path.isdir(os.path.join(pth, name))]
        except:
            return []

builtin.BuiltinRegistry.register(ClearDirCacheBuiltin)

def parse_declares(data):
    l = shlex.shlex(io.StringIO(data), posix=True)

    l.whitespace_split = True

    lastlineno = 1
    line = []
    lines = []
    while True:
        if l.lineno != lastlineno:
            lines.append((lastlineno, line))
            line = []
        lastlineno = l.lineno
        token = l.get_token()
        if token is None:
            break
        line.append(token)

    vars = {}
    funcstarts = []
    for (lineno, line) in lines:
        if line[0] == "declare":
            name = line[2]
            if "=" in name:
                name, value = name.split("=", 1)
            else:
                value = ""
            vars[name] = value
        elif len(line) == 3 and line[1] == '()' and line[2] == '{':
            funcstarts.append((lineno, line[0]))

    lines = data.split("\n")
    funcs = {}
    for i in range(len(funcstarts)):
        if i >= len(funcstarts) - 1:
            flines = lines[funcstarts[i][0]-1:]
        else:
            flines = lines[funcstarts[i][0]-1:funcstarts[i+1][0]-1]
        funcs[funcstarts[i][1]] = "\n".join(flines)

    return vars, funcs

class BashSource(builtin.Builtin):
    """Runs a bash script and imports all environment variables at the
    end of the script.
    """

    name = "bashsource"

    def _run(self, redirects, sess, indentation = ""):
        args = []
        for arg in self._arg[1:]:
            for exp in self._env._expand_argument(arg):
                args.append("source '%s'" % (exp,))
        args.append("{ declare -x; declare -f; } > $0")
        self._cmd = self._env.bash(
            "-l", "-i", "-c",
            "; ".join(args),
            self.parse_decls)
        res = self._cmd._run(redirects, sess, indentation)
        #self._pid = self._cmd._pid
        self._redirects = self._cmd._redirects
        return res
    
    async def parse_decls(self, stdin):
        # Parse and load environment variables from bash
        lines = []        
        async for line in stdin:
            lines.append(line)
        lines = "\n".join(lines)
        vars, funcs = parse_declares(lines)
        self._env._exports.update(vars)
        self._env._bashfunctions.update(funcs)

builtin.BuiltinRegistry.register(BashSource)
