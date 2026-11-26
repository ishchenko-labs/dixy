import inspect
from typing import get_type_hints

import pytest
from tests.samples import SampleDbPool, SampleRepo

from dixy.container import Container
from dixy.inject import Inject, inject
from dixy.module import Module
from dixy.providers import scoped, singleton


class AppModule(Module):
    db = singleton(SampleDbPool, dsn="test://")
    repo = scoped(SampleRepo)


class InjectContainer(Container):
    modules = (AppModule,)


class TestInjectDecorator:
    async def test_injects_marked_params(self) -> None:
        container = InjectContainer()

        @inject(container)
        async def handler(name: str, repo: Inject[SampleRepo]) -> SampleRepo:
            return repo

        result = await handler(name="test")

        assert isinstance(result, SampleRepo)
        assert isinstance(result.db, SampleDbPool)

    async def test_accepts_container_accessor(self) -> None:
        container = InjectContainer()

        @inject(lambda: container)
        async def handler(repo: Inject[SampleRepo]) -> SampleRepo:
            return repo

        result = await handler()

        assert isinstance(result, SampleRepo)

    def test_rejects_sync_functions(self) -> None:
        container = InjectContainer()

        with pytest.raises(TypeError, match="async function"):

            @inject(container)  # type: ignore[arg-type]  # sync fn rejected by design
            def handler(name: str, db: Inject[SampleDbPool]) -> SampleDbPool:
                return db

    async def test_raises_when_accessor_returns_no_container(self) -> None:
        def no_container() -> Container | None:
            return None

        @inject(no_container)
        async def handler(repo: Inject[SampleRepo]) -> SampleRepo:
            return repo

        with pytest.raises(RuntimeError, match="no container"):
            await handler()

    async def test_raises_when_accessor_returns_non_container(self) -> None:
        def bad_accessor() -> Container:
            return InjectContainer  # type: ignore[return-value]  # class, not instance

        @inject(bad_accessor)
        async def handler(repo: Inject[SampleRepo]) -> SampleRepo:
            return repo

        with pytest.raises(TypeError, match="must return a Container"):
            await handler()

    async def test_positional_args_work(self) -> None:
        container = InjectContainer()

        @inject(container)
        async def handler(user_id: int, repo: Inject[SampleRepo]) -> int:
            return user_id

        result = await handler(42)

        assert result == 42


class TestInjectSignature:
    def test_signature_excludes_injected_params(self) -> None:
        container = InjectContainer()

        @inject(container)
        async def handler(payload: str, repo: Inject[SampleRepo]) -> SampleRepo:
            return repo

        parameters = inspect.signature(handler).parameters

        assert list(parameters) == ["payload"]
        assert parameters["payload"].annotation is str
        assert get_type_hints(handler) == {"payload": str, "return": SampleRepo}
