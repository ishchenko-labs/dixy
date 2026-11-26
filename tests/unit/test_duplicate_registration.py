import pytest
from tests.samples import SampleDbPool, SampleFakeRepo, SampleRepo

from dixy.container import Container
from dixy.exceptions import DuplicateRegistrationError
from dixy.module import Module
from dixy.providers import alias, hook, instance, singleton


class TestProviderDuplicateConflicts:
    @pytest.mark.parametrize(
        "make_provider",
        [
            lambda: singleton(SampleRepo),
        ],
    )
    def test_two_providers_for_same_interface_raises(
        self, make_provider: object
    ) -> None:
        class ModuleA(Module):
            repo = make_provider()  # type: ignore[operator]

        class ModuleB(Module):
            repo = make_provider()  # type: ignore[operator]

        class Cnt(Container):
            modules = (ModuleA, ModuleB)

        with pytest.raises(DuplicateRegistrationError) as exc:
            Cnt()

        assert "SampleRepo" in str(exc.value)

    def test_provider_then_instance_raises(self) -> None:
        class ModuleA(Module):
            repo = singleton(SampleRepo)

        class ModuleB(Module):
            repo = instance(SampleRepo)

        class Cnt(Container):
            modules = (ModuleA, ModuleB)

        with pytest.raises(DuplicateRegistrationError):
            Cnt()


class TestInstanceDuplicatesAllowed:
    async def test_two_instance_declarations_coexist(self) -> None:
        class ModuleA(Module):
            db = instance(SampleDbPool)

        class ModuleB(Module):
            db = instance(SampleDbPool)

        class Cnt(Container):
            modules = (ModuleA, ModuleB)

        container = Cnt()
        pool = SampleDbPool("shared")
        container.bind(SampleDbPool, pool)

        assert await container.resolve(SampleDbPool) is pool


class TestAliasDuplicates:
    def test_same_target_allowed(self) -> None:
        class ModuleA(Module):
            real = singleton(SampleRepo)
            ref_a = alias(SampleFakeRepo, source=SampleRepo)

        class ModuleB(Module):
            ref_b = alias(SampleFakeRepo, source=SampleRepo)

        class Cnt(Container):
            modules = (ModuleA, ModuleB)

        Cnt()  # no raise

    def test_different_target_raises(self) -> None:
        class OtherRepo:
            pass

        class ModuleA(Module):
            real = singleton(SampleRepo)
            other = singleton(OtherRepo)
            ref_a = alias(SampleFakeRepo, source=SampleRepo)

        class ModuleB(Module):
            ref_b = alias(SampleFakeRepo, source=OtherRepo)

        class Cnt(Container):
            modules = (ModuleA, ModuleB)

        with pytest.raises(DuplicateRegistrationError):
            Cnt()


class TestHooksStillAccumulate:
    async def test_multiple_hooks_on_same_target_coexist(self) -> None:
        order: list[str] = []

        class ModuleA(Module):
            db = singleton(SampleDbPool, dsn="test://")
            hook_a = hook(SampleDbPool, setup=lambda _: order.append("a"))

        class ModuleB(Module):
            hook_b = hook(SampleDbPool, setup=lambda _: order.append("b"))

        class Cnt(Container):
            modules = (ModuleA, ModuleB)

        container = Cnt()

        await container.resolve(SampleDbPool)

        assert order == ["a", "b"]
