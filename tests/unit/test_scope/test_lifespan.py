from collections.abc import AsyncIterator, Callable, Iterator
from contextlib import (
    AbstractAsyncContextManager,
    AbstractContextManager,
    asynccontextmanager,
    contextmanager,
)
from typing import Any

import pytest
from tests.samples import SampleDbPool

from dixy.container import Container
from dixy.module import Module
from dixy.providers import scoped, singleton
from dixy.scope import Scope
from dixy.types import Registration, Strategy


class _Stub:
    pass


def _make_sync_lifespan(
    events: list[str],
) -> Callable[[], AbstractContextManager[_Stub]]:
    @contextmanager
    def lifespan() -> Iterator[_Stub]:
        events.append("enter")
        yield _Stub()
        events.append("exit")

    return lifespan


def _make_async_lifespan(
    events: list[str],
) -> Callable[[], AbstractAsyncContextManager[_Stub]]:
    @asynccontextmanager
    async def lifespan() -> AsyncIterator[_Stub]:
        events.append("enter")
        yield _Stub()
        events.append("exit")

    return lifespan


class TestLifespanEnterExit:
    @pytest.mark.parametrize(
        "make_lifespan",
        [_make_sync_lifespan, _make_async_lifespan],
        ids=["sync", "async"],
    )
    async def test_runs_on_scope(
        self,
        make_lifespan: Callable[[list[str]], Callable[..., Any]],
    ) -> None:
        events: list[str] = []
        lifespan = make_lifespan(events)

        class Mod(Module):
            stub = scoped(_Stub, lifespan=lifespan)

        class Con(Container):
            modules = (Mod,)

        container = Con()
        async with container.scope() as scope:
            await scope.resolve(_Stub)
            assert events == ["enter"]

        assert events == ["enter", "exit"]

    @pytest.mark.parametrize(
        "make_lifespan",
        [_make_sync_lifespan],
        ids=["sync"],
    )
    async def test_singleton_exits_on_container_close(
        self,
        make_lifespan: Callable[[list[str]], Callable[..., Any]],
    ) -> None:
        events: list[str] = []
        lifespan = make_lifespan(events)

        class Mod(Module):
            stub = singleton(_Stub, lifespan=lifespan)

        class Con(Container):
            modules = (Mod,)

        container = Con()
        async with container:
            await container.resolve(_Stub)
            assert events == ["enter"]

        assert events == ["enter", "exit"]


class TestLifespanResolvesDeps:
    async def test_typed_params_auto_resolved(self) -> None:
        seen: list[SampleDbPool] = []

        @asynccontextmanager
        async def lifespan(db: SampleDbPool) -> AsyncIterator[_Stub]:
            seen.append(db)
            yield _Stub()

        class Mod(Module):
            db = singleton(SampleDbPool, dsn="test://")
            stub = singleton(_Stub, lifespan=lifespan)

        class Con(Container):
            modules = (Mod,)

        container = Con()
        async with container:
            db = await container.resolve(SampleDbPool)
            await container.resolve(_Stub)

            assert seen == [db]


class TestLifespanExceptionPath:
    async def test_singleton_exits_when_block_raises(self) -> None:
        events: list[str] = []

        @asynccontextmanager
        async def lifespan() -> AsyncIterator[_Stub]:
            events.append("enter")
            try:
                yield _Stub()
            finally:
                events.append("exit")

        class Mod(Module):
            stub = singleton(_Stub, lifespan=lifespan)

        class Con(Container):
            modules = (Mod,)

        container = Con()
        with pytest.raises(RuntimeError, match="boom"):
            async with container:
                await container.resolve(_Stub)
                raise RuntimeError("boom")

        assert events == ["enter", "exit"]


class TestLifespanOutsideContainer:
    async def test_singleton_lifespan_requires_container_managed_scope(self) -> None:
        registry: dict[type, Registration] = {
            _Stub: Registration(
                interface=_Stub,
                implementation=_Stub,
                strategy=Strategy.SINGLETON,
                lifespan=_make_async_lifespan([]),
            ),
        }
        scope = Scope(registry=registry, singletons={})

        with pytest.raises(RuntimeError, match="Container-managed scope"):
            await scope.resolve(_Stub)


class TestLifespanValidation:
    @pytest.mark.parametrize(
        "extra",
        [
            {"factory": lambda: _Stub()},
            {"setup": lambda _: None},
            {"teardown": lambda _: None},
        ],
        ids=["factory", "setup", "teardown"],
    )
    def test_mutex_with_other_lifecycle_args(
        self, extra: dict[str, Callable[..., object]]
    ) -> None:
        with pytest.raises(ValueError, match="mutually exclusive"):
            # Deliberately mismatched kwargs to verify runtime validation.
            singleton(  # type: ignore[call-overload]
                _Stub, lifespan=lambda: iter([_Stub()]), **extra
            )
