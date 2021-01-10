import unittest
import pieshell
import sys
import os

dir = os.path.dirname(__file__)
sys.path[0:0] = [dir]
pieshell.envScope["env"]._cd(dir)


class TestPipelines(unittest.TestCase):
    def test_simple_pipeline(self):
        import simple_pipeline
        self.assertIn(b"simple_pipeline.pysh", simple_pipeline.output)
        self.assertIn(b"hello world", simple_pipeline.output)
        self.assertEqual(simple_pipeline.foo, 3)

    def test_function_pipeline(self):
        import function_pipeline
        self.assertEqual(function_pipeline.output, [b'Start', b"Read >b'Script run works'<", b'End'])

    def test_argpipe_pipeline(self):
        import argpipe_pipeline
        self.assertIn(b"FOO", argpipe_pipeline.output)
        self.assertIn(b"Read >b'BAR'<", argpipe_pipeline.output[2])

    def test_error_pipeline(self):
        import error_pipeline
        self.assertIsNone(error_pipeline.output)
        self.assertIsNotNone(error_pipeline.error)

    def test_bashsource_pipeline(self):
        import bashsource_pipeline
        #self.assertIn('xxx ()', bashsource_pipeline.env._exports["bash_functions"])
        self.assertIn('yyy', bashsource_pipeline.env._exports)
