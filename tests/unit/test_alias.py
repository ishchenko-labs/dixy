# mypy: disable-error-code="comparison-overlap,type-abstract"
from typing import Protocol

import pytest
from tests.samples import SampleDbPool, SampleRepo

from dixy.container import Container
from dixy.exceptions import InstanceNotProvidedError, OutOfScopeError
from dixy.module import Module
from dixy.providers import alias, instance, scoped, singleton


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

    async def test_alias_to_scoped_from_container_raises_out_of_scope(self) -> None:
        class MyModule(Module):
            db = singleton(SampleDbPool, dsn="test://")
            repo = scoped(SampleRepo)
            irepo = alias(IRepo, SampleRepo)

        class MyContainer(Container):
            modules = (MyModule,)

        container = MyContainer()

        with pytest.raises(OutOfScopeError) as exc_info:
            await container.resolve(IRepo)

        assert exc_info.value.interface is IRepo

    async def test_alias_to_unbound_instance_from_container_raises(self) -> None:
        class MyModule(Module):
            db = instance(SampleDbPool)
            idb = alias(IRepo, SampleDbPool)

        class MyContainer(Container):
            modules = (MyModule,)

        container = MyContainer()

        with pytest.raises(InstanceNotProvidedError) as exc_info:
            await container.resolve(IRepo)

        assert exc_info.value.interface is SampleDbPool

    async def test_alias_of_alias_resolves_to_the_same_instance(self) -> None:
        class IReadRepo(Protocol):
            def get(self) -> str: ...

        class MyModule(Module):
            db = singleton(SampleDbPool, dsn="test://")
            repo = scoped(SampleRepo)
            irepo = alias(IRepo, SampleRepo)
            iread = alias(IReadRepo, IRepo)

        class MyContainer(Container):
            modules = (MyModule,)

        container = MyContainer()
        container.validate()

        async with container.scope() as scope:
            assert await scope.resolve(IReadRepo) is await scope.resolve(SampleRepo)
