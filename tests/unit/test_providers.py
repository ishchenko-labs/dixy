from dixy.providers import singleton


class Dummy:
    pass


class DummyImpl:
    pass


class TestSingleton:
    def test_with_impl(self) -> None:
        result = singleton(Dummy, DummyImpl)

        assert result.interface is Dummy  # type: ignore[attr-defined]
        assert result.implementation is DummyImpl  # type: ignore[attr-defined]
