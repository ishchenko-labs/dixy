from collections.abc import Callable

import pytest
from tests.samples import SampleDbPool, SampleRepo

from dixy.scope import Scope
from dixy.types import Registration, Strategy


class TestScopeSetup:
    async def test_runs_after_creation(
        self, db_registration_factory: Callable[..., Registration]
    ) -> None:
        side_effect: list[SampleDbPool] = []

        def setup(pool: SampleDbPool) -> None:
            side_effect.append(pool)

        registry: dict[type, Registration] = {
            SampleDbPool: db_registration_factory(setup=setup),
        }
        scope = Scope(registry=registry, singletons={})

        instance = await scope.resolve(SampleDbPool)

        assert side_effect == [instance]

    @pytest.mark.parametrize("times", [2])
    async def test_runs_once_for_singleton_regardless_of_resolve_count(
        self,
        times: int,
        db_registration_factory: Callable[..., Registration],
    ) -> None:
        call_count = 0

        def setup(_: SampleDbPool) -> None:
            nonlocal call_count
            call_count += 1

        registry: dict[type, Registration] = {
            SampleDbPool: db_registration_factory(setup=setup),
        }
        scope = Scope(registry=registry, singletons={})

        for _ in range(times):
            await scope.resolve(SampleDbPool)

        assert call_count == 1

    async def test_runs_per_instance_for_transient(
        self, db_registration_factory: Callable[..., Registration]
    ) -> None:
        call_count = 0

        def setup(_: SampleDbPool) -> None:
            nonlocal call_count
            call_count += 1

        registry: dict[type, Registration] = {
            SampleDbPool: db_registration_factory(
                strategy=Strategy.TRANSIENT, setup=setup
            ),
        }
        scope = Scope(registry=registry, singletons={})

        await scope.resolve(SampleDbPool)
        await scope.resolve(SampleDbPool)

        assert call_count == 2

    async def test_async_setup_resolves_typed_params(
        self, db_registration_factory: Callable[..., Registration]
    ) -> None:
        observed: list[SampleDbPool] = []

        async def setup(repo: SampleRepo, db: SampleDbPool) -> None:
            observed.append(db)
            assert repo.db is db

        registry: dict[type, Registration] = {
            SampleDbPool: db_registration_factory(),
            SampleRepo: Registration(
                interface=SampleRepo,
                implementation=SampleRepo,
                strategy=Strategy.SCOPED,
                setup=setup,
            ),
        }
        scope = Scope(registry=registry, singletons={})

        await scope.resolve(SampleRepo)

        assert len(observed) == 1
