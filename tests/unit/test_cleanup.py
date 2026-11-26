import asyncio
from collections.abc import AsyncIterator, Callable, Iterator
from contextlib import asynccontextmanager, contextmanager, suppress
from typing import Any

import anyio
import anyio.lowlevel
import pytest

from dixy import Container, Inject, Module, inject, scoped, singleton


class First: ...


class Second: ...


class Third: ...


class Session:
    def __init__(self) -> None:
        self.outcome = "open"


def fail(_: object) -> None:
    raise RuntimeError("teardown failed")


def fail_again(_: object) -> None:
    raise LookupError("another teardown failed")


class Hanging:
    """A teardown that never finishes on its own, and says when it has started."""

    def __init__(self) -> None:
        self._started = asyncio.Event()

    async def __call__(self, _: object) -> None:
        self._started.set()
        await asyncio.Event().wait()

    async def started(self) -> None:
        """Wait for the teardown to start, and fail the test if it was skipped."""
        async with asyncio.timeout(1):
            await self._started.wait()


def recording_lifespans() -> tuple[list[Session], dict[str, Callable[[], Any]]]:
    """Return lifespans that commit or roll back the session they yield."""
    sessions: list[Session] = []

    @contextmanager
    def sync_lifespan() -> Iterator[Session]:
        session = Session()
        sessions.append(session)
        try:
            yield session
        except BaseException:
            session.outcome = "rolled back"
            raise
        else:
            session.outcome = "committed"

    @asynccontextmanager
    async def async_lifespan() -> AsyncIterator[Session]:
        with sync_lifespan() as session:
            yield session

    return sessions, {"sync": sync_lifespan, "async": async_lifespan}


def scope_container(*teardowns: Callable[[Any], Any]) -> type[Container]:
    first, second, third = teardowns

    class Resources(Module):
        a = scoped(First, teardown=first)
        b = scoped(Second, teardown=second)
        c = scoped(Third, teardown=third)

    class App(Container):
        modules = (Resources,)

    return App


def singleton_container(*teardowns: Callable[[Any], Any]) -> type[Container]:
    first, second, third = teardowns

    class Resources(Module):
        a = singleton(First, teardown=first)
        b = singleton(Second, teardown=second)
        c = singleton(Third, teardown=third)

    class App(Container):
        modules = (Resources,)

    return App


class TestScopeTeardownFailures:
    async def test_runs_every_teardown_when_one_fails(self) -> None:
        closed: list[object] = []
        container = scope_container(closed.append, fail, closed.append)()

        with pytest.raises(RuntimeError, match="teardown failed"):
            async with container.scope() as scope:
                first = await scope.resolve(First)
                await scope.resolve(Second)
                third = await scope.resolve(Third)

        assert closed == [third, first]

    async def test_raises_every_failure_when_several_teardowns_fail(self) -> None:
        container = scope_container(fail, fail_again, lambda _: None)()

        with pytest.raises(ExceptionGroup) as exc_info:
            async with container.scope() as scope:
                await scope.resolve(First)
                await scope.resolve(Second)

        assert [type(error) for error in exc_info.value.exceptions] == [
            LookupError,
            RuntimeError,
        ]

    async def test_error_from_the_scope_body_outlives_a_failing_teardown(self) -> None:
        closed: list[object] = []
        container = scope_container(closed.append, fail, closed.append)()

        with pytest.raises(ValueError, match="request failed") as exc_info:
            async with container.scope() as scope:
                first = await scope.resolve(First)
                await scope.resolve(Second)
                raise ValueError("request failed")

        assert closed == [first]
        assert exc_info.value.__notes__ == [
            "Scope teardown also failed: RuntimeError('teardown failed')"
        ]

    async def test_second_teardown_runs_nothing_again(self) -> None:
        closed: list[object] = []
        container = scope_container(closed.append, closed.append, closed.append)()

        async with container.scope() as scope:
            await scope.resolve(First)
        await scope.teardown()

        assert len(closed) == 1


@pytest.mark.parametrize("kind", ["sync", "async"])
class TestScopedLifespanOutcome:
    @staticmethod
    def container(lifespan: Callable[[], Any]) -> Container:
        class Sessions(Module):
            session = scoped(Session, lifespan=lifespan)

        class App(Container):
            modules = (Sessions,)

        return App()

    async def test_lifespan_sees_the_error_that_ended_the_scope(
        self, kind: str
    ) -> None:
        sessions, lifespans = recording_lifespans()
        container = self.container(lifespans[kind])

        with pytest.raises(ValueError, match="request failed"):
            async with container.scope() as scope:
                await scope.resolve(Session)
                raise ValueError("request failed")

        assert sessions[0].outcome == "rolled back"

    async def test_lifespan_sees_no_error_when_the_scope_succeeds(
        self, kind: str
    ) -> None:
        sessions, lifespans = recording_lifespans()
        container = self.container(lifespans[kind])

        async with container.scope() as scope:
            await scope.resolve(Session)

        assert sessions[0].outcome == "committed"

    async def test_lifespan_sees_the_error_raised_by_an_injected_function(
        self, kind: str
    ) -> None:
        sessions, lifespans = recording_lifespans()
        container = self.container(lifespans[kind])

        @inject(container)
        async def handler(session: Inject[Session]) -> None:
            raise ValueError("handler failed")

        with pytest.raises(ValueError, match="handler failed"):
            await handler()

        assert sessions[0].outcome == "rolled back"


class TestLifespanCannotSwallow:
    async def test_error_propagates_past_a_lifespan_that_suppresses_it(self) -> None:
        @contextmanager
        def swallowing() -> Iterator[Session]:
            with suppress(ValueError):
                yield Session()

        class Sessions(Module):
            session = scoped(Session, lifespan=swallowing)

        class App(Container):
            modules = (Sessions,)

        with pytest.raises(ValueError, match="request failed"):
            async with App().scope() as scope:
                await scope.resolve(Session)
                raise ValueError("request failed")


class TestContainerTeardownFailures:
    async def test_runs_every_singleton_teardown_when_one_fails(self) -> None:
        closed: list[object] = []
        app = singleton_container(closed.append, fail, closed.append)

        with pytest.raises(RuntimeError, match="teardown failed"):
            async with app() as container:
                first = await container.resolve(First)
                await container.resolve(Second)
                third = await container.resolve(Third)

        assert closed == [third, first]

    async def test_error_from_the_container_body_outlives_a_failing_teardown(
        self,
    ) -> None:
        closed: list[object] = []
        app = singleton_container(closed.append, fail, closed.append)

        with pytest.raises(ValueError, match="app failed") as exc_info:
            async with app() as container:
                first = await container.resolve(First)
                await container.resolve(Second)
                raise ValueError("app failed")

        assert closed == [first]
        assert exc_info.value.__notes__ == [
            "Container teardown also failed: RuntimeError('teardown failed')"
        ]

    async def test_singletons_are_torn_down_when_the_container_lifespan_fails(
        self,
    ) -> None:
        closed: list[object] = []
        app = singleton_container(closed.append, closed.append, closed.append)

        @contextmanager
        def failing_lifespan(_: Container) -> Iterator[None]:
            yield
            raise RuntimeError("lifespan exit failed")

        with pytest.raises(RuntimeError, match="lifespan exit failed"):
            async with app(lifespan=failing_lifespan) as container:
                first = await container.resolve(First)

        assert closed == [first]

    @pytest.mark.parametrize("kind", ["sync", "async"])
    async def test_singleton_lifespan_sees_the_error_that_closed_the_container(
        self, kind: str
    ) -> None:
        sessions, lifespans = recording_lifespans()

        class Sessions(Module):
            session = singleton(Session, lifespan=lifespans[kind])

        class App(Container):
            modules = (Sessions,)

        with pytest.raises(ValueError, match="app failed"):
            async with App() as container:
                await container.resolve(Session)
                raise ValueError("app failed")

        assert sessions[0].outcome == "rolled back"


class TestCancelledTeardown:
    async def test_runs_every_teardown_when_one_is_cancelled(self) -> None:
        closed: list[object] = []
        hanging = Hanging()
        container = scope_container(closed.append, hanging, closed.append)()

        async def work() -> list[object]:
            async with container.scope() as scope:
                return [
                    await scope.resolve(First),
                    await scope.resolve(Second),
                    await scope.resolve(Third),
                ]

        task = asyncio.create_task(work())
        await hanging.started()
        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task
        assert [type(resource) for resource in closed] == [Third, First]

    async def test_second_cancellation_stops_only_the_teardown_it_lands_on(
        self,
    ) -> None:
        closed: list[object] = []
        hanging, hanging_too = Hanging(), Hanging()
        container = scope_container(closed.append, hanging_too, hanging)()

        async def work() -> None:
            async with container.scope() as scope:
                await scope.resolve(First)
                await scope.resolve(Second)
                await scope.resolve(Third)

        task = asyncio.create_task(work())
        await hanging.started()
        task.cancel()
        await hanging_too.started()
        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task
        assert [type(resource) for resource in closed] == [First]

    async def test_cancellation_outlives_a_failing_teardown(self) -> None:
        hanging = Hanging()
        container = scope_container(fail, hanging, lambda _: None)()

        async def work() -> None:
            async with container.scope() as scope:
                await scope.resolve(First)
                await scope.resolve(Second)

        task = asyncio.create_task(work())
        await hanging.started()
        task.cancel()

        with pytest.raises(asyncio.CancelledError) as exc_info:
            await task
        assert exc_info.value.__notes__ == [
            "Scope teardown also failed: RuntimeError('teardown failed')"
        ]

    async def test_lifespan_rolls_back_when_teardown_is_cancelled(self) -> None:
        sessions, lifespans = recording_lifespans()
        hanging = Hanging()

        class Resources(Module):
            session = scoped(Session, lifespan=lifespans["async"])
            slow = scoped(First, teardown=hanging)

        class App(Container):
            modules = (Resources,)

        container = App()

        async def work() -> None:
            async with container.scope() as scope:
                await scope.resolve(Session)
                await scope.resolve(First)

        task = asyncio.create_task(work())
        await hanging.started()
        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task
        assert [session.outcome for session in sessions] == ["rolled back"]

    async def test_runs_every_singleton_teardown_when_one_is_cancelled(self) -> None:
        closed: list[object] = []
        hanging = Hanging()
        app = singleton_container(closed.append, hanging, closed.append)

        async def work() -> None:
            async with app() as container:
                await container.resolve(First)
                await container.resolve(Second)
                await container.resolve(Third)

        task = asyncio.create_task(work())
        await hanging.started()
        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task
        assert [type(resource) for resource in closed] == [Third, First]


class TestRepeatedCancellation:
    """anyio cancels a scope's task again at every wait until the scope is left."""

    @staticmethod
    async def close_within(app: type[Container]) -> None:
        with anyio.move_on_after(0.01) as deadline:
            async with app().scope() as scope:
                await scope.resolve(First)
                await scope.resolve(Second)
                await scope.resolve(Third)
        assert deadline.cancelled_caught

    async def test_shielded_teardown_finishes(self) -> None:
        closed: list[object] = []

        async def close_shielded(resource: object) -> None:
            with anyio.CancelScope(shield=True):
                await anyio.lowlevel.checkpoint()
                closed.append(resource)

        await self.close_within(
            scope_container(close_shielded, close_shielded, Hanging())
        )

        assert [type(resource) for resource in closed] == [Second, First]

    async def test_unshielded_teardown_is_started_but_cancelled(self) -> None:
        started: list[object] = []
        closed: list[object] = []

        async def close(resource: object) -> None:
            started.append(resource)
            await anyio.lowlevel.checkpoint()
            closed.append(resource)

        await self.close_within(scope_container(close, close, Hanging()))

        assert [type(resource) for resource in started] == [Second, First]
        assert closed == []
