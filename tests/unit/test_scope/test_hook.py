from collections.abc import Callable

import pytest
from tests.samples import SampleDbPool, SampleRepo

from dixy.container import Container
from dixy.module import Module
from dixy.providers import hook, instance, singleton
from dixy.scope import Scope
from dixy.types import Registration, Strategy


def _hook_registry(*hooks_for_db: Registration) -> dict[type, list[Registration]]:
    return {SampleDbPool: list(hooks_for_db)}


class TestHookSetup:
    async def test_resolves_typed_deps(
        self, db_registration_factory: Callable[..., Registration]
    ) -> None:
        observed: list[tuple[SampleRepo, SampleDbPool]] = []

        def on_setup(repo: SampleRepo, db: SampleDbPool) -> None:
            observed.append((repo, db))

        registry: dict[type, Registration] = {
            SampleDbPool: db_registration_factory(),
            SampleRepo: Registration(
                interface=SampleRepo,
                implementation=SampleRepo,
                strategy=Strategy.SCOPED,
            ),
        }
        scope = Scope(
            registry=registry,
            singletons={},
            hooks={
                SampleRepo: [
                    hook(SampleRepo, setup=on_setup).to_registration(),
                ],
            },
        )

        repo = await scope.resolve(SampleRepo)

        assert observed == [(repo, repo.db)]


class TestHookTeardown:
    async def test_runs_on_scope_teardown(self) -> None:
        torn_down: list[object] = []

        registry: dict[type, Registration] = {
            SampleDbPool: Registration(
                interface=SampleDbPool,
                implementation=SampleDbPool,
                strategy=Strategy.SCOPED,
                kwargs={"dsn": "test://"},
            ),
        }
        scope = Scope(
            registry=registry,
            singletons={},
            hooks=_hook_registry(
                hook(
                    SampleDbPool, teardown=lambda x: torn_down.append(x)
                ).to_registration(),
            ),
        )
        instance = await scope.resolve(SampleDbPool)

        await scope.teardown()

        assert torn_down == [instance]


class TestHookSingletonTeardown:
    async def test_runs_on_container_close(
        self, close_pool: Callable[[SampleDbPool], object], closed: list[object]
    ) -> None:
        class HookedModule(Module):
            db = singleton(SampleDbPool, dsn="test://")
            db_hook = hook(SampleDbPool, teardown=close_pool)

        class HookedContainer(Container):
            modules = (HookedModule,)

        async with HookedContainer() as container:
            pool = await container.resolve(SampleDbPool)

        assert closed == [pool]

    async def test_skipped_for_bound_instance(self, closed: list[object]) -> None:
        class BoundModule(Module):
            db = instance(SampleDbPool)
            db_hook = hook(SampleDbPool, teardown=closed.append)

        class BoundContainer(Container):
            modules = (BoundModule,)

        async with BoundContainer() as container:
            container.bind(SampleDbPool, SampleDbPool())

        assert closed == []


class TestHookValidation:
    def test_hook_requires_setup_or_teardown(self) -> None:
        with pytest.raises(ValueError, match="at least one"):
            hook(SampleDbPool)
