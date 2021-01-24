import sys
import os
import code
import readline

from . import environ
from . import log
from . import version

# Example usage
# for line in env.find(".", name='foo*', type='f') | env.grep("bar.*"):
#    print line

def main():
    args = []
    kws = {}
    for arg in sys.argv[1:]:
        if arg.startswith("--"):
            arg = arg[2:]
            if "=" in arg:
                name, value = arg.split("=", 1)
            else:
                name = arg
                value = True
            kws[name] = value
        else:
            args.append(arg)

    if kws.get("help", False):
        print("""Usage:

pieshell [OPTIONS] [ACTION]

Where ACTION is any of
  --help
    Show this help
  --version
    Show version information
  FILE.pysh
    Execute the given file
  --cmd='any valid pieshell command or python statement'
    Execute the commandline or python statement

Where OPTIONS are any of
  --ptpython
    Fancy editing environment based on ptpython (pip install ptpython)
  --log=NAME,NAME,NAME
    Turn on logging of classes of events
  --no-startup
    Do not run ~/.config/pieshell at startup
""")
    elif kws.get("version", False):
        print(version.version)
    else:
        if 'log' in kws:
            for name in kws['log'].split(','):
                log.debug[name] = True

        with environ.envScope:
            environ.envScope["args"] = args
            environ.envScope["kws"] = kws

            if not kws.get("no-startup", False):
                environ.envScope.execute_startup()

            if "cmd" in kws:
                environ.envScope.execute_expr(kws["cmd"])
            elif args:
                for arg in args:
                    environ.envScope.execute_file(arg)
            else:
                if kws.get("ptpython", False):
                    import pieshell.monkeypatches.patch_jedi
                    import ptpython.repl

                    import pygments.token
                    import ptpython.prompt_style
                    def in_tokens(self, cli):
                        return [(pygments.token.Token.Prompt, str(environ.envScope))]
                    ptpython.prompt_style.ClassicPrompt.in_tokens = in_tokens

                    ptpython.repl.embed(locals=environ.envScope, vi_mode=False)
                else:
                    import pieshell
                    code.InteractiveConsole(locals=environ.envScope).interact(banner=pieshell.banner, exitmsg="...om nom nom")

if __name__ == '__main__':
    main()
