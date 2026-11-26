from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest
from tests.samples import SampleDbPool, SampleFakeRepo, SampleRepo

from dixy.container import Container
from dixy.exceptions import MissingDependencyError
from dixy.module import Module
from dixy.providers import alias, instance, scoped, singleton


class AppModule(Module):
    db = singleton(SampleDbPool, dsn="prod://")
    repo = scoped(SampleRepo)


class AppContainer(Container):
    modules = (AppModule,)


class TestClone:
    async def test_clone_does_not_share_singletons(self) -> None:
        container = AppContainer()
        original = await container.resolve(SampleDbPool)
        cloned = container.clone()

        actual = await cloned.resolve(SampleDbPool)

        assert actual is not original

    async def test_clone_copies_instance_values(self) -> None:
        class InstanceModule(Module):
            db = instance(SampleDbPool)

        class InstanceContainer(Container):
            modules = (InstanceModule,)

        pool = SampleDbPool("shared")
        container = InstanceContainer()
        container.bind(SampleDbPool, pool)

        cloned = container.clone()

        assert await cloned.resolve(SampleDbPool) is pool

    async def test_clone_supports_singleton_lifespan(self) -> None:
        events: list[str] = []

        @asynccontextmanager
        async def lifespan() -> AsyncIterator[SampleDbPool]:
            events.append("enter")
            yield SampleDbPool()
            events.append("exit")

        class LifespanModule(Module):
            db = singleton(SampleDbPool, lifespan=lifespan)

        class LifespanContainer(Container):
            modules = (LifespanModule,)

        cloned = LifespanContainer().clone()

        async with cloned:
            pool = await cloned.resolve(SampleDbPool)
            assert isinstance(pool, SampleDbPool)
            assert events == ["enter"]

        assert events == ["enter", "exit"]


class TestOverride:
    async def test_override_with_type(self) -> None:
        container = AppContainer()
        cloned = container.clone()

        cloned.override(interface=SampleRepo, implementation=SampleFakeRepo)

        async with cloned.scope() as scope:
            result = await scope.resolve(SampleRepo)

            assert isinstance(result, SampleFakeRepo)

    async def test_override_with_instance(self) -> None:
        container = AppContainer()
        cloned = container.clone()
        fake_pool = SampleDbPool("fake")

        cloned.override(interface=SampleDbPool, implementation=fake_pool)

        result = await cloned.resolve(SampleDbPool)

        assert result is fake_pool

    async def test_original_not_affected_by_override(self) -> None:
        container = AppContainer()
        cloned = container.clone()

        cloned.override(interface=SampleDbPool, implementation=SampleDbPool("fake"))

        result = await container.resolve(SampleDbPool)

        assert result.dsn == "prod://"

    def test_override_unregistered_interface_raises(self) -> None:
        cloned = AppContainer().clone()

        with pytest.raises(MissingDependencyError) as exc_info:
            cloned.override(interface=SampleFakeRepo, implementation=SampleFakeRepo)

        assert str(exc_info.value) == "No registration found for SampleFakeRepo"

    async def test_override_alias_with_type_replaces_only_the_alias(self) -> None:
        class ReadOnlyRepo(SampleRepo): ...

        class AliasModule(Module):
            db = singleton(SampleDbPool, dsn="prod://")
            repo = scoped(SampleRepo)
            reader = alias(ReadOnlyRepo, SampleRepo)

        class AliasContainer(Container):
            modules = (AliasModule,)

        class FakeReader(ReadOnlyRepo): ...

        cloned = AliasContainer().clone()

        cloned.override(interface=ReadOnlyRepo, implementation=FakeReader)

        cloned.validate()
        async with cloned.scope() as scope:
            reader = await scope.resolve(ReadOnlyRepo)
            same_reader = await scope.resolve(ReadOnlyRepo)
            repo = await scope.resolve(SampleRepo)

        assert isinstance(reader, FakeReader)
        assert reader is same_reader
        assert type(repo) is SampleRepo

    async def test_override_instance_with_type_builds_it_once(self) -> None:
        class InstanceModule(Module):
            pool = instance(SampleDbPool)

        class InstanceContainer(Container):
            modules = (InstanceModule,)

        class FakePool(SampleDbPool): ...

        container = InstanceContainer()
        container.bind(SampleDbPool, SampleDbPool("prod://"))
        cloned = container.clone()

        cloned.override(interface=SampleDbPool, implementation=FakePool)

        cloned.validate()
        pool = await cloned.resolve(SampleDbPool)

        assert isinstance(pool, FakePool)
        assert pool is await cloned.resolve(SampleDbPool)
        assert type(await container.resolve(SampleDbPool)) is SampleDbPool
