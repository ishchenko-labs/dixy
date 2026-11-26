from __future__ import annotations

import asyncio
import inspect
import logging
from collections.abc import Callable
from typing import Any, assert_never, cast, overload

from .exceptions import InstanceNotProvidedError, MissingDependencyError
from .resolver import Resolver
from .selector import Selector, _Call, _GetAttr, _GetItem, replay
from .types import UNRESOLVED, Registration, Strategy

logger = logging.getLogger(__name__)


def _format_selector(selector: Selector) -> str:
    """Format selector as readable chain: Settings.db_dsn, Settings.redis.url."""
    parts = [selector.get_interface().__name__]
    for op in selector.get_ops():
        match op:
            case _GetAttr(name=name):
                parts.append(name)
            case _Call():
                parts[-1] += "()"
            case _GetItem(key=key):
                parts[-1] += f"[{key!r}]"
    return ".".join(parts)


def _exit_lifespan(cm: Any) -> Callable[[Any], Any]:
    """Wrap a context manager exit into a teardown-callback shape (instance, fn)."""
    if hasattr(cm, "__aexit__"):

        async def aexit(_instance: Any) -> None:
            await cm.__aexit__(None, None, None)

        return aexit

    def exit_(_instance: Any) -> None:
        cm.__exit__(None, None, None)

    return exit_


class Scope:
    def __init__(
        self,
        registry: dict[type, Registration],
        singletons: dict[type, Any],
        hooks: dict[type, list[Registration]] | None = None,
        singleton_lifespans: dict[type, Any] | None = None,
        singleton_locks: dict[type, asyncio.Lock] | None = None,
    ) -> None:
        self._registry = registry
        self._singletons = singletons
        self._hooks = hooks if hooks is not None else {}
        self._singleton_lifespans = singleton_lifespans
        self._singleton_locks = singleton_locks if singleton_locks is not None else {}
        self._scoped: dict[type, Any] = {}
        self._scoped_locks: dict[type, asyncio.Lock] = {}
        self._teardown_callbacks: list[tuple[object, Callable[[Any], Any]]] = []
        self._resolver = Resolver(registry)

    @overload
    async def resolve[T](self, interface: type[T]) -> T: ...
    @overload
    async def resolve(self, interface: Any) -> Any: ...
    async def resolve(self, interface: Any) -> Any:
        """Resolve a dependency, supporting async factories."""
        reg = self._get_registration(interface)
        if reg.strategy == Strategy.ALIAS:
            logger.debug(
                "Resolved %s -> %s (alias)",
                interface.__name__,
                reg.implementation.__name__,
            )
            return await self.resolve(reg.implementation)

        self._guard_instance(interface, reg)

        cached = self._get_cached(interface, reg)
        if cached is not UNRESOLVED:
            logger.debug("Resolved %s (cached)", interface.__name__)
            return cached

        lock = self._lock_for(interface, reg)
        if lock is None:
            return await self._create_and_store(interface, reg)

        async with lock:
            # Double-check: another coroutine may have created it while we waited.
            cached = self._get_cached(interface, reg)
            if cached is not UNRESOLVED:
                logger.debug("Resolved %s (cached)", interface.__name__)
                return cached
            return await self._create_and_store(interface, reg)

    async def _create_and_store(self, interface: type, reg: Registration) -> Any:
        instance = await self._create(reg)
        self._store(interface, reg, instance)
        logger.debug("Resolved %s (%s)", interface.__name__, reg.strategy.name)
        return instance

    def _get_registration(self, interface: type) -> Registration:
        if interface not in self._registry:
            raise MissingDependencyError(interface)
        return self._registry[interface]

    def _guard_instance(self, interface: type, reg: Registration) -> None:
        if reg.strategy == Strategy.INSTANCE and interface not in self._singletons:
            raise InstanceNotProvidedError(interface)

    def _lock_for(self, interface: type, reg: Registration) -> asyncio.Lock | None:
        """Return the creation lock for cached strategies, None for uncached ones.

        Singleton locks are shared across scopes (singletons are container-wide);
        scoped locks are per-scope. Serializing creation per key stops concurrent
        first-resolve from building two instances and leaking one.
        """
        match reg.strategy:
            case Strategy.SINGLETON:
                locks = self._singleton_locks
            case Strategy.SCOPED:
                locks = self._scoped_locks
            case _:
                return None
        lock = locks.get(interface)
        if lock is None:
            lock = asyncio.Lock()
            locks[interface] = lock
        return lock

    def _get_cached(self, interface: type, reg: Registration) -> Any:
        match reg.strategy:
            case Strategy.INSTANCE | Strategy.SINGLETON:
                if interface in self._singletons:
                    return self._singletons[interface]
            case Strategy.SCOPED:
                if interface in self._scoped:
                    return self._scoped[interface]
            case Strategy.TRANSIENT | Strategy.ALIAS | Strategy.HOOK:
                ...
            case _ as unreachable:
                assert_never(unreachable)
        return UNRESOLVED

    def _store(self, interface: type, reg: Registration, instance: Any) -> None:
        match reg.strategy:
            case Strategy.SINGLETON:
                self._singletons[interface] = instance
            case Strategy.SCOPED:
                self._scoped[interface] = instance
                if reg.teardown:
                    self._teardown_callbacks.append((instance, reg.teardown))
                for hook_reg in self._hooks.get(interface, []):
                    if hook_reg.teardown:
                        self._teardown_callbacks.append((instance, hook_reg.teardown))
            case Strategy.TRANSIENT | Strategy.INSTANCE | Strategy.ALIAS:
                ...
            case Strategy.HOOK:
                ...
            case _ as unreachable:
                assert_never(unreachable)

    async def _create(self, reg: Registration) -> Any:
        """Create an instance, awaiting async factories/lifespans if needed."""
        if reg.lifespan:
            result = await self._enter_lifespan(reg)
        else:
            target = reg.factory or reg.implementation
            resolved_kwargs = await self._resolve_selectors(reg.kwargs)
            kwargs = await self._resolver.build_kwargs(
                target=target,
                resolve_fn=self.resolve,
                explicit_kwargs=resolved_kwargs,
            )
            result = target(**kwargs)
            if reg.factory and inspect.iscoroutine(result):
                result = await result
            if reg.setup:
                await self._run_setup(reg.setup, result)
        for hook_reg in self._hooks.get(reg.interface, []):
            if hook_reg.setup:
                await self._run_setup(hook_reg.setup, result)
        return result

    async def _enter_lifespan(self, reg: Registration) -> Any:
        lifespan = cast("Callable[..., Any]", reg.lifespan)
        resolved_kwargs = await self._resolve_selectors(reg.kwargs)
        kwargs = await self._resolver.build_kwargs(
            target=lifespan,
            resolve_fn=self.resolve,
            explicit_kwargs=resolved_kwargs,
        )
        cm = lifespan(**kwargs)
        if hasattr(cm, "__aenter__"):
            instance = await cm.__aenter__()
        else:
            instance = cm.__enter__()
        self._record_lifespan(reg, cm, instance)
        return instance

    def _record_lifespan(self, reg: Registration, cm: Any, instance: Any) -> None:
        if reg.strategy == Strategy.SCOPED:
            self._teardown_callbacks.append((instance, _exit_lifespan(cm)))
        elif reg.strategy == Strategy.SINGLETON:
            if self._singleton_lifespans is None:
                msg = "singleton lifespan requires a Container-managed scope"
                raise RuntimeError(msg)
            self._singleton_lifespans[reg.interface] = cm

    async def _run_setup(self, setup_fn: Callable[..., Any], instance: Any) -> None:
        kwargs = await self._resolver.build_kwargs(
            target=setup_fn,
            resolve_fn=self.resolve,
            explicit_kwargs=self._instance_as_first_arg(setup_fn, instance),
        )
        result = setup_fn(**kwargs)
        if inspect.iscoroutine(result):
            await result

    @staticmethod
    def _instance_as_first_arg(
        setup_fn: Callable[..., Any], instance: Any
    ) -> dict[str, Any]:
        sig = inspect.signature(setup_fn)
        first_param = next(iter(sig.parameters), None)
        return {first_param: instance} if first_param else {}

    async def _resolve_selectors(self, kwargs: dict[str, Any]) -> dict[str, Any]:
        resolved: dict[str, Any] = {}
        for k, v in kwargs.items():
            if isinstance(v, Selector):
                resolved[k] = await self._resolve_selector(v)
            else:
                resolved[k] = v
        return resolved

    async def _resolve_selector(self, selector: Selector) -> Any:
        obj: Any = await self.resolve(selector.get_interface())
        result = await replay(selector, obj, resolve=self._resolve_selector)
        logger.debug("Resolved selector %s", _format_selector(selector))
        return result

    async def teardown(self) -> None:
        """Tear down all scoped dependencies in reverse creation order."""
        torn_down = 0
        for instance, teardown_fn in reversed(self._teardown_callbacks):
            result = teardown_fn(instance)
            if asyncio.iscoroutine(result):
                await result
            torn_down += 1
        if torn_down:
            logger.debug("Scope torn down, %d instances cleaned up", torn_down)
