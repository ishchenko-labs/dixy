import gc
import weakref
from collections.abc import Callable
from typing import Any

import pytest
from tests.samples import SampleDbPool, SampleRepo

from dixy.introspector import Introspector


class _CallableWithoutHash:
    __hash__ = None  # type: ignore[assignment]  # unhashable on purpose

    def __call__(self, repo: str = "fallback") -> str:
        return repo


def _make_factory() -> Callable[[SampleDbPool], SampleRepo]:
    def factory(pool: SampleDbPool) -> SampleRepo:
        return SampleRepo(pool)

    return factory


@pytest.mark.parametrize("read", [Introspector.get_hints, Introspector.get_defaults])
class TestCache:
    def test_reads_a_target_once(self, read: Callable[[Any], object]) -> None:
        first = read(SampleRepo)

        assert read(SampleRepo) is first

    def test_hands_out_a_read_only_view(self, read: Callable[[Any], Any]) -> None:
        result = read(SampleRepo)

        with pytest.raises(TypeError):
            result["intruder"] = int

    def test_lets_a_dropped_factory_go(self, read: Callable[[Any], object]) -> None:
        factory = _make_factory()
        read(factory)
        gone = weakref.ref(factory)

        del factory
        gc.collect()

        assert gone() is None


def test_still_reads_a_callable_it_cannot_key_on() -> None:
    defaults = Introspector.get_defaults(_CallableWithoutHash())

    assert dict(defaults) == {"repo": "fallback"}


class TestGetHints:
    def test_reads_init_parameters_of_a_class(self) -> None:
        assert dict(Introspector.get_hints(SampleRepo)) == {"db": SampleDbPool}
