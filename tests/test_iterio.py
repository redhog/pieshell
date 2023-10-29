import unittest
import pieshell.iterio
import pieshell.utils.asyncutils
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
        ihi = ih.__aiter__()
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
        ihi = ih.__aiter__()
        assert asyncio.get_event_loop().run_until_complete(ihi.__anext__()) == "hello 0"
        assert asyncio.get_event_loop().run_until_complete(ihi.__anext__()) == "hello 1"

    def test_run(self):
        ls = pieshell.env.echo("hello").run([pieshell.redir.Redirect("stdout", pieshell.redir.PIPE)])
        ih = ls.__aiter__()
        res = asyncio.get_event_loop().run_until_complete(ih.__anext__())
        assert res == "hello"

    def test_asyncitertoiter(self):
        async def gen():
            await asyncio.sleep(0.01)
            yield 1
            await asyncio.sleep(0.01)
            yield 2
        res = list(pieshell.utils.asyncutils.asyncitertoiter(gen()))
        assert res == [1, 2]

    def test_itertoasync(self):
        async def tst():
            res = []
            async for item in pieshell.utils.asyncutils.itertoasync([1, 2]):
                res.append(item)
            return res
        res = asyncio.get_event_loop().run_until_complete(tst())
        assert res == [1, 2]
        
    def test_itertoasync2(self):
        async def val(x):
            return x
        async def tst():
            res = []
            async for item in pieshell.utils.asyncutils.itertoasync([
                    val(1), val(2)]):
                res.append(item)
            return res
        res = asyncio.get_event_loop().run_until_complete(tst())
        assert res == [1, 2]
        
    def test_asyncmap(self):
        async def gen():
            yield 1
            yield 2
        @pieshell.utils.asyncutils.asyncmap
        def mapper(a):
            return a + 1
        async def tst():
            res = []
            async for item in mapper(gen()):
                res.append(item)
            return res
        res = asyncio.get_event_loop().run_until_complete(tst())
        assert res == [2, 3]
        

        
