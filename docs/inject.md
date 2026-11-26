# Injecting into functions

Classes get their dependencies through constructors. Functions that a framework calls for you, such
as request handlers, queue consumers and workflow activities, have no constructor. `@inject` fills
their parameters instead.

```python
@inject(container)
async def handle(user_id: int, service: Inject[UserService]) -> None:
    await service.deactivate(user_id)

await handle(42)
```

## What one call does

1. Opens a new [scope](container.md#scopes).
2. Resolves every parameter marked `Inject[...]` from it.
3. Calls the function with the caller's arguments plus the resolved ones.
4. Closes the scope when the function returns or raises.

Each call is therefore its own unit of work: scoped dependencies are shared within the call and
cleaned up right after it. An error raised by the function reaches the scope, so a scoped
[lifespan](providers.md#reacting-to-how-the-work-ended) rolls back exactly the calls that failed.

## Rules

| Rule                                         | Why                                                             |
|----------------------------------------------|-----------------------------------------------------------------|
| The function must be `async`                 | Resolution is asynchronous. A sync function is rejected when it is decorated |
| Put injected parameters last                 | The caller passes its own arguments positionally; injected ones are added by name |
| An argument the caller passes by name wins   | A test can hand in a fake for one call without touching the container |
| Unmarked parameters are left alone           | They are the caller's to pass                                   |

## What frameworks see

Many frameworks read a function's signature to decide what to pass or how to decode a payload. The
decorated function shows them only the caller's parameters. Injected ones are hidden, so a
framework neither tries to supply them nor rejects them as unknown.

## A container that comes later

Framework entry points are usually defined at import time, long before the application builds its
container. For that case `@inject` accepts a function that returns the container instead of the
container itself. It is called on every invocation, so it always sees the container that is active
now.

```python
@inject(lambda: active.container)
async def handle(user_id: int, service: Inject[UserService]) -> None: ...
```

If it returns `None` when the function is called, the call fails with a clear error instead of an
obscure one. Set and clear the active container with a
[container lifespan](container.md#running-code-around-the-container), so that it can never point at
a closed container.

[`inject_handlers.py`](../examples/inject_handlers.py) shows both forms and a per-call override.
