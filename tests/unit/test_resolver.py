import asyncio
import time
from dataclasses import dataclass, field
from typing import Any

import pytest
from pydantic import BaseModel
from tests.samples import SampleDbPool, SampleRepo, SampleService, SampleSession

from dixy.exceptions import MissingDependencyError
from dixy.resolver import Resolver
from dixy.types import Registration, Strategy


class _WithOptional:
    def __init__(self, db: SampleDbPool | None = None) -> None:
        self.db = db


class _RequiredOptional:
    def __init__(self, db: SampleDbPool | None) -> None:
        self.db = db


class _RequiredPrimitive:
    def __init__(self, dsn: str) -> None:
        self.dsn = dsn


class _ThreeIndependentDeps:
    def __init__(
        self, db: SampleDbPool, repo: SampleRepo, session: SampleSession
    ) -> None:
        self.db = db
        self.repo = repo
        self.session = session


class TestBuildKwargs:
    async def test_uses_default_for_unregistered_primitive(self) -> None:
        repo = SampleRepo(SampleDbPool("test"))
        registry: dict[type, Registration] = {
            SampleRepo: Registration(
                interface=SampleRepo,
                implementation=SampleRepo,
                strategy=Strategy.SCOPED,
            )
        }
        resolver = Resolver(registry)

        result = await resolver.build_kwargs(
            target=SampleService,
            resolve_fn=lambda t: repo,
            explicit_kwargs={},
        )

        assert result["repo"] is repo
        assert result["timeout"] == 30

    async def test_skips_primitive_without_default(self) -> None:
        resolver = Resolver({})

        result = await resolver.build_kwargs(
            target=_RequiredPrimitive,
            resolve_fn=lambda t: None,
            explicit_kwargs={},
        )

        assert result == {}

    async def test_raises_for_missing_non_primitive(self) -> None:
        resolver = Resolver({})

        with pytest.raises(MissingDependencyError) as exc_info:
            await resolver.build_kwargs(
                target=SampleRepo,
                resolve_fn=lambda t: None,
                explicit_kwargs={},
            )

        assert exc_info.value.interface is SampleDbPool
        assert exc_info.value.required_by is SampleRepo

    async def test_optional_registered_resolves(self) -> None:
        db = SampleDbPool("test")
        registry: dict[type, Registration] = {
            SampleDbPool: Registration(
                interface=SampleDbPool,
                implementation=SampleDbPool,
                strategy=Strategy.SINGLETON,
            )
        }
        resolver = Resolver(registry)

        result = await resolver.build_kwargs(
            target=_WithOptional,
            resolve_fn=lambda t: db,
            explicit_kwargs={},
        )

        assert result["db"] is db

    async def test_optional_unregistered_is_none(self) -> None:
        resolver = Resolver({})

        result = await resolver.build_kwargs(
            target=_WithOptional,
            resolve_fn=lambda t: None,
            explicit_kwargs={},
        )

        assert result["db"] is None

    async def test_resolves_pydantic_service_with_dependency(self) -> None:
        class UserService(BaseModel):
            model_config = {"arbitrary_types_allowed": True}
            repo: SampleRepo
            timeout: int = 30

        repo = SampleRepo(SampleDbPool("test"))
        registry: dict[type, Registration] = {
            SampleRepo: Registration(
                interface=SampleRepo,
                implementation=SampleRepo,
                strategy=Strategy.SCOPED,
            )
        }
        resolver = Resolver(registry)

        result = await resolver.build_kwargs(
            target=UserService,
            resolve_fn=lambda t: repo,
            explicit_kwargs={},
        )

        assert result["repo"] is repo
        assert "timeout" not in result


class TestDataclassSupport:
    async def test_dataclass_default_factory(self) -> None:
        @dataclass
        class WithFactory:
            items: list[str] = field(default_factory=list)

        resolver = Resolver({})

        result = await resolver.build_kwargs(
            target=WithFactory,
            resolve_fn=lambda t: None,
            explicit_kwargs={},
        )

        assert "items" not in result  # default_factory handled by dataclass __init__

    async def test_dataclass_inheritance(self) -> None:
        @dataclass
        class Base:
            repo: SampleRepo

        @dataclass
        class Child(Base):
            name: str = "default"

        repo = SampleRepo(SampleDbPool("test"))
        registry: dict[type, Registration] = {
            SampleRepo: Registration(
                interface=SampleRepo,
                implementation=SampleRepo,
                strategy=Strategy.SCOPED,
            )
        }
        resolver = Resolver(registry)

        result = await resolver.build_kwargs(
            target=Child,
            resolve_fn=lambda t: repo,
            explicit_kwargs={},
        )

        assert result["repo"] is repo
        assert result["name"] == "default"


class TestGetDependencies:
    def test_skips_primitives(self) -> None:
        assert Resolver({}).get_dependencies(_RequiredPrimitive, {}) == set()

    def test_skips_explicit_kwargs(self) -> None:
        assert Resolver({}).get_dependencies(SampleRepo, {"db": "provided"}) == set()

    def test_skips_optional_deps(self) -> None:
        assert Resolver({}).get_dependencies(_RequiredOptional, {}) == set()


class TestBuildKwargsConcurrency:
    _DELAY: float = 0.2

    async def test_awaits_async_dependencies_concurrently(self) -> None:
        registry: dict[type, Registration] = {
            SampleDbPool: Registration(
                interface=SampleDbPool,
                implementation=SampleDbPool,
                strategy=Strategy.SINGLETON,
            ),
            SampleRepo: Registration(
                interface=SampleRepo,
                implementation=SampleRepo,
                strategy=Strategy.SINGLETON,
            ),
            SampleSession: Registration(
                interface=SampleSession,
                implementation=SampleSession,
                strategy=Strategy.SINGLETON,
            ),
        }
        db = SampleDbPool("test")
        repo = SampleRepo(db)
        session = SampleSession()
        instances: dict[type, Any] = {
            SampleDbPool: db,
            SampleRepo: repo,
            SampleSession: session,
        }

        async def _slow_resolve(interface: type) -> Any:
            await asyncio.sleep(self._DELAY)
            return instances[interface]

        resolver = Resolver(registry)

        started_at = time.monotonic()
        result = await resolver.build_kwargs(
            target=_ThreeIndependentDeps,
            resolve_fn=_slow_resolve,
            explicit_kwargs={},
        )
        elapsed = time.monotonic() - started_at

        assert result == {"db": db, "repo": repo, "session": session}
        assert elapsed < self._DELAY * 2

    async def test_propagates_a_failing_dependency_after_awaiting_the_others(
        self,
    ) -> None:
        registry: dict[type, Registration] = {
            SampleDbPool: Registration(
                interface=SampleDbPool,
                implementation=SampleDbPool,
                strategy=Strategy.SINGLETON,
            ),
            SampleRepo: Registration(
                interface=SampleRepo,
                implementation=SampleRepo,
                strategy=Strategy.SINGLETON,
            ),
            SampleSession: Registration(
                interface=SampleSession,
                implementation=SampleSession,
                strategy=Strategy.SINGLETON,
            ),
        }
        completed: list[type] = []

        async def _resolve(interface: type) -> Any:
            if interface is SampleDbPool:
                raise MissingDependencyError(interface)
            await asyncio.sleep(self._DELAY)
            completed.append(interface)
            return (
                SampleRepo(SampleDbPool())
                if interface is SampleRepo
                else SampleSession()
            )

        resolver = Resolver(registry)

        with pytest.raises(MissingDependencyError):
            await resolver.build_kwargs(
                target=_ThreeIndependentDeps,
                resolve_fn=_resolve,
                explicit_kwargs={},
            )

        assert set(completed) == {SampleRepo, SampleSession}
