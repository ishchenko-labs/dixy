# mypy: disable-error-code="comparison-overlap,type-abstract"
from typing import Protocol

from tests.samples import SampleDbPool, SampleRepo

from dixy.container import Container
from dixy.module import Module
from dixy.providers import alias, scoped, singleton


class IRepo(Protocol):
    def get(self) -> str: ...


class TestAlias:
    async def test_alias_in_container_with_modules(self) -> None:
        class MyModule(Module):
            db = singleton(SampleDbPool, dsn="test://")
            repo = scoped(SampleRepo)
            irepo = alias(IRepo, SampleRepo)

        class MyContainer(Container):
            modules = (MyModule,)

        container = MyContainer()

        async with container.scope() as scope:
            repo = await scope.resolve(SampleRepo)
            irepo = await scope.resolve(IRepo)

            assert repo is irepo

    async def test_alias_from_container_resolve(self) -> None:
        class MyModule(Module):
            db = singleton(SampleDbPool, dsn="test://")
            db_alias = alias(IRepo, SampleDbPool)

        class MyContainer(Container):
            modules = (MyModule,)

        container = MyContainer()

        db = await container.resolve(SampleDbPool)
        aliased = await container.resolve(IRepo)

        assert db is aliased
