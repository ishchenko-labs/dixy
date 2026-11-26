from tests.samples import SampleDbPool

from dixy.container import Container
from dixy.module import Module
from dixy.providers import singleton


async def async_create_pool() -> SampleDbPool:
    return SampleDbPool(dsn="async://")


class TestAsyncFactory:
    async def test_container_resolve_with_async_singleton(self) -> None:
        class AsyncModule(Module):
            db = singleton(SampleDbPool, factory=async_create_pool)

        class AsyncContainer(Container):
            modules = (AsyncModule,)

        container = AsyncContainer()

        result = await container.resolve(SampleDbPool)

        assert isinstance(result, SampleDbPool)
        assert result.dsn == "async://"
