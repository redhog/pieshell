from cmdline import *
import sys
import os

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

"""
    elif kws.get("test", False):
        test()
    else:
        with InteractiveConsole() as console:
            console.push('import readline')
            conf = os.path.expanduser('~/.config/pieshell')
            if os.path.exists(conf):
                console.exec_file(conf)
            if "cmd" in kws:
                console.push(kws["cmd"])
            elif args:
                for arg in args:
                    console.exec_file(arg)
            else:
                console.interact()

if __name__ == '__main__':
    main()
