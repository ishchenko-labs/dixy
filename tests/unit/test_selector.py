import pytest

from dixy.selector import (
    Selector,
    _Call,
    _GetAttr,
    and_,
    or_,
    replay,
)


class TestSelectorGetAttr:
    def test_getattr_is_immutable(self) -> None:
        sel = Selector(object)

        first = sel.a
        second = sel.b

        assert first.get_ops() == (_GetAttr("a"),)
        assert second.get_ops() == (_GetAttr("b"),)

    def test_dunder_raises_attribute_error(self) -> None:
        sel = Selector(object)

        with pytest.raises(AttributeError):
            sel.__custom_dunder__  # noqa: B018

    def test_single_underscore_allowed(self) -> None:
        sel = Selector(object)

        result = sel._private

        assert result.get_ops() == (_GetAttr("_private"),)

    def test_replay_is_a_selectable_field(self) -> None:
        sel = Selector(object)

        result = sel.replay

        assert result.get_ops() == (_GetAttr("replay"),)


class TestSelectorCall:
    def test_call_with_args(self) -> None:
        sel = Selector(object)

        result = sel.method("a", key="b")

        assert result.get_ops() == (_GetAttr("method"), _Call(("a",), {"key": "b"}))


class TestOr:
    async def test_replay_uses_value_when_truthy(self) -> None:
        s = or_(Selector(object).name, "fallback")

        class Obj:
            name = "real"

        result = await replay(s, Obj())

        assert result == "real"

    async def test_replay_uses_fallback_when_empty_string(self) -> None:
        s = or_(Selector(object).name, "fallback")

        class Obj:
            name = ""

        result = await replay(s, Obj())

        assert result == "fallback"


class TestAnd:
    async def test_replay_uses_fallback_when_truthy(self) -> None:
        s = and_(Selector(object).name, "replacement")

        class Obj:
            name = "exists"

        result = await replay(s, Obj())

        assert result == "replacement"

    async def test_replay_keeps_original_when_falsy(self) -> None:
        s = and_(Selector(object).name, "replacement")

        class Obj:
            name = None

        result = await replay(s, Obj())

        assert result is None

    async def test_replay_resolves_selector_fallback(self) -> None:
        s = and_(Selector(object).name, Selector(str))

        class Obj:
            name = "exists"

        result = await replay(s, Obj(), resolve=lambda _sel: "from-selector")

        assert result == "from-selector"
