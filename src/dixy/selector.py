from __future__ import annotations

import inspect
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, assert_never, overload


@dataclass(slots=True, frozen=True)
class _GetAttr:
    name: str


@dataclass(slots=True, frozen=True)
class _Call:
    args: tuple[Any, ...]
    kwargs: dict[str, Any]


@dataclass(slots=True, frozen=True)
class _GetItem:
    key: Any


@dataclass(slots=True, frozen=True)
class _Or:
    fallback: Any


@dataclass(slots=True, frozen=True)
class _And:
    fallback: Any


type _Op = _GetAttr | _Call | _GetItem | _Or | _And


class Selector:
    def __init__(self, interface: type, ops: tuple[_Op, ...] = ()) -> None:
        self._interface = interface
        self._ops = ops

    def get_interface(self) -> type:
        return self._interface

    def get_ops(self) -> tuple[_Op, ...]:
        return self._ops

    def __getattr__(self, name: str) -> Selector:
        if name.startswith("__") and name.endswith("__"):
            raise AttributeError(name)
        return Selector(self.get_interface(), (*self.get_ops(), _GetAttr(name)))

    def __call__(self, *args: Any, **kwargs: Any) -> Selector:
        return Selector(self.get_interface(), (*self.get_ops(), _Call(args, kwargs)))

    def __getitem__(self, key: Any) -> Selector:
        return Selector(self.get_interface(), (*self.get_ops(), _GetItem(key)))


def _resolve_fallback(
    fallback: Any,
    resolve: Callable[[Selector], Any] | None,
) -> Any:
    if isinstance(fallback, Selector) and resolve:
        return resolve(fallback)
    return fallback


async def replay(
    selector: Selector,
    obj: Any,
    *,
    resolve: Callable[[Selector], Any] | None = None,
) -> Any:
    """Replay selector's ops on obj; a function so no method shadows a field name."""
    for op in selector.get_ops():
        match op:
            case _GetAttr(name=name):
                obj = getattr(obj, name)
            case _Call(args=args, kwargs=kw):
                obj = obj(*args, **kw)
                if inspect.iscoroutine(obj):
                    obj = await obj
            case _GetItem(key=key):
                obj = obj[key]
            case _Or(fallback=fallback):
                if not obj:
                    result = _resolve_fallback(fallback, resolve)
                    obj = await result if inspect.isawaitable(result) else result
            case _And(fallback=fallback):
                if obj:
                    result = _resolve_fallback(fallback, resolve)
                    obj = await result if inspect.isawaitable(result) else result
            case _ as unreachable:
                assert_never(unreachable)
    return obj


@overload
def select[T](interface: type[T]) -> T: ...
@overload
def select(interface: Any) -> Any: ...
def select(interface: Any) -> Any:
    """Create a lazy selector for extracting values from a registered dependency.

    Usage in modules:
        storage = scoped(S3Storage, bucket_name=select(Settings).s3_bucket)
    """
    return Selector(interface)


def or_(selector: Any, fallback: Any) -> Any:
    """Return fallback if the selector value is falsy.

    Usage in modules:
        ns = or_(select(Settings).namespace, "default")
    """
    return Selector(selector.get_interface(), (*selector.get_ops(), _Or(fallback)))


def and_(selector: Any, fallback: Any) -> Any:
    """Return fallback if the selector value is truthy.

    Usage in modules:
        key = and_(select(S).api_key, select(S).api_key.get_secret_value())
    """
    return Selector(selector.get_interface(), (*selector.get_ops(), _And(fallback)))
