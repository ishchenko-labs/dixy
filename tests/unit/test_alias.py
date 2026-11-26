# mypy: disable-error-code="comparison-overlap,type-abstract"
from typing import Protocol

import pytest
from tests.samples import SampleDbPool, SampleRepo

from dixy.container import Container
from dixy.exceptions import InstanceNotProvidedError, OutOfScopeError
from dixy.module import Module
from dixy.providers import alias, hook, instance, scoped, singleton


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


class TestHookOnAlias:
    async def test_setup_runs_on_the_instance_behind_the_alias(self) -> None:
        set_up: list[object] = []

        class OwnerModule(Module):
            db = singleton(SampleDbPool, dsn="test://")
            repo = scoped(SampleRepo)
            irepo = alias(IRepo, SampleRepo)

        class FeatureModule(Module):
            on_repo = hook(IRepo, setup=lambda created: set_up.append(created))

        class MyContainer(Container):
            modules = (OwnerModule, FeatureModule)

        async with MyContainer().scope() as scope:
            repo = await scope.resolve(SampleRepo)

        assert set_up == [repo]

    async def test_setup_runs_once_however_the_instance_is_asked_for(self) -> None:
        set_up: list[object] = []

        class MyModule(Module):
            db = singleton(SampleDbPool, dsn="test://")
            repo = scoped(SampleRepo)
            irepo = alias(IRepo, SampleRepo)
            on_repo = hook(IRepo, setup=lambda created: set_up.append(created))

        class MyContainer(Container):
            modules = (MyModule,)

        async with MyContainer().scope() as scope:
            irepo = await scope.resolve(IRepo)
            await scope.resolve(SampleRepo)

        assert set_up == [irepo]

    async def test_teardown_runs_when_the_scope_closes(self) -> None:
        torn_down: list[object] = []

        class MyModule(Module):
            db = singleton(SampleDbPool, dsn="test://")
            repo = scoped(SampleRepo)
            irepo = alias(IRepo, SampleRepo)
            on_repo = hook(IRepo, teardown=torn_down.append)

        class MyContainer(Container):
            modules = (MyModule,)

        async with MyContainer().scope() as scope:
            repo = await scope.resolve(IRepo)
            assert torn_down == []

        assert torn_down == [repo]

    async def test_teardown_runs_when_the_container_closes(self) -> None:
        torn_down: list[object] = []

        class MyModule(Module):
            db = singleton(SampleDbPool, dsn="test://")
            idb = alias(IRepo, SampleDbPool)
            on_db = hook(IRepo, teardown=torn_down.append)

        class MyContainer(Container):
            modules = (MyModule,)

        async with MyContainer() as container:
            db = await container.resolve(SampleDbPool)

        assert torn_down == [db]

    async def test_hooks_on_alias_and_source_run_in_module_order(self) -> None:
        order: list[str] = []

        class OwnerModule(Module):
            db = singleton(SampleDbPool, dsn="test://")
            idb = alias(IRepo, SampleDbPool)

        class FirstFeature(Module):
            on_db = hook(IRepo, setup=lambda _: order.append("first"))

        class SecondFeature(Module):
            on_db = hook(SampleDbPool, setup=lambda _: order.append("second"))

        class ThirdFeature(Module):
            on_db = hook(IRepo, setup=lambda _: order.append("third"))

        class MyContainer(Container):
            modules = (OwnerModule, FirstFeature, SecondFeature, ThirdFeature)

        await MyContainer().resolve(SampleDbPool)

        assert order == ["first", "second", "third"]

    async def test_clone_keeps_hooks_on_an_alias(self) -> None:
        set_up: list[object] = []

        class MyModule(Module):
            db = singleton(SampleDbPool, dsn="test://")
            idb = alias(IRepo, SampleDbPool)
            on_db = hook(IRepo, setup=lambda created: set_up.append(created))

        class MyContainer(Container):
            modules = (MyModule,)

        cloned = MyContainer().clone()
        db = await cloned.resolve(SampleDbPool)

        assert set_up == [db]
