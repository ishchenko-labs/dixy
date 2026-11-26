from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Protocol

import pytest
from tests.samples import SampleDbPool, SampleRepo, SampleSession

from dixy.container import Container
from dixy.exceptions import (
    CaptiveDependencyError,
    CyclicDependencyError,
    InstanceNotProvidedError,
    MissingDependencyError,
)
from dixy.module import Module
from dixy.providers import alias, hook, instance, scoped, singleton, transient


class CyclicA:
    def __init__(self, b: "CyclicB") -> None:
        self.b = b


class CyclicB:
    def __init__(self, a: CyclicA) -> None:
        self.a = a


class TestValidateMissing:
    def test_raises_for_missing_dependency(self) -> None:
        class Repo:
            def __init__(self, db: SampleDbPool) -> None:
                self.db = db

        class BadModule(Module):
            repo = scoped(Repo)

        class BadContainer(Container):
            modules = (BadModule,)

        container = BadContainer()

        with pytest.raises(MissingDependencyError) as exc_info:
            container.validate()

        assert exc_info.value.interface is SampleDbPool

    def test_skips_factory_registrations(self) -> None:
        class Repo:
            def __init__(self, db: SampleDbPool) -> None:
                self.db = db

        class FactoryModule(Module):
            repo = scoped(Repo, factory=lambda: Repo(SampleDbPool()))

        class FactoryContainer(Container):
            modules = (FactoryModule,)

        container = FactoryContainer()

        container.validate()


class TestValidateCycles:
    def test_raises_for_direct_cycle(self) -> None:
        class CyclicModule(Module):
            a = scoped(CyclicA)
            b = scoped(CyclicB)

        class CyclicContainer(Container):
            modules = (CyclicModule,)

        container = CyclicContainer()

        with pytest.raises(CyclicDependencyError) as exc_info:
            container.validate()

        assert CyclicA in exc_info.value.chain
        assert CyclicB in exc_info.value.chain

    def test_no_cycle_passes(self) -> None:
        class A:
            pass

        class B:
            def __init__(self, a: A) -> None:
                self.a = a

        class LinearModule(Module):
            a = scoped(A)
            b = scoped(B)

        class LinearContainer(Container):
            modules = (LinearModule,)

        container = LinearContainer()

        container.validate()


class TestValidateCaptive:
    def test_raises_when_singleton_depends_on_scoped(self) -> None:
        class ScopedDep:
            pass

        class SingletonService:
            def __init__(self, dep: ScopedDep) -> None:
                self.dep = dep

        class CaptiveModule(Module):
            dep = scoped(ScopedDep)
            service = singleton(SingletonService)

        class CaptiveContainer(Container):
            modules = (CaptiveModule,)

        container = CaptiveContainer()

        with pytest.raises(CaptiveDependencyError) as exc_info:
            container.validate()

        assert exc_info.value.owner_type is SingletonService
        assert exc_info.value.scoped_type is ScopedDep

    def test_raises_when_transient_depends_on_scoped(self) -> None:
        class ScopedDep:
            pass

        class TransientService:
            def __init__(self, dep: ScopedDep) -> None:
                self.dep = dep

        class CaptiveModule(Module):
            dep = scoped(ScopedDep)
            service = transient(TransientService)

        class CaptiveContainer(Container):
            modules = (CaptiveModule,)

        container = CaptiveContainer()

        with pytest.raises(CaptiveDependencyError) as exc_info:
            container.validate()

        assert exc_info.value.owner_type is TransientService
        assert exc_info.value.owner_strategy == "transient"
        assert exc_info.value.scoped_type is ScopedDep

    def test_singleton_depending_on_singleton_ok(self) -> None:
        class DepA:
            pass

        class DepB:
            def __init__(self, a: DepA) -> None:
                self.a = a

        class OkModule(Module):
            a = singleton(DepA)
            b = singleton(DepB)

        class OkContainer(Container):
            modules = (OkModule,)

        container = OkContainer()

        container.validate()


class TestValidateInstances:
    def test_raises_when_instance_not_provided(self) -> None:
        class InstanceModule(Module):
            db = instance(SampleDbPool)

        class InstanceContainer(Container):
            modules = (InstanceModule,)

        container = InstanceContainer()

        with pytest.raises(InstanceNotProvidedError):
            container.validate()

    def test_passes_when_instance_provided(self) -> None:
        class InstanceModule(Module):
            db = instance(SampleDbPool)

        class InstanceContainer(Container):
            modules = (InstanceModule,)

        container = InstanceContainer()
        container.bind(SampleDbPool, SampleDbPool())

        container.validate()


def _make_repo(db: SampleDbPool) -> SampleRepo:
    return SampleRepo(db=db)


class TestValidateFactories:
    def test_catches_missing_factory_dep(self) -> None:
        class Mod(Module):
            repo = scoped(SampleRepo, factory=_make_repo)

        class Con(Container):
            modules = (Mod,)

        with pytest.raises(MissingDependencyError) as exc_info:
            Con().validate()

        assert exc_info.value.interface is SampleDbPool

    def test_catches_captive_factory_dep(self) -> None:
        def make_session(_db: SampleDbPool) -> SampleSession:
            return SampleSession()

        class Mod(Module):
            db = scoped(SampleDbPool)
            session = singleton(SampleSession, factory=make_session)

        class Con(Container):
            modules = (Mod,)

        with pytest.raises(CaptiveDependencyError):
            Con().validate()

    def test_catches_factory_cycle(self) -> None:
        def repo_via_factory(db: SampleDbPool) -> SampleRepo:
            return SampleRepo(db=db)

        def db_via_factory(_repo: SampleRepo) -> SampleDbPool:
            return SampleDbPool()

        class Mod(Module):
            repo = scoped(SampleRepo, factory=repo_via_factory)
            db = scoped(SampleDbPool, factory=db_via_factory)

        class Con(Container):
            modules = (Mod,)

        with pytest.raises(CyclicDependencyError):
            Con().validate()


class TestValidateLifespan:
    def test_lifespan_provider_skips_implementation_init(self) -> None:
        class NeedsUnregistered:
            def __init__(self, missing: SampleDbPool) -> None:
                self.missing = missing

        @asynccontextmanager
        async def lifespan() -> AsyncIterator[NeedsUnregistered]:
            yield NeedsUnregistered(SampleDbPool())

        class Mod(Module):
            service = singleton(NeedsUnregistered, lifespan=lifespan)

        class Con(Container):
            modules = (Mod,)

        Con().validate()

    def test_validates_lifespan_own_dependencies(self) -> None:
        class NoArgs:
            pass

        @asynccontextmanager
        async def lifespan(db: SampleDbPool) -> AsyncIterator[NoArgs]:
            _ = db
            yield NoArgs()

        class Mod(Module):
            service = singleton(NoArgs, lifespan=lifespan)

        class Con(Container):
            modules = (Mod,)

        with pytest.raises(MissingDependencyError) as exc_info:
            Con().validate()

        assert exc_info.value.interface is SampleDbPool


class IRepo(Protocol):
    def get(self) -> str: ...


class IReadRepo(Protocol):
    def get(self) -> str: ...


class TestValidateAliases:
    def test_raises_when_alias_source_is_not_registered(self) -> None:
        class BadModule(Module):
            db = singleton(SampleDbPool)
            irepo = alias(IRepo, SampleRepo)

        class BadContainer(Container):
            modules = (BadModule,)

        container = BadContainer()

        with pytest.raises(MissingDependencyError) as exc_info:
            container.validate()

        assert exc_info.value.interface is SampleRepo
        assert exc_info.value.required_by is IRepo

    def test_raises_when_singleton_depends_on_alias_of_scoped(self) -> None:
        class Service:
            def __init__(self, repo: IRepo) -> None:
                self.repo = repo

        class BadModule(Module):
            db = singleton(SampleDbPool)
            repo = scoped(SampleRepo)
            irepo = alias(IRepo, SampleRepo)
            service = singleton(Service)

        class BadContainer(Container):
            modules = (BadModule,)

        container = BadContainer()

        with pytest.raises(CaptiveDependencyError) as exc_info:
            container.validate()

        assert exc_info.value.owner_type is Service
        assert exc_info.value.scoped_type is SampleRepo

    def test_raises_when_aliases_point_at_each_other(self) -> None:
        class BadModule(Module):
            irepo = alias(IRepo, IReadRepo)
            iread = alias(IReadRepo, IRepo)

        class BadContainer(Container):
            modules = (BadModule,)

        container = BadContainer()

        with pytest.raises(CyclicDependencyError):
            container.validate()

    def test_scoped_depending_on_alias_of_scoped_passes(self) -> None:
        class Service:
            def __init__(self, repo: IRepo) -> None:
                self.repo = repo

        class GoodModule(Module):
            db = singleton(SampleDbPool)
            repo = scoped(SampleRepo)
            irepo = alias(IRepo, SampleRepo)
            service = scoped(Service)

        class GoodContainer(Container):
            modules = (GoodModule,)

        container = GoodContainer()

        container.validate()


class Mediator:
    def __init__(self) -> None:
        self.handlers: list[object] = []


class OrderHandler:
    def __init__(self, mediator: Mediator) -> None:
        self.mediator = mediator


def register_order_handler(mediator: Mediator, handler: OrderHandler) -> None:
    mediator.handlers.append(handler)


def register_repo(mediator: Mediator, repo: SampleRepo) -> None:
    mediator.handlers.append(repo)


class TestValidateSetup:
    def test_raises_for_missing_setup_dependency(self) -> None:
        class BadModule(Module):
            mediator = singleton(Mediator, setup=register_repo)

        class BadContainer(Container):
            modules = (BadModule,)

        container = BadContainer()

        with pytest.raises(MissingDependencyError) as exc_info:
            container.validate()

        assert exc_info.value.interface is SampleRepo
        assert exc_info.value.required_by is Mediator

    def test_raises_for_missing_hook_setup_dependency(self) -> None:
        class OwnerModule(Module):
            mediator = singleton(Mediator)

        class FeatureModule(Module):
            handlers = hook(Mediator, setup=register_repo)

        class BadContainer(Container):
            modules = (OwnerModule, FeatureModule)

        container = BadContainer()

        with pytest.raises(MissingDependencyError) as exc_info:
            container.validate()

        assert exc_info.value.interface is SampleRepo

    def test_raises_for_cycle_through_setup(self) -> None:
        class BadModule(Module):
            mediator = singleton(Mediator, setup=register_order_handler)
            handler = singleton(OrderHandler)

        class BadContainer(Container):
            modules = (BadModule,)

        container = BadContainer()

        with pytest.raises(CyclicDependencyError) as exc_info:
            container.validate()

        assert set(exc_info.value.chain) == {Mediator, OrderHandler}

    def test_raises_for_cycle_through_hook_setup(self) -> None:
        class OwnerModule(Module):
            mediator = singleton(Mediator)

        class FeatureModule(Module):
            handler = singleton(OrderHandler)
            handlers = hook(Mediator, setup=register_order_handler)

        class BadContainer(Container):
            modules = (OwnerModule, FeatureModule)

        container = BadContainer()

        with pytest.raises(CyclicDependencyError):
            container.validate()

    def test_raises_when_singleton_setup_depends_on_scoped(self) -> None:
        class BadModule(Module):
            db = singleton(SampleDbPool)
            repo = scoped(SampleRepo)
            mediator = singleton(Mediator, setup=register_repo)

        class BadContainer(Container):
            modules = (BadModule,)

        container = BadContainer()

        with pytest.raises(CaptiveDependencyError) as exc_info:
            container.validate()

        assert exc_info.value.owner_type is Mediator
        assert exc_info.value.scoped_type is SampleRepo

    def test_setup_instance_parameter_is_not_a_dependency(self) -> None:
        def configure(target: SampleSession) -> None:
            target.open = False

        class GoodModule(Module):
            mediator = singleton(Mediator, setup=configure)
            untyped = singleton(SampleDbPool, setup=lambda pool: None)

        class GoodContainer(Container):
            modules = (GoodModule,)

        container = GoodContainer()

        container.validate()

    def test_satisfied_setup_dependencies_pass(self) -> None:
        class GoodModule(Module):
            db = singleton(SampleDbPool)
            repo = singleton(SampleRepo)
            mediator = singleton(Mediator, setup=register_repo)

        class GoodContainer(Container):
            modules = (GoodModule,)

        container = GoodContainer()

        container.validate()
