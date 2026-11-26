import pytest
from tests.samples import SampleDbPool, SampleRepo

from dixy.exceptions import InstanceNotProvidedError, MissingDependencyError
from dixy.scope import Scope
from dixy.types import Registration, Strategy


class TestScopeResolve:
    async def test_factory_typed_param_resolves_from_registry(self) -> None:
        pool = SampleDbPool("auto")

        def make_repo(db: SampleDbPool) -> SampleRepo:
            return SampleRepo(db=db)

        registry: dict[type, Registration] = {
            SampleDbPool: Registration(
                interface=SampleDbPool,
                implementation=SampleDbPool,
                strategy=Strategy.SINGLETON,
                factory=lambda: pool,
            ),
            SampleRepo: Registration(
                interface=SampleRepo,
                implementation=SampleRepo,
                strategy=Strategy.SCOPED,
                factory=make_repo,
            ),
        }
        scope = Scope(registry=registry, singletons={})

        repo = await scope.resolve(SampleRepo)

        assert repo.db is pool

    async def test_factory_explicit_kwarg_overrides_auto_resolve(self) -> None:
        registry_pool = SampleDbPool("from-registry")
        explicit_pool = SampleDbPool("from-explicit")

        def make_repo(db: SampleDbPool) -> SampleRepo:
            return SampleRepo(db=db)

        registry: dict[type, Registration] = {
            SampleDbPool: Registration(
                interface=SampleDbPool,
                implementation=SampleDbPool,
                strategy=Strategy.SINGLETON,
                factory=lambda: registry_pool,
            ),
            SampleRepo: Registration(
                interface=SampleRepo,
                implementation=SampleRepo,
                strategy=Strategy.SCOPED,
                factory=make_repo,
                kwargs={"db": explicit_pool},
            ),
        }
        scope = Scope(registry=registry, singletons={})

        repo = await scope.resolve(SampleRepo)

        assert repo.db is explicit_pool

    async def test_resolve_unregistered_raises(self) -> None:
        scope = Scope(registry={}, singletons={})

        with pytest.raises(MissingDependencyError):
            await scope.resolve(SampleDbPool)

    async def test_unbound_instance_raises(self) -> None:
        registry: dict[type, Registration] = {
            SampleDbPool: Registration(
                interface=SampleDbPool,
                implementation=SampleDbPool,
                strategy=Strategy.INSTANCE,
            )
        }
        scope = Scope(registry=registry, singletons={})

        with pytest.raises(InstanceNotProvidedError):
            await scope.resolve(SampleDbPool)
