from __future__ import annotations

import dataclasses
import inspect
import sys
import weakref
from collections.abc import Callable, Mapping
from types import MappingProxyType
from typing import Any, ClassVar, get_type_hints

from .types import UNRESOLVED

type _Cache = weakref.WeakKeyDictionary[Callable[..., Any], Mapping[str, Any]]


class Introspector:
    """Read type hints and defaults from classes or callables.

    Results are cached per target, because every resolution reads them again.
    The cache holds its targets weakly, so a factory created on the fly and
    then dropped leaves no entry behind.
    """

    _hints: ClassVar[_Cache] = weakref.WeakKeyDictionary()
    _defaults: ClassVar[_Cache] = weakref.WeakKeyDictionary()

    @classmethod
    def get_hints(cls, target: Callable[..., Any]) -> Mapping[str, Any]:
        """Extract parameter type hints from a class __init__ or a callable."""
        return cls._cached(cls._hints, target, cls._read_hints)

    @classmethod
    def get_defaults(cls, target: Callable[..., Any]) -> Mapping[str, Any]:
        """Extract default values for parameters."""
        return cls._cached(cls._defaults, target, cls._read_defaults)

    @staticmethod
    def _cached(
        cache: _Cache,
        target: Callable[..., Any],
        read: Callable[[Callable[..., Any]], dict[str, Any]],
    ) -> Mapping[str, Any]:
        """Read target once, or on every call if it cannot key a weak cache."""
        try:
            return cache[target]
        except KeyError:
            result = cache[target] = MappingProxyType(read(target))
            return result
        except TypeError:
            return MappingProxyType(read(target))

    @classmethod
    def _read_hints(cls, target: Callable[..., Any]) -> dict[str, Any]:
        if not inspect.isclass(target):
            return cls._get_callable_hints(target)
        globalns = cls._get_module_namespace(target)
        if dataclasses.is_dataclass(target):
            hints = cls._get_dataclass_hints(target, globalns)
        elif cls._is_pydantic_model(target):
            hints = cls._get_pydantic_hints(target, globalns)
        else:
            hints = cls._get_regular_hints(target, globalns)
        hints.pop("return", None)
        return hints

    @classmethod
    def _read_defaults(cls, target: Callable[..., Any]) -> dict[str, Any]:
        if not inspect.isclass(target):
            return cls._get_callable_defaults(target)
        if dataclasses.is_dataclass(target):
            return cls._get_dataclass_defaults(target)
        if cls._is_pydantic_model(target):
            return cls._get_pydantic_defaults(target)
        return cls._get_regular_defaults(target)

    @staticmethod
    def _is_pydantic_model(target: type) -> bool:
        return hasattr(target, "model_fields")

    @staticmethod
    def _get_module_namespace(target: Callable[..., Any]) -> dict[str, Any] | None:
        module = sys.modules.get(target.__module__)
        return vars(module) if module else None

    @staticmethod
    def _get_dataclass_hints(
        target: type, globalns: dict[str, Any] | None
    ) -> dict[str, Any]:
        hints = get_type_hints(target, globalns=globalns)
        init_fields = {f.name for f in dataclasses.fields(target) if f.init}
        return {k: v for k, v in hints.items() if k in init_fields}

    @staticmethod
    def _get_pydantic_hints(
        target: type, globalns: dict[str, Any] | None
    ) -> dict[str, Any]:
        hints = get_type_hints(target, globalns=globalns)
        return {k: v for k, v in hints.items() if k in target.model_fields}  # type: ignore[attr-defined]  # pydantic model

    @staticmethod
    def _get_regular_hints(
        target: type, globalns: dict[str, Any] | None
    ) -> dict[str, Any]:
        return get_type_hints(target.__init__, globalns=globalns)  # type: ignore[misc]  # __init__ has no overload

    @classmethod
    def _get_callable_hints(cls, target: Callable[..., Any]) -> dict[str, Any]:
        globalns = cls._get_module_namespace(target)
        hints = get_type_hints(target, globalns=globalns)
        hints.pop("return", None)
        return hints

    @staticmethod
    def _get_dataclass_defaults(target: type) -> dict[str, Any]:
        defaults: dict[str, Any] = {}
        for f in dataclasses.fields(target):
            if f.default is not dataclasses.MISSING:
                defaults[f.name] = f.default
            elif f.default_factory is not dataclasses.MISSING:
                # has default — don't call factory eagerly
                defaults[f.name] = UNRESOLVED
        return defaults

    @staticmethod
    def _get_pydantic_defaults(target: type) -> dict[str, Any]:
        return {
            name: UNRESOLVED
            for name, field_info in target.model_fields.items()  # type: ignore[attr-defined]  # pydantic model
            if not field_info.is_required()
        }

    @staticmethod
    def _get_regular_defaults(target: type) -> dict[str, Any]:
        sig = inspect.signature(target.__init__)  # type: ignore[misc]  # __init__ has no overload
        return {
            name: param.default
            for name, param in sig.parameters.items()
            if name != "self" and param.default is not inspect.Parameter.empty
        }

    @staticmethod
    def _get_callable_defaults(target: Callable[..., Any]) -> dict[str, Any]:
        sig = inspect.signature(target)
        return {
            name: param.default
            for name, param in sig.parameters.items()
            if param.default is not inspect.Parameter.empty
        }
