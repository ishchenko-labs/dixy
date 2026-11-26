import pytest
from tests.samples import SampleSettings, SampleStorage

from dixy.container import Container
from dixy.module import Module
from dixy.providers import instance, scoped
from dixy.selector import or_, select


class TestSelectorResolution:
    async def test_resolve_single_attr(self) -> None:
        class Mod(Module):
            settings = instance(SampleSettings)
            storage = scoped(SampleStorage, dsn=select(SampleSettings).db_dsn)

        class Con(Container):
            modules = (Mod,)

        container = Con()
        container.bind(SampleSettings, SampleSettings(db_dsn="pg://custom"))

        async with container.scope() as scope:
            storage = await scope.resolve(SampleStorage)

        assert storage.dsn == "pg://custom"

    async def test_resolve_getitem(self) -> None:
        class HostService:
            def __init__(self, host: str) -> None:
                self.host = host

        class Mod(Module):
            settings = instance(SampleSettings)
            svc = scoped(HostService, host=select(SampleSettings).hosts[0])

        class Con(Container):
            modules = (Mod,)

        container = Con()
        container.bind(SampleSettings, SampleSettings(hosts=["primary", "secondary"]))

        async with container.scope() as scope:
            svc = await scope.resolve(HostService)

        assert svc.host == "primary"

    async def test_resolve_method_call(self) -> None:
        class Secret:
            def __init__(self, value: str) -> None:
                self._value = value

            def get_secret_value(self) -> str:
                return self._value

        class SettingsWithSecret:
            def __init__(self) -> None:
                self.password = Secret("s3cr3t")

        class DbConn:
            def __init__(self, password: str) -> None:
                self.password = password

        class Mod(Module):
            settings = instance(SettingsWithSecret)
            db = scoped(
                DbConn,
                password=select(SettingsWithSecret).password.get_secret_value(),
            )

        class Con(Container):
            modules = (Mod,)

        container = Con()
        container.bind(SettingsWithSecret, SettingsWithSecret())

        async with container.scope() as scope:
            db = await scope.resolve(DbConn)

        assert db.password == "s3cr3t"

    async def test_missing_attribute_raises(self) -> None:
        class Svc:
            def __init__(self, val: str) -> None:
                self.val = val

        class Mod(Module):
            settings = instance(SampleSettings)
            svc = scoped(Svc, val=select(SampleSettings).nonexistent)  # type: ignore[attr-defined]

        class Con(Container):
            modules = (Mod,)

        container = Con()
        container.bind(SampleSettings, SampleSettings())

        with pytest.raises(AttributeError):
            async with container.scope() as scope:
                await scope.resolve(Svc)

    async def test_empty_chain_resolves_full_object(self) -> None:
        class Holder:
            def __init__(self, settings: SampleSettings) -> None:
                self.settings = settings

        class Mod(Module):
            settings = instance(SampleSettings)
            holder = scoped(Holder, settings=select(SampleSettings))

        class Con(Container):
            modules = (Mod,)

        s = SampleSettings()
        container = Con()
        container.bind(SampleSettings, s)

        async with container.scope() as scope:
            holder = await scope.resolve(Holder)

        assert holder.settings is s


class TestSelectorOrResolution:
    async def test_or_with_literal_fallback(self) -> None:
        class Settings:
            def __init__(self, ns: str | None = None) -> None:
                self.ns = ns

        class Svc:
            def __init__(self, ns: str) -> None:
                self.ns = ns

        class Mod(Module):
            settings = instance(Settings)
            svc = scoped(Svc, ns=or_(select(Settings).ns, "default"))

        class Con(Container):
            modules = (Mod,)

        container = Con()
        container.bind(Settings, Settings(ns=None))

        async with container.scope() as scope:
            svc = await scope.resolve(Svc)

        assert svc.ns == "default"

    async def test_or_with_selector_fallback(self) -> None:
        class Settings:
            def __init__(self, ns: str | None = None) -> None:
                self.ns = ns

        class Defaults:
            def __init__(self, ns: str = "from-defaults") -> None:
                self.ns = ns

        class Svc:
            def __init__(self, ns: str) -> None:
                self.ns = ns

        class Mod(Module):
            settings = instance(Settings)
            defaults = instance(Defaults)
            svc = scoped(Svc, ns=or_(select(Settings).ns, select(Defaults).ns))

        class Con(Container):
            modules = (Mod,)

        container = Con()
        container.bind(Settings, Settings(ns=None))
        container.bind(Defaults, Defaults())

        async with container.scope() as scope:
            svc = await scope.resolve(Svc)

        assert svc.ns == "from-defaults"


class TestSelectorAsyncResolution:
    async def test_resolve_with_async_method_call(self) -> None:
        class AsyncSecret:
            def __init__(self, value: str) -> None:
                self._value = value

            async def get_secret_value(self) -> str:
                return self._value

        class AsyncSettings:
            def __init__(self) -> None:
                self.password = AsyncSecret("async_secret")

        class DbConn:
            def __init__(self, password: str) -> None:
                self.password = password

        class Mod(Module):
            settings = instance(AsyncSettings)
            db = scoped(
                DbConn,
                password=select(AsyncSettings).password.get_secret_value(),
            )

        class Con(Container):
            modules = (Mod,)

        container = Con()
        container.bind(AsyncSettings, AsyncSettings())

        async with container.scope() as scope:
            db = await scope.resolve(DbConn)

        assert db.password == "async_secret"
