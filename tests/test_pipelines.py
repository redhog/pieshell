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
