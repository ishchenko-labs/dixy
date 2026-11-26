from tests.samples import SampleRepo, SampleService

from dixy.module import Module
from dixy.providers import scoped, singleton


class TestModuleCollectsProviders:
    def test_collects_providers_from_class_attrs(self) -> None:
        class MyModule(Module):
            repo = scoped(SampleRepo)
            service = singleton(SampleService)

        providers = MyModule.get_providers()

        assert len(providers) == 2
        types = {p.interface for p in providers}
        assert types == {SampleRepo, SampleService}

    def test_separate_modules_are_independent(self) -> None:
        class ModuleA(Module):
            repo = scoped(SampleRepo)

        class ModuleB(Module):
            service = singleton(SampleService)

        assert len(ModuleA.get_providers()) == 1
        assert len(ModuleB.get_providers()) == 1
        assert ModuleA.get_providers()[0].interface is SampleRepo
        assert ModuleB.get_providers()[0].interface is SampleService
