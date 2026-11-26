from __future__ import annotations

import asyncio
import functools
import logging
from collections.abc import AsyncIterator, Callable
from contextlib import (
    AbstractAsyncContextManager,
    AbstractContextManager,
    AsyncExitStack,
    asynccontextmanager,
)
from types import TracebackType
from typing import Any, ClassVar, Self, cast, overload

from .exceptions import (
    CaptiveDependencyError,
    CyclicDependencyError,
    DuplicateRegistrationError,
    InstanceNotProvidedError,
    MissingDependencyError,
    OutOfScopeError,
)
from .module import Module
from .resolver import Resolver
from .scope import (
    Cleanup,
    Scope,
    call_teardown,
    exit_lifespan,
    note_failures,
    raise_failures,
    run_cleanups,
)
from .types import Registration, Strategy

logger = logging.getLogger(__name__)


type Lifespan[T] = Callable[
    [T],
    AbstractContextManager[None] | AbstractAsyncContextManager[None],
]


class Container:
    """Dependency injection container.

    Collects registrations from modules and resolves dependencies.
    """

    modules: ClassVar[tuple[type[Module], ...]] = ()

    def __init__(self, *, lifespan: Lifespan[Container] | None = None) -> None:
        self._registry: dict[type, Registration] = {}
        self._hooks: dict[type, list[Registration]] = {}
        self._singletons: dict[type, Any] = {}
        self._singleton_lifespans: dict[type, Any] = {}
        self._singleton_locks: dict[type, asyncio.Lock] = {}
        self._root_scope = Scope(
            self._registry,
            self._singletons,
            self._hooks,
            self._singleton_lifespans,
            self._singleton_locks,
        )
        self._lifespan = lifespan
        self._async_stack: AsyncExitStack | None = None

        self._collect_registrations()
        logger.info(
            "Initialized with %d registrations from %d modules",
            len(self._registry),
            len(self.modules),
        )

    def _collect_registrations(self) -> None:
        for module_cls in self.modules:
            for provider in module_cls.get_providers():
                reg = provider.to_registration()
                if reg.strategy == Strategy.HOOK:
                    hook_target = cast("type", reg.hook_target)
                    self._hooks.setdefault(hook_target, []).append(reg)
                    continue
                if (existing := self._registry.get(reg.interface)) is not None:
                    self._check_registration_conflict(new=reg, existing=existing)
                self._registry[reg.interface] = reg

    @staticmethod
    def _check_registration_conflict(
        *, new: Registration, existing: Registration
    ) -> None:
        """Raise unless the new registration is compatible with the existing one.

        - INSTANCE declarations are pure "expected to be bound" markers and may
          repeat across modules (no implementation, no conflict).
        - ALIAS declarations may repeat if they point at the same source.
        - Provider strategies (SINGLETON/SCOPED/TRANSIENT) always conflict —
          two implementations for one interface is ambiguous.
        """
        if new.strategy == existing.strategy == Strategy.INSTANCE:
            return
        if (
            new.strategy == existing.strategy == Strategy.ALIAS
            and new.implementation is existing.implementation
        ):
            return
        raise DuplicateRegistrationError(new.interface)

    def bind[T](self, interface: type[T], value: T) -> None:
        """Bind a pre-built instance for an instance() declaration."""
        self._singletons[interface] = value
        logger.info("Bound %s", interface.__name__)

    @overload
    async def resolve[T](self, interface: type[T]) -> T: ...
    @overload
    async def resolve(self, interface: Any) -> Any: ...
    async def resolve(self, interface: Any) -> Any:
        """Resolve a singleton, transient, or instance dependency."""
        self._check_access(interface)
        return await self._root_scope.resolve(interface)

    def _check_access(self, interface: type) -> None:
        if interface not in self._registry:
            raise MissingDependencyError(interface)

        reg = self._behind_aliases(interface)
        if reg is None:
            return

        match reg.strategy:
            case Strategy.SCOPED:
                raise OutOfScopeError(interface)
            case Strategy.INSTANCE if reg.interface not in self._singletons:
                raise InstanceNotProvidedError(reg.interface)

    def _behind_aliases(self, interface: type) -> Registration | None:
        """Return the registration an alias chain ends at, or None if it ends nowhere.

        An alias has no lifetime of its own, so every lifetime rule applies to
        what it points at. A chain that loops ends at an alias, which no rule
        matches; validate() reports the loop itself.
        """
        seen: set[type] = set()
        reg = self._registry.get(interface)
        while reg is not None and reg.strategy == Strategy.ALIAS:
            if reg.interface in seen:
                break
            seen.add(reg.interface)
            reg = self._registry.get(reg.implementation)
        return reg

    def _dependencies_of(self, reg: Registration, resolver: Resolver) -> set[type]:
        """Return everything resolved while a registration's instance is created.

        An alias needs only its source. Anything else needs what its constructor,
        factory or lifespan asks for, plus what its own setup and the setups
        hooked onto it ask for: those run before the instance is cached, so a
        dependency that leads back to it would wait on it forever.
        """
        if reg.strategy == Strategy.ALIAS:
            return {reg.implementation}
        target = reg.factory or reg.lifespan or reg.implementation
        deps = resolver.get_dependencies(target, reg.kwargs)
        hooks = self._hooks.get(reg.interface, [])
        for setup in (reg.setup, *(hook_reg.setup for hook_reg in hooks)):
            if setup is not None:
                deps |= resolver.get_setup_dependencies(setup)
        return deps

    def _new_scope(self) -> Scope:
        scope = Scope(
            registry=self._registry,
            singletons=self._singletons,
            hooks=self._hooks,
            singleton_lifespans=self._singleton_lifespans,
            singleton_locks=self._singleton_locks,
        )
        logger.debug("Scope created")
        return scope

    @asynccontextmanager
    async def scope(self) -> AsyncIterator[Scope]:
        """Create an async scope."""
        child = self._new_scope()
        try:
            yield child
        except BaseException as error:
            try:
                await child.teardown(error)
            except Exception as failure:
                note_failures([failure], error, owner="Scope")
            raise
        else:
            await child.teardown()

    async def __aenter__(self) -> Self:
        stack = AsyncExitStack()
        await stack.__aenter__()
        self._async_stack = stack
        if self._lifespan is not None:
            cm = self._lifespan(self)
            if isinstance(cm, AbstractAsyncContextManager):
                await stack.enter_async_context(cm)
            else:
                stack.enter_context(cm)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        cleanups = self._singleton_cleanups()
        if (stack := self._async_stack) is not None:
            self._async_stack = None
            cleanups.insert(0, functools.partial(exit_lifespan, stack))
        failures = await run_cleanups(cleanups, exc_val, owner="Container")
        logger.info("Container closed, %d cleanups run", len(cleanups))
        if exc_val is None:
            raise_failures(failures)
        else:
            note_failures(failures, exc_val, owner="Container")

    def _singleton_cleanups(self) -> list[Cleanup]:
        """Collect the cleanups of created singletons in reverse creation order.

        Iterates the singleton cache, whose insertion order is creation order,
        so a dependency is never disposed before the singleton that holds it.
        """
        cleanups: list[Cleanup] = []
        for interface in reversed(list(self._singletons)):
            reg = self._registry.get(interface)
            if reg is None or reg.strategy != Strategy.SINGLETON:
                continue
            instance = self._singletons[interface]
            if reg.teardown:
                cleanups.append(call_teardown(reg.teardown, instance))
            if interface in self._singleton_lifespans:
                cm = self._singleton_lifespans.pop(interface)
                cleanups.append(functools.partial(exit_lifespan, cm))
            cleanups.extend(
                call_teardown(hook_reg.teardown, instance)
                for hook_reg in self._hooks.get(interface, [])
                if hook_reg.teardown
            )
        return cleanups

    def validate(self) -> None:
        """Validate the dependency graph at startup."""
        try:
            self._check_instances()
            self._check_missing()
            self._check_cycles()
            self._check_captive()
        except Exception as exc:
            logger.warning("Validation failed: %s", exc)
            raise
        logger.info("Validated successfully (%d registrations)", len(self._registry))

    def _check_instances(self) -> None:
        for reg in self._registry.values():
            if (
                reg.strategy == Strategy.INSTANCE
                and reg.interface not in self._singletons
            ):
                raise InstanceNotProvidedError(reg.interface)

    def _check_missing(self) -> None:
        resolver = Resolver(self._registry)
        for reg in self._registry.values():
            if reg.strategy == Strategy.INSTANCE:
                continue
            for dep in self._dependencies_of(reg, resolver):
                if dep not in self._registry:
                    raise MissingDependencyError(dep, required_by=reg.interface)

    def _check_cycles(self) -> None:
        resolver = Resolver(self._registry)
        visited: set[type] = set()
        path: list[type] = []

        for node in self._registry:
            self._visit(node, resolver, visited, path)

    def _visit(
        self,
        node: type,
        resolver: Resolver,
        visited: set[type],
        path: list[type],
    ) -> None:
        if node in visited or node not in self._registry:
            return

        reg = self._registry[node]
        if reg.strategy == Strategy.INSTANCE:
            visited.add(node)
            return

        if node in path:
            cycle_start = path.index(node)
            raise CyclicDependencyError([*path[cycle_start:], node])

        path.append(node)
        for dep in self._dependencies_of(reg, resolver):
            self._visit(dep, resolver, visited, path)
        path.pop()
        visited.add(node)

    def _check_captive(self) -> None:
        """Reject a singleton or transient that depends on a scoped provider.

        Both can be resolved at the root, where they cache their scoped
        dependency in the permanent root scope, which then never tears down.
        A direct check covers every chain: any deeper capture goes through an
        intermediate that is itself a root-lived provider with a scoped
        dependency, so it is flagged on its own. An alias is no such
        intermediate, so a dependency is judged by what its aliases end at.
        """
        resolver = Resolver(self._registry)
        for reg in self._registry.values():
            if reg.strategy not in (Strategy.SINGLETON, Strategy.TRANSIENT):
                continue
            for dep in self._dependencies_of(reg, resolver):
                dep_reg = self._behind_aliases(dep)
                if dep_reg is not None and dep_reg.strategy == Strategy.SCOPED:
                    raise CaptiveDependencyError(
                        owner_type=reg.interface,
                        owner_strategy=reg.strategy.name.lower(),
                        scoped_type=dep_reg.interface,
                    )

    @classmethod
    def _from_parts(
        cls,
        registry: dict[type, Registration],
        singletons: dict[type, Any],
        hooks: dict[type, list[Registration]],
    ) -> Container:
        container = object.__new__(cls)
        container._registry = registry
        container._hooks = hooks
        container._singletons = singletons
        container._singleton_lifespans = {}
        container._singleton_locks = {}
        container._lifespan = None
        container._async_stack = None
        container._root_scope = Scope(
            registry,
            singletons,
            hooks,
            container._singleton_lifespans,
            container._singleton_locks,
        )
        return container

    def clone(self) -> Container:
        """Create a copy of this container for testing.

        Same registrations, a fresh singleton cache, and instance() values
        copied. Pass the clone to @inject (or resolve from it directly) to use
        it in place of the original. The container-level lifespan= is not
        copied — use per-singleton lifespan= for setup that must run on clones.
        """
        singletons = {
            tp: self._singletons[tp]
            for tp, reg in self._registry.items()
            if reg.strategy == Strategy.INSTANCE and tp in self._singletons
        }
        cloned = self._from_parts(
            self._registry.copy(),
            singletons,
            {k: list(v) for k, v in self._hooks.items()},
        )
        logger.debug("Cloned container")
        return cloned

    def _lifetime_for_replacement(self, interface: type) -> Strategy:
        """Return the lifetime a class that replaces this interface is built with.

        An alias lives as long as what it points at. An instance was handed over
        ready-made and lives as long as the container, which for something dixy
        builds is a singleton. An alias that ends nowhere has no lifetime to
        copy, so its replacement is built anew each time rather than cached
        under a guessed one.
        """
        replaced = self._behind_aliases(interface) or self._registry[interface]
        match replaced.strategy:
            case Strategy.INSTANCE:
                return Strategy.SINGLETON
            case Strategy.ALIAS:
                return Strategy.TRANSIENT
            case strategy:
                return strategy

    def override(
        self, *, interface: type, implementation: type[object] | object
    ) -> None:
        """Replace a registration for testing."""
        if interface not in self._registry:
            raise MissingDependencyError(interface)

        if isinstance(implementation, type):
            if self._registry[interface].strategy == Strategy.INSTANCE:
                # The object bound so far would stay the cached answer.
                self._singletons.pop(interface, None)
            self._registry[interface] = Registration(
                strategy=self._lifetime_for_replacement(interface),
                interface=interface,
                implementation=implementation,
            )
        else:
            self._registry[interface] = Registration(
                strategy=Strategy.INSTANCE,
                interface=interface,
                implementation=type(implementation),
            )
            self._singletons[interface] = implementation
        logger.debug(
            "Overridden %s with %s",
            interface.__name__,
            implementation.__name__
            if isinstance(implementation, type)
            else type(implementation).__name__,
        )
