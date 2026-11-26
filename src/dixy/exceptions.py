from __future__ import annotations

from collections.abc import Callable
from typing import Any


def _name_of(target: Callable[..., Any]) -> str:
    return getattr(target, "__name__", type(target).__name__)


class DixyError(Exception):
    """Base exception for all dixy errors."""


class MissingDependencyError(DixyError):
    """Raised when a required dependency is not registered."""

    def __init__(
        self,
        interface: type,
        required_by: Callable[..., Any] | None = None,
    ) -> None:
        self.interface = interface
        self.required_by = required_by
        msg = f"No registration found for {interface.__name__}" + (
            f" (required by {_name_of(rb)})" if (rb := required_by) else ""
        )
        super().__init__(msg)


class CyclicDependencyError(DixyError):
    """Raised when a circular dependency is detected."""

    def __init__(self, chain: list[type]) -> None:
        self.chain = chain
        names = " → ".join(t.__name__ for t in chain)
        super().__init__(f"Cyclic dependency detected: {names}")


class CaptiveDependencyError(DixyError):
    """Raised when a longer-lived provider depends on a scoped dependency."""

    def __init__(
        self, *, owner_type: type, owner_strategy: str, scoped_type: type
    ) -> None:
        self.owner_type = owner_type
        self.owner_strategy = owner_strategy
        self.scoped_type = scoped_type
        super().__init__(
            f"Captive dependency: {owner_strategy} {owner_type.__name__} "
            f"depends on scoped {scoped_type.__name__}"
        )


class OutOfScopeError(DixyError):
    """Raised when resolving a scoped dependency without a scope."""

    def __init__(self, interface: type) -> None:
        self.interface = interface
        super().__init__(
            f"Cannot resolve scoped dependency {interface.__name__} "
            f"without a scope. Use container.scope()."
        )


class InstanceNotProvidedError(DixyError):
    """Raised when an instance() dependency was not provided via bind()."""

    def __init__(self, interface: type) -> None:
        self.interface = interface
        super().__init__(
            f"Instance for {interface.__name__} was declared but never "
            f"provided via container.bind()"
        )


class DuplicateRegistrationError(DixyError):
    """Raised when an interface is registered by multiple modules with conflicts."""

    def __init__(self, interface: type) -> None:
        self.interface = interface
        super().__init__(
            f"{interface.__name__} registered by multiple modules with "
            f"conflicting providers. Move the declaration to a single owning "
            f"module, or use alias() if you intend to expose the same instance "
            f"under two interfaces."
        )
