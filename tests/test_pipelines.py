import pieshell
import sys
import os

dirname = os.path.dirname(__file__)
sys.path[0:0] = [dirname]
pieshell.envScope["env"]._cd(dirname)


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

    def DISABLEDtest_bashsource_pipeline(self):
        import bashsource_pipeline
        assert 'xxx ()' in bashsource_pipeline.env._exports["bash_functions"]
        assert 'yyy' in bashsource_pipeline.env._exports
