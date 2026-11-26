from collections.abc import AsyncIterator, Callable, Iterator
from contextlib import asynccontextmanager, contextmanager

import pytest
from tests.samples import SampleDbPool, SampleRepo, SampleService

from dixy.container import Container
from dixy.exceptions import (
    InstanceNotProvidedError,
    MissingDependencyError,
    OutOfScopeError,
)
from dixy.module import Module
from dixy.providers import hook, instance, scoped, singleton, transient


class InfraModule(Module):
    db = singleton(SampleDbPool, dsn="test://")


class DomainModule(Module):
    repo = scoped(SampleRepo)
    service = scoped(SampleService)


class AppContainer(Container):
    modules = (InfraModule, DomainModule)


class TestContainerResolve:
    async def test_resolve_transient(self) -> None:
        class TransientModule(Module):
            db = transient(SampleDbPool, dsn="test://")

        class TransientContainer(Container):
            modules = (TransientModule,)

        container = TransientContainer()

        first = await container.resolve(SampleDbPool)
        second = await container.resolve(SampleDbPool)

        assert first is not second

    async def test_resolve_scoped_raises_scope_error(self) -> None:
        container = AppContainer()

        with pytest.raises(OutOfScopeError):
            await container.resolve(SampleRepo)

    async def test_resolve_unregistered_raises(self) -> None:
        container = AppContainer()

        with pytest.raises(MissingDependencyError):
            await container.resolve(int)


class TestContainerSet:
    async def test_set_provides_instance(self) -> None:
        class InstanceModule(Module):
            db = instance(SampleDbPool)

        class InstanceContainer(Container):
            modules = (InstanceModule,)

        pool = SampleDbPool("provided")
        container = InstanceContainer()
        container.bind(SampleDbPool, pool)

        result = await container.resolve(SampleDbPool)

        assert result is pool

    async def test_resolve_instance_without_set_raises(self) -> None:
        class InstanceModule(Module):
            db = instance(SampleDbPool)

        class InstanceContainer(Container):
            modules = (InstanceModule,)

        container = InstanceContainer()

        with pytest.raises(InstanceNotProvidedError):
            await container.resolve(SampleDbPool)


class TestContainerCreateScope:
    async def test_scope_shares_singletons_with_container(self) -> None:
        container = AppContainer()
        db_from_container = await container.resolve(SampleDbPool)

        async with container.scope() as scope:
            db_from_scope = await scope.resolve(SampleDbPool)

            assert db_from_scope is db_from_container

    async def test_scope_disposes_on_exit(self) -> None:
        closed: list[object] = []

        class DisposableModule(Module):
            db = scoped(
                SampleDbPool, dsn="test://", teardown=lambda x: closed.append(x)
            )

        class DisposableContainer(Container):
            modules = (DisposableModule,)

        container = DisposableContainer()

        async with container.scope() as scope:
            inst = await scope.resolve(SampleDbPool)

        assert closed == [inst]


class TestContainerLifecycle:
    async def test_async_context_manager_disposes_singletons(
        self, close_pool: Callable[[SampleDbPool], object], closed: list[object]
    ) -> None:
        class LifecycleModule(Module):
            db = singleton(SampleDbPool, dsn="test://", teardown=close_pool)

        class LifecycleContainer(Container):
            modules = (LifecycleModule,)

        async with LifecycleContainer() as container:
            pool = await container.resolve(SampleDbPool)

        assert closed == [pool]

    async def test_singletons_torn_down_in_reverse_creation_order(self) -> None:
        order: list[str] = []

        class Db:
            pass

        class Service:
            def __init__(self, db: Db) -> None:
                self.db = db

        # Service is declared before its dependency Db, so registration order
        # is the reverse of creation order — Db is built first to satisfy
        # Service. Teardown must follow creation, not declaration.
        class OrderModule(Module):
            service = singleton(Service, teardown=lambda _: order.append("service"))
            db = singleton(Db, teardown=lambda _: order.append("db"))

        class OrderContainer(Container):
            modules = (OrderModule,)

        async with OrderContainer() as container:
            await container.resolve(Service)

        assert order == ["service", "db"]


class TestContainerLifespan:
    async def test_lifespan_runs_around_body(self) -> None:
        events: list[str] = []

        @asynccontextmanager
        async def track_events(container: Container) -> AsyncIterator[None]:
            events.append("startup")
            yield
            events.append("shutdown")

        class LifespanContainer(Container):
            pass

        async with LifespanContainer(lifespan=track_events):
            events.append("body")

        assert events == ["startup", "body", "shutdown"]

    async def test_lifespan_receives_container_instance(self) -> None:
        received: list[Container] = []

        @asynccontextmanager
        async def capture_container(container: Container) -> AsyncIterator[None]:
            received.append(container)
            yield

        class LifespanContainer(Container):
            pass

        async with LifespanContainer(lifespan=capture_container) as container:
            pass

        assert received == [container]

    async def test_lifespan_shutdown_runs_even_on_exception(self) -> None:
        events: list[str] = []

        @asynccontextmanager
        async def track_events(container: Container) -> AsyncIterator[None]:
            events.append("startup")
            try:
                yield
            finally:
                events.append("shutdown")

        class LifespanContainer(Container):
            pass

        with pytest.raises(RuntimeError, match="boom"):
            async with LifespanContainer(lifespan=track_events):
                raise RuntimeError("boom")

        assert events == ["startup", "shutdown"]

    async def test_sync_lifespan_accepted_in_async_context(self) -> None:
        events: list[str] = []

        @contextmanager
        def sync_track(container: Container) -> Iterator[None]:
            events.append("startup")
            yield
            events.append("shutdown")

        class LifespanContainer(Container):
            pass

        async with LifespanContainer(lifespan=sync_track):
            events.append("body")

        assert events == ["startup", "body", "shutdown"]


class TestContainerRootScopeHook:
    async def test_hook_fires_on_root_scope_singleton_resolution(self) -> None:
        """A hook on a singleton must fire even when resolved at the root scope.

        Regression: the root scope is built before registrations are collected,
        so it must share the container's (initially empty) hooks dict by
        reference rather than replacing it.
        """
        observed: list[SampleDbPool] = []

        def on_setup(pool: SampleDbPool) -> None:
            observed.append(pool)

        class HookedModule(Module):
            db = singleton(SampleDbPool, dsn="test://")
            db_hook = hook(SampleDbPool, setup=on_setup)

        class HookedContainer(Container):
            modules = (HookedModule,)

        container = HookedContainer()
        instance_ = await container.resolve(SampleDbPool)

        assert observed == [instance_]
