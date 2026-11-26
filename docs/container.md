# Container and scopes

The container owns what lives as long as the application. A scope owns what lives for one unit of
work. Everything else on this page follows from that split.

## Life of a container

```python
async with AppContainer() as container:
    container.bind(Settings, load_settings())
    container.validate()
    ...  # run the application
```

| Step                 | What happens                                                               |
|----------------------|----------------------------------------------------------------------------|
| Create               | Providers are collected from the modules. Nothing is built yet             |
| `bind`               | You hand over the objects declared with `instance`                         |
| `validate`           | The whole wiring is checked without building anything                      |
| Use                  | Dependencies are built on first use                                        |
| Leave the `with` block | Singletons are [cleaned up](#cleanup)                                    |

A container also works without `async with`, which is convenient in a script or a test. Nothing
closes its singletons then, so use the `with` block wherever cleanup matters.

There is no global registry. Create as many containers as you need: tests usually build a fresh one
per case.

## Scopes

A scope is opened for one unit of work and closed when that work ends, whether it succeeded or
raised.

```python
async with container.scope() as scope:
    service = await scope.resolve(UserService)
```

| Asked from      | Singleton, instance | Transient | Scoped                    |
|-----------------|---------------------|-----------|---------------------------|
| The container   | Resolved            | Resolved  | `OutOfScopeError`         |
| A scope         | Resolved, shared with the container | Resolved | Resolved, one per scope |

Scopes are independent of each other and cheap to open: one per HTTP request or per message is the
intended use.

## Cleanup

A scope cleans up what it built when it closes, and the container does the same for singletons. The
rules are the same for both.

| Rule                                   | What it means                                                       |
|----------------------------------------|---------------------------------------------------------------------|
| Reverse order of creation              | A dependency is closed after whatever uses it                       |
| Every cleanup runs                     | One that fails or is cancelled does not stop the ones after it      |
| Failures are raised at the end         | A single failure as itself, several as one `ExceptionGroup`         |
| The work's own error wins              | If the block raised, that error propagates. Cleanup failures are logged and attached to it as notes |
| A lifespan learns how the work ended   | It receives the error, so it can [commit or roll back](providers.md#reacting-to-how-the-work-ended) |
| A cancellation is never swallowed      | It is raised again once the remaining cleanups have run             |

### Cancellation during cleanup

A task can be cancelled while it is cleaning up: a client disconnects, a timeout fires, the process
is told to stop. Dixy still starts every remaining cleanup, and tells the lifespans among them that
the work was cancelled, so nothing is committed as a success that the caller will see as cancelled.

What dixy cannot do is make a cleanup finish while it is being cancelled itself. Plain asyncio
cancels a task once, so the remaining cleanups complete. anyio cancel scopes, which Starlette and
FastAPI use, keep cancelling until the task ends, and that interrupts each cleanup at its first
`await`. Shield a cleanup that must finish there:

```python
async def close_session(session: Session) -> None:
    with anyio.CancelScope(shield=True):
        await session.close()
```

## Validation

`validate` walks every provider and its dependencies and raises on the first problem it finds. Call
it once at startup, after `bind`. A wiring mistake then stops the deploy instead of failing a
request.

It catches a dependency that nobody provides, a cycle, a declared instance that was never bound,
and a long-lived dependency that holds on to a scoped one. [Errors](errors.md) lists each with its
cause and fix, and [`startup_validation.py`](../examples/startup_validation.py) triggers them.

Validation reads everything dixy would call to build a dependency: constructors, factories,
lifespans, `setup` callbacks and hooks. The one thing it cannot know about is a
[required plain value](wiring.md#plain-values) that was never passed.

## Concurrency

Resolving is safe to do from many tasks at once. When several tasks ask for the same singleton, or
the same scoped dependency within one scope, for the first time together, exactly one instance is
built and all of them get it.

## Running code around the container

A container accepts a `lifespan`: a context manager that receives the container, is entered when
the container starts, and exits before the singletons are cleaned up. Use it for what must happen
exactly while the container is alive, such as making the container reachable for
[functions decorated before it existed](inject.md#a-container-that-comes-later) and removing it
again at shutdown.

```python
async with AppContainer(lifespan=publish_container) as container:
    ...
```

## Logging

Dixy logs through the standard `logging` module, on loggers named `dixy.*`.

| Level     | What is logged                                                  |
|-----------|-----------------------------------------------------------------|
| `INFO`    | Container created, instance bound, validation passed, container closed |
| `WARNING` | Validation failed, with the reason                              |
| `ERROR`   | A cleanup failed while another error was already propagating    |
| `DEBUG`   | Every single resolution                                         |

`DEBUG` produces hundreds of records for a large scope. If your application sends debug logs
somewhere costly, set the `dixy` logger to `INFO` or higher.
