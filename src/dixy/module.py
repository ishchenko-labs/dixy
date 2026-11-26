from __future__ import annotations

from typing import Any, ClassVar

from .providers import Provider


class Module:
    """Base class for dependency modules.

    Providers are collected from class attributes only — not inherited
    from parent modules. Use composition (multiple modules in Container)
    instead of module inheritance.
    """

    _providers: ClassVar[list[Provider]]

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        cls._providers = []
        for value in vars(cls).values():
            if isinstance(value, Provider):
                cls._providers.append(value)

    @classmethod
    def get_providers(cls) -> list[Provider]:
        return cls._providers.copy()
