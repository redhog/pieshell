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
        self.assertIn("simple_pipeline.pysh", simple_pipeline.output)
        self.assertIn("hello world", simple_pipeline.output)
        self.assertEqual(simple_pipeline.foo, 3)

    def test_function_pipeline(self):
        import function_pipeline
        self.assertEqual(function_pipeline.output, ['Start', "Read >Script run works<", 'End'])

    def test_argpipe_pipeline(self):
        import argpipe_pipeline
        self.assertIn("FOO", argpipe_pipeline.output)
        self.assertIn("Read >BAR<", argpipe_pipeline.output[2])

    def test_error_pipeline(self):
        import error_pipeline
        self.assertIsNone(error_pipeline.output)
        self.assertIsNotNone(error_pipeline.error)

    def test_bashsource_pipeline(self):
        import bashsource_pipeline
        #self.assertIn('xxx ()', bashsource_pipeline.env._exports["bash_functions"])
        self.assertIn('yyy', bashsource_pipeline.env._exports)

    def test_string_parallel(self):
        list(pieshell.env.cat(pieshell.env.ls, pieshell.env.ls))
        
    def test_one(self):
        e = pieshell.env
        for x in e.ls | e.grep(".py$") | e.sed("s+shell+nanan+g"):
            pass

    def test_two(self):
        e = pieshell.env
        def somefn():
            yield "foo bar fien\n"
            yield "foo naja hehe\n"
            yield "bar naja fie\n"
        for x in somefn() | e.grep("foo"):
            pass

    def test_three(self):
        e = pieshell.env
        data = [
            "foo bar fien\n",
            "foo naja hehe\n",
            "bar naja fie\n"
            ]
        list(data | e.grep("foo"))

    def disabled_test_four(self):
        e = pieshell.env
        for x in ((e.echo("hejjo") | e.sed("s+o+FLUFF+g"))
                   + e.echo("hopp")
                 ) | e.sed("s+h+nan+g"):
            pass

    def test_five(self):
        e = pieshell.env
        list(e.cat(iter(["foo", "bar", "fie"])) | e.cat())

    def test_multi_pipe_input(self):
        e = pieshell.env
        list(e.cat(e.ls, e.ls))
