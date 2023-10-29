import unittest
import pieshell
import sys
import os

dirname = os.path.dirname(__file__)
sys.path[0:0] = [dirname]
pieshell.envScope["env"]._cd(dirname)


class TestRepr(unittest.TestCase):
    def test_command_repr(self):
        e = pieshell.env
        l = e.ls('-l') | None
        assert "ls('-l') with 1 --> /dev/null in" in repr(l)
        
    def test_running_command_repr(self):
        e = pieshell.env
        p = (e.ls("-l") | None).run_interactive()
        assert "ls('-l') as" in repr(p)
        assert "with 1 --> /dev/null" in repr(p)
        assert "(exit_code=0)" in repr(p)

    def test_pipe_dir(self):
        e = pieshell.env
        p = e.ls | e.cat
        assert "src" in dir(p)
        assert "dst" in dir(p)
