import asyncio
import types

def asyncitertoiter(aitf):
    loop = asyncio.get_event_loop()
    def it():
        ait = loop.run_until_complete(aitf)
        while True:
            try:
                yield loop.run_until_complete(ait.__anext__())
            except StopAsyncIteration:
                return
    return iter(it())

class itertoasync(object):
    def __init__(self, it):
        self.it = iter(it)
    async def __aiter__(self):
        self.it = iter(self.it)
        return self
    async def __anext__(self):
        try:
            value = next(self.it)
        except StopIteration:
            raise StopAsyncIteration
        if isinstance(value, types.CoroutineType):
            value = await value
        return value

class asyncmap(object):
    def __init__(self, fn, aiter = None):
        self.fn = fn
        self.ait = aiter
    def __call__(self, aiter):
        return type(self)(self.fn, aiter)
    async def __aiter__(self):
        self.ait = await self.ait.__aiter__()
        return self
    async def __anext__(self):
        return self.fn(await self.ait.__anext__())
