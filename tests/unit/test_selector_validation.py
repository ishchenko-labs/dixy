import pytest
from tests.samples import SampleSettings, SampleStorage

from dixy.container import Container
from dixy.exceptions import (
    CaptiveDependencyError,
    CyclicDependencyError,
    MissingDependencyError,
)
from dixy.module import Module
from dixy.providers import scoped, singleton
from dixy.selector import select


class TestSelectorValidation:
    def test_missing_selector_source_raises(self) -> None:
        class Mod(Module):
            storage = scoped(SampleStorage, dsn=select(SampleSettings).db_dsn)

        class Con(Container):
            modules = (Mod,)

        container = Con()

        with pytest.raises(MissingDependencyError) as exc_info:
            container.validate()

        assert exc_info.value.interface is SampleSettings

    def test_captive_dependency_via_selector(self) -> None:
        class ScopedSettings:
            def __init__(self) -> None:
                self.dsn = "test://"

        class SingletonStorage:
            def __init__(self, dsn: str) -> None:
                self.dsn = dsn

        class Mod(Module):
            settings = scoped(ScopedSettings)
            storage = singleton(SingletonStorage, dsn=select(ScopedSettings).dsn)

        class Con(Container):
            modules = (Mod,)

        container = Con()

        with pytest.raises(CaptiveDependencyError):
            container.validate()

    def test_cycle_via_selector(self) -> None:
        class ConfigA:
            def __init__(self, val: str = "a") -> None:
                self.val = val

        class ServiceB:
            def __init__(self, a: ConfigA) -> None:
                self.a = a

        class Mod(Module):
            a = scoped(ConfigA, val=select(ServiceB).a.val)
            b = scoped(ServiceB)

        class Con(Container):
            modules = (Mod,)

        container = Con()

        with pytest.raises(CyclicDependencyError):
            container.validate()
