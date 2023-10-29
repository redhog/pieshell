import unittest
import pieshell
import sys
import os

dir = os.path.dirname(__file__)
sys.path[0:0] = [dir]
pieshell.envScope["env"]._cd(dir)


class TestRedirection(unittest.TestCase):
    def test_one(self):
        e = pieshell.env
        p = (e.ls | pieshell.Redirect("stdout", pieshell.TMP)).run_interactive()
        assert os.path.exists(p.ls.output_files[1].path)
        p.remove_output_files()
