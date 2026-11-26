# Dixy

Minimalist, type-driven dependency injection library for Python 3.12+. Async-first, fully typed.

## Public API

```python
from dixy import Container, Lifespan, Module, Scope, Inject, inject
from dixy import singleton, scoped, transient, instance, alias, hook, select, or_, and_
```

______________________________________________________________________

## Lifetimes

| Lifetime    | Created                    | Cached            | Torn down                           |
| ----------- | -------------------------- | ----------------- | ----------------------------------- |
| `singleton` | First `resolve()`          | One per container | Container close (`__aexit__`)       |
| `scoped`    | First `resolve()` in scope | One per scope     | Scope close                         |
| `transient` | Every `resolve()`          | Never             | Not managed                         |
| `instance`  | Outside container          | One per container | Not managed (user's responsibility) |
| `alias`     | Never (delegates)          | Via source        | Via source                          |

______________________________________________________________________

## Module

Base class for grouping related dependency registrations as class attributes.

Providers are collected from class attributes only — not inherited from parent modules. Use composition (multiple modules in Container) instead of module inheritance.

```python
class InfraModule(Module):
    db = instance(DbPool)
    events = singleton(EventBus, InMemoryEventBus)

class DomainModule(Module):
    repo = scoped(UserRepository, PgUserRepo)
    read_repo = alias(ReadOnlyRepository, UserRepository)
    service = scoped(UserService)
    validator = transient(InputValidator)
```

______________________________________________________________________

## Provider Functions

### singleton(interface, implementation?, \*, factory?, setup?, teardown?, lifespan?, \*\*kwargs)

One instance per container lifetime. Torn down when the container closes.

### scoped(interface, implementation?, \*, factory?, setup?, teardown?, lifespan?, \*\*kwargs)

One instance per scope. Torn down when the scope closes.

### transient(interface, implementation?, \*, factory?, setup?, \*\*kwargs)

New instance every `resolve()`. No teardown — caller manages lifecycle.

### alias(interface, source)

Resolve interface as the same instance as source. No new instance — delegates to `resolve(source)`.

```python
repo = scoped(UserRepository, PgUserRepo)
read_repo = alias(ReadOnlyRepository, UserRepository)
# scope.resolve(ReadOnlyRepository) is scope.resolve(UserRepository) → True
```

### instance(interface)

Pre-built instance provided via `container.bind()`. Declare in module, bind at startup.

### hook(interface, \*, setup?, teardown?)

Attach extra `setup` / `teardown` callbacks to a registration declared in another module, so a module can extend a shared service without owning its registration. The callbacks receive the same instance; a hook's setup runs after the owner's own. At least one of the two is required.

```python
class OrdersModule(Module):
    handlers = hook(Mediator, setup=register_order_handlers)
```

### select(interface)

Create a lazy selector for extracting values from a registered dependency. Use in kwargs to pass individual fields instead of injecting the whole object.

Supports attribute access, method calls, and item access:

```python
class InfraModule(Module):
    settings = instance(Settings)
    storage = scoped(S3Storage, bucket_name=select(Settings).s3_bucket)
    cache = scoped(RedisCache, url=select(Settings).redis.url)                    # nested
    db = scoped(Database, dsn=select(Settings).password.get_secret_value())        # method call
    primary = scoped(PrimaryDb, dsn=select(Settings).databases["primary"])         # item access
```

### or\_ / and\_

Fallback helpers for selectors. `or_` returns the fallback when the resolved value is falsy (`None`, `""`, `0`). `and_` substitutes the value when truthy. Both accept literals or other selectors as fallback:

```python
from dixy import select, or_, and_

# Literal fallback
ns = or_(select(Settings).namespace, "default")

# Selector fallback — resolved from the container
ns = or_(select(Settings).namespace, select(Defaults).namespace)

# Conditional extraction (get_secret_value only if api_key is not None)
key = and_(select(Settings).api_key, select(Settings).api_key.get_secret_value())
```

Selectors are resolved lazily when the dependent service is created. The source type must be registered in the container — `validate()` catches missing sources, cycles, and captive dependencies involving selectors.

### Common parameters

- **interface** — type used as lookup key for `resolve()`
- **implementation** — concrete class to instantiate. Defaults to interface when omitted
- **factory** — custom callable instead of auto-resolve. Supports async factories
- **setup** — callback run on every new instance right after it is created. Receives the instance as its first argument; any other parameters are resolved from the container. Supports async
- **teardown** — cleanup callback called on scope/container close. Supports async
- **lifespan** — context manager (sync or async) whose entered value becomes the instance; it is exited on scope/container close. Its parameters are resolved like constructor arguments. Mutually exclusive with `factory`, `setup`, and `teardown`; not available for `transient`
- **kwargs** — explicit constructor arguments (for primitives that can't be auto-resolved)

______________________________________________________________________

## Container

### Defining

```python
class AppContainer(Container):
    modules = (InfraModule, DomainModule)
```

Create as many container instances as you need — there is no global registry. Tests typically build a fresh container per case.

### Lifecycle

Container is an async context manager. Singleton teardown callbacks are called on exit.

```python
async with AppContainer() as container:
    container.bind(DbPool, pool)
    container.validate()
    # app runs
# singletons torn down
```

### bind(interface, value)

Bind a pre-built instance for an `instance()` declaration. Call before `validate()`.

### validate()

Check the dependency graph at startup. Raises on:

| Error                      | Cause                                         |
| -------------------------- | --------------------------------------------- |
| `MissingDependencyError`   | Dependency type not registered                |
| `CyclicDependencyError`    | A depends on B depends on A                   |
| `CaptiveDependencyError`   | Singleton or transient depends on scoped      |
| `InstanceNotProvidedError` | `instance()` declared but `bind()` not called |

### resolve(interface)

Resolve a dependency by type, supporting sync and async factories. Resolving a scoped dependency from the container raises `OutOfScopeError` — use a scope.

### scope()

Create a scope for resolving scoped dependencies.

```python
async with container.scope() as scope:
    service = await scope.resolve(UserService)
```

### clone()

Create a copy for testing. Same registrations, fresh singleton cache, `instance()` values copied. Pass the clone to `@inject` (or resolve from it directly) to use it in place of the original.

### override(\*, interface, implementation)

Replace a registration. Accepts a type (auto-resolved) or an object (used directly).

```python
test = container.clone()
test.override(interface=UserRepository, implementation=FakeUserRepo)          # type
test.override(interface=DbPool, implementation=DbPool(dsn="fake://"))          # object
test.validate()
```

______________________________________________________________________

## Scope

Returned by `container.scope()`. Resolves all lifetimes.

### resolve(interface)

Same as the container but also resolves scoped dependencies.

### teardown()

Called automatically on scope exit. Tears down scoped dependencies with `teardown=` callbacks in reverse creation order.

______________________________________________________________________

## @inject

Decorator that resolves `Inject[T]` parameters from the container. Opens a scope per call.

```python
container = AppContainer()

@inject(container)
async def handle(user_id: int, service: Inject[UserService]) -> None:
    user = await service.get(user_id)
```

- Takes a container instance, or a `() -> Container` accessor for late binding (framework entry points defined before the container exists)
- Parameters without `Inject[T]` passed by caller as usual
- Requires an async function; resolves via `resolve()`
- Opens a scope per call, torn down on return

______________________________________________________________________

## Auto-resolve

When no `factory` is provided, dependencies are resolved by inspecting `__init__` type hints.

For each parameter:

1. Already in explicit kwargs → use it
1. `Optional[T]` / `T | None` → resolve T if registered, else `None`
1. Primitive (`int`, `str`, `float`, `bool`, `bytes`) → use default or skip
1. Type registered → resolve recursively
1. Has default → use default
1. Otherwise → `MissingDependencyError`

Supports: regular classes, dataclasses, Pydantic BaseModel, `from __future__ import annotations`.

Type hints and defaults are read once per class or factory and cached, so a scope rebuilt on every request does not read them again. The cache holds its keys weakly: a factory created on the fly leaves no entry behind once it is dropped. Hints are read on first use, so a forward reference must resolve by then.

Every resolution is logged at `DEBUG` on the `dixy` loggers, hundreds of records for a large scope. An app that routes stdlib logging somewhere costly should raise `dixy` to `WARNING`.

______________________________________________________________________

## Async Factories

Factories can be async. Use `resolve()` for resolution:

```python
async def create_pool() -> DbPool:
    return await asyncpg.create_pool("postgres://...")

class InfraModule(Module):
    db = singleton(DbPool, factory=create_pool)

# Resolve from the container
pool = await container.resolve(DbPool)

# Or in a scope
async with container.scope() as scope:
    pool = await scope.resolve(DbPool)
```

______________________________________________________________________

## Testing

```python
# Clone + override
test = container.clone()
test.override(interface=UserRepository, implementation=FakeUserRepo)
test.override(interface=EventBus, implementation=InMemoryEventBus)
test.validate()

async with test.scope() as scope:
    service = await scope.resolve(UserService)
    # gets FakeUserRepo, not PgUserRepo

# With @inject — decorate with the container under test
test = container.clone()
test.override(interface=UserRepository, implementation=FakeUserRepo)

@inject(test)
async def handler(repo: Inject[UserRepository]) -> None: ...

await handler()  # uses the overridden clone
```

______________________________________________________________________

## Exceptions

| Exception                    | When                                     |
| ---------------------------- | ---------------------------------------- |
| `DixyError`                  | Base for all dixy errors                 |
| `MissingDependencyError`     | Dependency not registered                |
| `CyclicDependencyError`      | Circular dependency in graph             |
| `CaptiveDependencyError`     | Singleton or transient depends on scoped |
| `OutOfScopeError`            | Resolving scoped from container directly |
| `InstanceNotProvidedError`   | `instance()` without `bind()`            |
| `DuplicateRegistrationError` | Conflicting providers for one interface  |

______________________________________________________________________

## Integration Examples

### FastAPI

```python
# container.py
class InfraModule(Module):
    db = instance(DbPool)

class DomainModule(Module):
    repo = scoped(UserRepository, PgUserRepo)
    service = scoped(UserService)

class AppContainer(Container):
    modules = (InfraModule, DomainModule)

# dependencies.py
async def get_scope(request: Request):
    async with request.app.state.container.scope() as scope:
        yield scope

def Provide[T](interface: type[T]) -> T:
    """Resolve a dependency from the request scope via FastAPI Depends."""
    async def dep(scope=Depends(get_scope)):
        return await scope.resolve(interface)
    return Depends(dep)

# routes/users.py
router = APIRouter()

@router.get("/users/{user_id}")
async def get_user(
    user_id: int,
    service: UserService = Provide(UserService),
):
    return await service.get(user_id)

# factory.py
def create_app(container: AppContainer) -> FastAPI:
    app = FastAPI()
    app.state.container = container
    app.include_router(router)
    return app

# main.py
async def main():
    pool = await create_pool("postgres://...")

    async with AppContainer() as container:
        container.bind(DbPool, pool)
        container.validate()
        app = create_app(container)
        # run app
    # singletons torn down
```

`Provide(T)` is a user-defined helper, not part of dixy. FastAPI caches `Depends` per request, so `get_scope` is called once — all `Provide(T)` in a route share the same scope.

### Temporal Activity

```python
# container.py
class AppContainer(Container):
    modules = (InfraModule, DomainModule)

# activities.py — the container is created later (in the worker), so resolve
# it lazily through an accessor. A lifespan sets the binding on startup and
# clears it on shutdown, so a torn-down container is never reused.
class _Active:
    container: Container | None = None

@asynccontextmanager
async def activity_lifespan(container: Container) -> AsyncIterator[None]:
    _Active.container = container
    try:
        yield
    finally:
        _Active.container = None

@activity.defn
@inject(lambda: _Active.container)
async def send_notification(
    params: NotificationParams,
    service: Inject[NotificationService],
) -> None:
    await service.send(params)

# worker.py
async def run_worker():
    async with AppContainer(lifespan=activity_lifespan) as container:
        container.bind(DbPool, await create_pool("postgres://..."))
        container.validate()

        worker = Worker(client=client, activities=[send_notification])
        await worker.run()
    # singletons torn down, binding cleared
```
