import pieshell
import sys
import os

dir = os.path.dirname(__file__)
sys.path[0:0] = [dir]
pieshell.envScope["env"]._cd(dir)


class TestPipelines:
    def test_simple_pipeline(self):
        import simple_pipeline
        assert "simple_pipeline.pysh" in simple_pipeline.output
        assert "hello world" in simple_pipeline.output
        assert simple_pipeline.foo == 3

    def test_function_pipeline(self):
        import function_pipeline
        assert function_pipeline.output == ['Start', 'Read >Script run works<', 'End']

    def test_argpipe_pipeline(self):
        import argpipe_pipeline
        assert "FOO" in argpipe_pipeline.output
        assert "Read >BAR<" in argpipe_pipeline.output[2]

    def test_error_pipeline(self):
        import error_pipeline
        assert error_pipeline.output is None
        assert error_pipeline.error is not None

    def test_bashsource_pipeline(self):
        import bashsource_pipeline
        assert 'xxx ()' in bashsource_pipeline.env._exports["bash_functions"]
        assert 'yyy' in bashsource_pipeline.env._exports

    def test_multiargpipe_pipeline(self):
        output_a = []
        output_b = []
        def a(stdin):
            for line in stdin:
                if line is None:
                    yield; continue
                output_a.append(line)
        def b(stdin):
            for line in stdin:
                if line is None:
                    yield; continue
                output_b.append(line)
        pieshell.env.bash(
            "-l", "-i", "-c",
            "for ((x=0;x<100;x++)); do echo bar > $1; echo foo > $0; done",
            a, b).run_interactive()
        assert 'foo' in output_a
        assert 'bar' in output_b


    def test_xxx(self):
        exports = {}

        def store_functions(stdin):
            # Save functions
            func_decls = []
            for decl in stdin:
                if decl is None:
                    yield; continue
                func_decls.append(decl)
            exports["bash_functions"] = "\n".join(func_decls)
            yield

        def parse_exports(stdin):
            # Parse and load environment variables from bash
            for decl in stdin:
                if decl is None:
                    yield; continue
                if "=" not in decl: continue
                name, value = decl[len("declare -x "):].split("=", 1)    
                exports[name] = value.strip("\"")
            yield

        pieshell.env.bash(
            "-l", "-i", "-c",
            "echo hej; xxx () { echo hej; }; export yyy=1; declare -x > $0; declare -f > $1",
            parse_exports,
            store_functions).run_interactive()

        assert 'xxx ()' in exports["bash_functions"]
        assert 'yyy' in exports
