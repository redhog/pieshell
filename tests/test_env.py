import unittest
import pieshell
import sys
import os

dirname = os.path.dirname(__file__)
sys.path[0:0] = [dirname]
pieshell.envScope["env"]._cd(dirname)


class TestEnv(unittest.TestCase):
    def test_dir(self):
        e = pieshell.env
        assert "ls" in dir(e)

    def test_expand_argument(self):
        assert './pieshell/__init__.py' in pieshell.env._expand_argument("pieshell/*.py")
        
    def test_exports(self):
        s = pieshell.EnvScope(env=pieshell.env())
        s["exports"]["a"] = "hello"
        assert s["a"] == "hello"
        s["a"] = "world"
        assert s["exports"]["a"] == "world"
        s["b"] = "nope"
        assert "b" not in s["exports"]

    def test_keys(self):
        s = pieshell.EnvScope(env=pieshell.env())
        s["exports"]["a"] = "hello"
        s["b"] = "world"
        assert "ls" in s.keys()
        assert "a" in s.keys()
        assert "b" in s.keys()

    def test_execute_expr(self):
        s = pieshell.EnvScope(env=pieshell.env())
        s.execute_expr("res = list(ls)")
        assert "LICENSE.txt" in s["res"]

    def test_copy_resource(self):
        s = pieshell.EnvScope(env=pieshell.env)
        if os.path.exists("/tmp/testfile"):
            os.unlink("/tmp/testfile")
        s._copy_resource(
            "resource://pieshell/resources/default_config.pysh",
            "/tmp/testfile")
        assert os.path.exists("/tmp/testfile")

    def test_execute_startup(self):
        s = pieshell.EnvScope(env=pieshell.env())
        envstr = pieshell.Environment.__str__ # Save the prompt function so other tests don't fail
        s.execute_startup()
        pieshell.Environment.__str__ = envstr
        assert s["Redirect"] == pieshell.Redirect
