import unittest
import pieshell.iterio
import sys
import os
import asyncio


class TestIterio(unittest.TestCase):
    def test_input_handler(self):
        r, w = os.pipe()

        def gen():
            while True:
                yield b'hello'
        pieshell.iterio.OutputHandler(w, iter(gen()))        
        ih = pieshell.iterio.InputHandler(r)
        ihi = asyncio.get_event_loop().run_until_complete(ih.__aiter__())
        assert b"hello" in asyncio.get_event_loop().run_until_complete(ihi.__anext__())
        assert b"hello" in asyncio.get_event_loop().run_until_complete(ihi.__anext__())

    def test_line_input_handler(self):
        r, w = os.pipe()

        def gen():
            a = 0
            while True:
                yield b'hello ' + str(a).encode("ascii")
                a += 1
        pieshell.iterio.LineOutputHandler(w, iter(gen()))        
        ih = pieshell.iterio.LineInputHandler(r)
        ihi = asyncio.get_event_loop().run_until_complete(ih.__aiter__())
        assert asyncio.get_event_loop().run_until_complete(ihi.__anext__()) == "hello 0"
        assert asyncio.get_event_loop().run_until_complete(ihi.__anext__()) == "hello 1"

    def test_run(self):
        ls = pieshell.env.echo("hello").run([pieshell.redir.Redirect("stdout", pieshell.redir.PIPE)])
        ih = asyncio.get_event_loop().run_until_complete(ls.__aiter__())
        res = asyncio.get_event_loop().run_until_complete(ih.__anext__())
        assert res == "hello"
