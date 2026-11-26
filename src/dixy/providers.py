from __future__ import annotations

from collections.abc import Callable
from typing import Any, overload

from .types import Registration, Strategy


class Provider:
    def __init__(
        self,
        strategy: Strategy,
        interface: type,
        implementation: type | None = None,
        factory: Callable[..., Any] | None = None,
        setup: Callable[..., Any] | None = None,
        teardown: Callable[[Any], Any] | None = None,
        lifespan: Callable[..., Any] | None = None,
        hook_target: type | None = None,
        kwargs: dict[str, Any] | None = None,
    ) -> None:
        if lifespan is not None and any(
            arg is not None for arg in (factory, setup, teardown)
        ):
            raise ValueError(
                "lifespan is mutually exclusive with factory/setup/teardown — "
                "use lifespan alone for paired init/cleanup, or "
                "factory/setup/teardown for independent callbacks"
            )
        self.strategy = strategy
        self.interface = interface
        self.implementation = implementation or interface
        self.factory = factory
        self.setup = setup
        self.teardown = teardown
        self.lifespan = lifespan
        self.hook_target = hook_target
        self.kwargs = kwargs or {}

    def to_registration(self) -> Registration:
        return Registration(
            strategy=self.strategy,
            interface=self.interface,
            implementation=self.implementation,
            factory=self.factory,
            setup=self.setup,
            teardown=self.teardown,
            lifespan=self.lifespan,
            hook_target=self.hook_target,
            kwargs=self.kwargs,
        )


@overload
def singleton[T](
    interface: type[T], implementation: type | None = ..., **kwargs: Any
) -> T: ...
@overload
def singleton(
    interface: Any, implementation: type | None = ..., **kwargs: Any
) -> Any: ...
def singleton(
    interface: Any,
    implementation: type | None = None,
    *,
    factory: Callable[..., Any] | None = None,
    setup: Callable[..., Any] | None = None,
    teardown: Callable[..., Any] | None = None,
    lifespan: Callable[..., Any] | None = None,
    **kwargs: Any,
) -> Any:
    return Provider(
        strategy=Strategy.SINGLETON,
        interface=interface,
        implementation=implementation,
        factory=factory,
        setup=setup,
        teardown=teardown,
        lifespan=lifespan,
        kwargs=kwargs,
    )


@overload
def scoped[T](
    interface: type[T], implementation: type | None = ..., **kwargs: Any
) -> T: ...
@overload
def scoped(interface: Any, implementation: type | None = ..., **kwargs: Any) -> Any: ...
def scoped(
    interface: Any,
    implementation: type | None = None,
    *,
    factory: Callable[..., Any] | None = None,
    setup: Callable[..., Any] | None = None,
    teardown: Callable[..., Any] | None = None,
    lifespan: Callable[..., Any] | None = None,
    **kwargs: Any,
) -> Any:
    return Provider(
        strategy=Strategy.SCOPED,
        interface=interface,
        implementation=implementation,
        factory=factory,
        setup=setup,
        teardown=teardown,
        lifespan=lifespan,
        kwargs=kwargs,
    )


@overload
def transient[T](
    interface: type[T], implementation: type | None = ..., **kwargs: Any
) -> T: ...
@overload
def transient(
    interface: Any, implementation: type | None = ..., **kwargs: Any
) -> Any: ...
def transient(
    interface: Any,
    implementation: type | None = None,
    *,
    factory: Callable[..., Any] | None = None,
    setup: Callable[..., Any] | None = None,
    **kwargs: Any,
) -> Any:
    return Provider(
        strategy=Strategy.TRANSIENT,
        interface=interface,
        implementation=implementation,
        factory=factory,
        setup=setup,
        kwargs=kwargs,
    )


@overload
def alias[T](interface: type[T], source: type) -> T: ...
@overload
def alias(interface: Any, source: type) -> Any: ...
def alias(interface: Any, source: type) -> Any:
    """Resolve interface as the same instance as source."""
    return Provider(
        strategy=Strategy.ALIAS,
        interface=interface,
        implementation=source,
    )


@overload
def instance[T](interface: type[T]) -> T: ...
@overload
def instance(interface: Any) -> Any: ...
def instance(interface: Any) -> Any:
    return Provider(
        strategy=Strategy.INSTANCE,
        interface=interface,
    )


def hook(
    interface: type,
    *,
    setup: Callable[..., Any] | None = None,
    teardown: Callable[..., Any] | None = None,
) -> Provider:
    """Register a lifecycle hook for an interface declared in another module."""
    if setup is None and teardown is None:
        raise ValueError("hook requires at least one of setup or teardown")
    marker = type(f"_Hook_{interface.__name__}_{id(setup or teardown):x}", (), {})
    return Provider(
        strategy=Strategy.HOOK,
        interface=marker,
        hook_target=interface,
        setup=setup,
        teardown=teardown,
    )
