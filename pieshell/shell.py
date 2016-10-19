import sys
import os
import code

from . import environ
from . import log
from . import version

# Example usage
# for line in env.find(".", name='foo*', type='f') | env.grep("bar.*"):
#    print line

def main():

    def test():
        try:
            e = env
            print "===={test one}===="
            for x in e.ls | e.grep(".py$") | e.sed("s+shell+nanan+g"):
                print x

            print "===={test two}===="
            def somefn():
                yield "foo bar fien\n"
                yield "foo naja hehe\n"
                yield "bar naja fie\n"

            for x in somefn() | e.grep("foo"):
                print x


            print "===={test three}===="
            data = [
                "foo bar fien\n",
                "foo naja hehe\n",
                "bar naja fie\n"
                ]

            print list(data | e.grep("foo"))

            # print "===={test four}===="

            # for x in ((e.echo("hejjo") | e.sed("s+o+FLUFF+g"))
            #            + e.echo("hopp")
            #          ) | e.sed("s+h+nan+g"):
            #     print x

            print "===={test five}===="

            print list(env.cat(iter(["foo", "bar", "fie"])) | env.cat())

        except:
            import sys, pdb
            sys.last_traceback = sys.exc_info()[2]
            pdb.pm()

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
        print """Usages:

pieshell
pieshell FILE.pysh
pieshell --cmd='any valid pieshell command or python statement'
pieshell --test
pieshell --help
pieshell --version
pieshell --ptpython
    Fancy editing environment based on ptpython (pip install ptpython)
pieshell --log=NAME,NAME,NAME


"""
    elif kws.get("version", False):
        print version.version
    elif kws.get("test", False):
        test()
    else:
        if 'log' in kws:
            for name in kws['log'].split(','):
                log.debug[name] = True

        with environ.envScope:
            environ.envScope["args"] = args
            environ.envScope["kws"] = kws
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
                    code.InteractiveConsole(locals=environ.envScope).interact()

if __name__ == '__main__':
    main()
