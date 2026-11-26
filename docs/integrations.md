# Integrations

Dixy has no framework plugins and needs none. Every integration is the same three decisions:

| Decision                      | Usual answer                                                      |
|-------------------------------|-------------------------------------------------------------------|
| Who owns the container        | The process: start it at boot, close it at shutdown               |
| What is one unit of work      | One request, message, job or activity: open a scope for each      |
| How entry points get dependencies | Resolve from the scope, or decorate the function with `@inject` |

## FastAPI

| Piece                         | Role                                                              |
|-------------------------------|-------------------------------------------------------------------|
| The app's lifespan            | Creates the container, binds settings, validates, closes it at shutdown |
| A dependency that yields a scope | Opens the scope for a request and closes it after the response |
| A small helper                | Turns "resolve this type" into a FastAPI dependency               |

FastAPI evaluates a dependency once per request, so everything a request resolves shares one scope.
An error raised by the endpoint, an `HTTPException` included, reaches that scope. Together they make
a scoped unit of work behave as expected: one per request,
[committed or rolled back](providers.md#reacting-to-how-the-work-ended) with it.

```python
def resolved[T](interface: type[T]) -> Any:
    async def dependency(scope: Annotated[Scope, Depends(request_scope)]) -> T:
        return await scope.resolve(interface)

    return Depends(dependency)


@app.get("/users/{user_id}")
async def get_user(user_id: int, service: Annotated[UserService, resolved(UserService)]): ...
```

The complete application, with a unit of work per request, is
[`fastapi_app.py`](../examples/fastapi_app.py). The test suite runs it through FastAPI's test
client.

## Temporal

A Temporal activity is one unit of work, and `@inject` gives each call its own scope. Two things
are specific to Temporal:

- Activities are defined at import time, before the worker creates the container. Decorate them
  with a [container accessor](inject.md#a-container-that-comes-later), and let a
  [container lifespan](container.md#running-code-around-the-container) set and clear the active
  container.
- Temporal reads an activity's signature to decode its input. Injected parameters are
  [hidden from it](inject.md#what-frameworks-see), so the activity's input stays what the workflow
  sends.

```python
@activity.defn
@inject(lambda: active.container)
async def send_notification(params: NotificationParams, service: Inject[Notifier]) -> None:
    await service.send(params)
```

Put `@inject` under `@activity.defn`, so Temporal registers the function that already hides its
injected parameters.

There is no runnable Temporal example in the repository, because it would need a Temporal server.
The behaviour it relies on, the accessor and the hidden parameters, is covered by dixy's own tests.

## Anything else

A queue consumer, a CLI command or a scheduled job follows the same shape: decorate the function
that handles one item with `@inject`, or open a scope around it by hand. If the framework builds
its handlers before your container exists, use the accessor form.
