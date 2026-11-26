import asyncio

from tests.samples import SampleDbPool

from dixy.container import Container
from dixy.module import Module
from dixy.providers import scoped, singleton


async def _slow_pool(created: list[int]) -> SampleDbPool:
    created.append(1)
    # Yield control between the cache-miss check and the store so that, without
    # a creation lock, every concurrent resolver would build its own instance.
    await asyncio.sleep(0)
    return SampleDbPool()


class TestConcurrentResolution:
    async def test_singleton_created_once_under_gather(self) -> None:
        created: list[int] = []

        class Mod(Module):
            db = singleton(SampleDbPool, factory=lambda: _slow_pool(created))

        class Con(Container):
            modules = (Mod,)

        container = Con()

        results = await asyncio.gather(
            *(container.resolve(SampleDbPool) for _ in range(20))
        )

        assert sum(created) == 1
        assert all(r is results[0] for r in results)

    async def test_scoped_created_once_under_gather(self) -> None:
        created: list[int] = []

        class Mod(Module):
            db = scoped(SampleDbPool, factory=lambda: _slow_pool(created))

        class Con(Container):
            modules = (Mod,)

        container = Con()

        async with container.scope() as scope:
            results = await asyncio.gather(
                *(scope.resolve(SampleDbPool) for _ in range(20))
            )

        assert sum(created) == 1
        assert all(r is results[0] for r in results)
