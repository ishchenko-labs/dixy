from __future__ import annotations

import functools
import inspect
import logging
from collections.abc import Callable, Coroutine
from typing import (
    Annotated,
    Any,
    Protocol,
    TypeAliasType,
    get_args,
    get_origin,
    get_type_hints,
)

from .container import Container

logger = logging.getLogger(__name__)


class _InjectMarker: ...


type Inject[T] = Annotated[T, _InjectMarker]


class _InjectDecorator(Protocol):
    """Return type of inject() — preserves the wrapped coroutine's return type."""

    def __call__[R](
        self,
        fn: Callable[..., Coroutine[Any, Any, R]],
    ) -> Callable[..., Coroutine[Any, Any, R]]: ...


def inject(
    source: Container | Callable[[], Container | None],
) -> _InjectDecorator:
    """Inject dependencies marked with Inject[T] into async function parameters.

    Accepts a container instance, or a no-arg accessor returning the active
    container — use the accessor when the container is created after the
    decorated function is defined (e.g. framework entry points).
    """

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        if not inspect.iscoroutinefunction(fn):
            msg = (
                f"@inject requires an async function; {fn.__name__} is sync. "
                f"dixy resolves dependencies asynchronously."
            )
            raise TypeError(msg)

        params = _AnnotationInspector.collect_params(fn)

        @functools.wraps(fn)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            logger.debug("Injecting %s into %s", list(params.keys()), fn.__name__)
            container = _resolve_source(source)
            async with container.scope() as scope:
                await _resolve_params(params, kwargs, scope.resolve)
                return await fn(*args, **kwargs)

        _hide_injected_params(async_wrapper, fn, params)
        return async_wrapper

    return decorator


def _hide_injected_params(
    wrapper: Callable[..., Any],
    fn: Callable[..., Any],
    injected: dict[str, type[Any]],
) -> None:
    """Expose only the non-injected parameters to external introspection.

    Frameworks such as Temporal read a callable's signature and type hints to
    deserialize its arguments. Injected parameters are filled by the container,
    not by the caller, so they must not appear in the wrapper's public contract;
    functools.wraps copies them verbatim, which this corrects.
    """
    signature = inspect.signature(fn)
    visible = [
        param for name, param in signature.parameters.items() if name not in injected
    ]
    wrapper.__signature__ = signature.replace(parameters=visible)  # type: ignore[attr-defined]  # __signature__ is settable at runtime; absent from typeshed's function type
    wrapper.__annotations__ = {
        name: hint for name, hint in fn.__annotations__.items() if name not in injected
    }


def _resolve_source(
    source: Container | Callable[[], Container | None],
) -> Container:
    if isinstance(source, Container):
        return source
    container = source()
    if container is None:
        msg = (
            "inject accessor returned no container; ensure a Container is "
            "active before calling inject-decorated functions."
        )
        raise RuntimeError(msg)
    if not isinstance(container, Container):
        msg = (
            f"inject accessor must return a Container, got {type(container).__name__}."
        )
        raise TypeError(msg)
    return container


async def _resolve_params(
    params: dict[str, type[Any]],
    kwargs: dict[str, Any],
    resolve_fn: Callable[..., Any],
) -> None:
    for name, param_type in params.items():
        if name not in kwargs:
            kwargs[name] = await resolve_fn(param_type)


class _AnnotationInspector:
    """Detect and unwrap Inject[T] annotations, handling TypeAliasType."""

    @classmethod
    def collect_params(cls, fn: Callable[..., Any]) -> dict[str, type[Any]]:
        """Collect parameters annotated with Inject[T]."""
        hints = get_type_hints(fn, include_extras=True)
        return {
            name: cls._unwrap(hint)
            for name, hint in hints.items()
            if name != "return" and cls._is_inject(hint)
        }

    @staticmethod
    def _is_inject(annotation: Any) -> bool:
        resolved = _AnnotationInspector._resolve(annotation)
        if get_origin(resolved) is not Annotated:
            return False
        return any(a is _InjectMarker for a in get_args(resolved))

    @staticmethod
    def _unwrap(annotation: Any) -> type[Any]:
        resolved = _AnnotationInspector._resolve(annotation)
        return get_args(resolved)[0]  # type: ignore[no-any-return]  # get_args returns tuple[Any, ...]

    @staticmethod
    def _resolve(annotation: Any) -> Any:
        if isinstance(annotation, TypeAliasType):
            return annotation.__value__

        origin = get_origin(annotation)
        if isinstance(origin, TypeAliasType):
            type_params = origin.__type_params__
            type_args = get_args(annotation)
            value = origin.__value__
            if type_params and type_args:
                param_map = dict(
                    zip(type_params, type_args, strict=True),
                )
                return _AnnotationInspector._substitute(value, param_map)
            return value

        return annotation

    @staticmethod
    def _substitute(tp: Any, param_map: dict[Any, Any]) -> Any:
        if tp in param_map:
            return param_map[tp]

        origin = get_origin(tp)
        if origin is None:
            return tp

        args = get_args(tp)
        if not args:
            return tp

        new_args = tuple(_AnnotationInspector._substitute(a, param_map) for a in args)
        return origin[new_args] if len(new_args) > 1 else origin[new_args[0]]
