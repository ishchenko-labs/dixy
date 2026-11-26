from __future__ import annotations

import asyncio
import inspect
import types
from collections.abc import Callable, Mapping
from typing import Any, Final, Union, get_args, get_origin

from .exceptions import MissingDependencyError
from .introspector import Introspector
from .selector import Selector
from .types import PRIMITIVES, UNRESOLVED, Registration


class Resolver:
    """Resolve dependencies for class instantiation."""

    _OPTIONAL_ARGS_LEN: Final[int] = 2

    def __init__(self, registry: dict[type, Registration]) -> None:
        self._registry = registry

    async def build_kwargs(
        self,
        target: Callable[..., Any],
        resolve_fn: Callable[[type], Any],
        explicit_kwargs: dict[str, Any],
    ) -> dict[str, Any]:
        """Build kwargs for target, awaiting its dependencies concurrently."""
        kwargs = self._build(target, resolve_fn, explicit_kwargs)
        pending = {
            name: value for name, value in kwargs.items() if inspect.iscoroutine(value)
        }
        if pending:
            results = await asyncio.gather(*pending.values(), return_exceptions=True)
            for name, result in zip(pending, results, strict=True):
                if isinstance(result, BaseException):
                    raise result
                kwargs[name] = result
        return kwargs

    def _build(
        self,
        target: Callable[..., Any],
        resolve_fn: Callable[[type], Any],
        explicit_kwargs: dict[str, Any],
    ) -> dict[str, Any]:
        """Collect kwargs by resolving each parameter."""
        hints = Introspector.get_hints(target)
        defaults = Introspector.get_defaults(target)
        kwargs: dict[str, Any] = dict(explicit_kwargs)

        for name, hint in hints.items():
            if name not in kwargs:
                value = self._resolve_param(name, hint, resolve_fn, defaults, target)
                if value is not UNRESOLVED:
                    kwargs[name] = value

        return kwargs

    def get_dependencies(
        self, target: Callable[..., Any], explicit_kwargs: dict[str, Any]
    ) -> set[type]:
        """Return the set of types that target depends on for validation."""
        hints = Introspector.get_hints(target)
        defaults = Introspector.get_defaults(target)

        # Pass 1: type-hint-based dependencies (skip explicit kwargs)
        deps = {
            dep
            for name, hint in hints.items()
            if name not in explicit_kwargs
            if (dep := self._extract_dependency(name, hint, defaults)) is not None
        }

        # Pass 2: selector source types from explicit kwargs
        for value in explicit_kwargs.values():
            if isinstance(value, Selector):
                deps.add(value.get_interface())

        return deps

    def get_setup_dependencies(self, setup: Callable[..., Any]) -> set[type]:
        """Return what a setup callback needs besides the instance it sets up."""
        instance_param = next(iter(inspect.signature(setup).parameters), None)
        explicit_kwargs = {instance_param: None} if instance_param else {}
        return self.get_dependencies(setup, explicit_kwargs)

    def _resolve_param(
        self,
        name: str,
        hint: Any,
        resolve_fn: Callable[[type], Any],
        defaults: Mapping[str, Any],
        target: Callable[..., Any],
    ) -> Any:
        """Resolve a single parameter. Returns value, coroutine, or UNRESOLVED."""
        if self._is_optional(hint):
            inner = self._unwrap_optional(hint)
            if inner in self._registry:
                return resolve_fn(inner)
            return defaults.get(name)

        if self._is_primitive(hint):
            return defaults.get(name, UNRESOLVED)

        if hint in self._registry:
            return resolve_fn(hint)

        if name in defaults:
            return defaults[name]

        raise MissingDependencyError(hint, required_by=target)

    @staticmethod
    def _extract_dependency(name: str, hint: Any, defaults: Mapping[str, Any]) -> Any:
        """Extract a required dependency type, or None if optional."""
        if Resolver._is_optional(hint):
            return None

        if Resolver._is_primitive(hint):
            return None

        if name in defaults:
            return None

        return hint

    @staticmethod
    def _is_optional(tp: Any) -> bool:
        origin = get_origin(tp)
        if origin is Union or isinstance(tp, types.UnionType):
            args = get_args(tp)
            return type(None) in args and len(args) == Resolver._OPTIONAL_ARGS_LEN
        return False

    @staticmethod
    def _unwrap_optional(tp: Any) -> Any:
        args = get_args(tp)
        for arg in args:
            if arg is not type(None):
                return arg
        return type(None)

    @staticmethod
    def _is_primitive(tp: Any) -> bool:
        return tp in PRIMITIVES
