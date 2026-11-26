from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Final

UNRESOLVED: Final[object] = object()

PRIMITIVES: Final[frozenset[type]] = frozenset(
    {int, str, float, bool, bytes, type(None)}
)


class Strategy(Enum):
    """Provider resolution strategy."""

    ALIAS = auto()
    SCOPED = auto()
    INSTANCE = auto()
    TRANSIENT = auto()
    SINGLETON = auto()
    HOOK = auto()


@dataclass(frozen=True, slots=True)
class Registration:
    """Internal representation of a registered dependency in the container."""

    strategy: Strategy
    interface: type
    implementation: type
    factory: Callable[..., Any] | None = None
    setup: Callable[..., Any] | None = None
    teardown: Callable[[Any], Any] | None = None
    lifespan: Callable[..., Any] | None = None
    hook_target: type | None = None
    kwargs: dict[str, Any] = field(default_factory=dict)
