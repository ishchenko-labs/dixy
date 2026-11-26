# Dixy documentation

Dixy wires an async Python application together from type hints. You say which classes exist and
how long each one lives; dixy builds them in the right order, hands them to whoever asks, and
cleans them up afterwards.

## The model in one minute

| Piece         | What it is                                                                            |
|---------------|---------------------------------------------------------------------------------------|
| **Provider**  | One line that says how to get a dependency and how long it lives                      |
| **Module**    | A plain class that groups related providers                                           |
| **Container** | The application's set of modules. Owns everything that lives as long as the app       |
| **Scope**     | A short-lived child of the container: one request, one job, one message               |
| **Interface** | The type you ask for. Often the class itself, sometimes a base class or a `Protocol`  |

```python
class AppModule(Module):
    settings = instance(Settings)                # built by you, bound at startup
    pool = singleton(ConnectionPool)             # one per container
    session = scoped(Session)                    # one per scope
    request_id = transient(RequestId)            # a new one every time

class AppContainer(Container):
    modules = (AppModule,)
```

Your own classes stay free of dixy: no decorators, no base classes, no container passed around. A
class declares what it needs in its constructor, and that is the whole contract.

## Guides

| Guide                                | Read it when you want to                                         |
|--------------------------------------|------------------------------------------------------------------|
| [Providers](providers.md)            | Choose a lifetime, add a factory or cleanup, share one instance  |
| [Wiring](wiring.md)                  | Know how constructor arguments get filled, and pass plain values |
| [Container and scopes](container.md) | Start and stop the app, open scopes, validate the wiring         |
| [Injecting into functions](inject.md)| Fill the parameters of handlers, jobs and activities             |
| [Testing](testing.md)                | Replace real dependencies with fakes                             |
| [Integrations](integrations.md)      | Use dixy with FastAPI, Temporal, or another framework            |
| [Errors](errors.md)                  | Understand an exception and fix what caused it                   |

## Examples

Every file in [`examples/`](../examples) runs on its own, and the test suite runs each one, so they
stay correct. Start any of them with `python examples/<name>.py`.

| Example                                                        | Shows                                                    |
|----------------------------------------------------------------|----------------------------------------------------------|
| [`quickstart.py`](../examples/quickstart.py)                   | The smallest complete application                        |
| [`lifetimes.py`](../examples/lifetimes.py)                     | What each lifetime shares, and the order of cleanup      |
| [`lifecycle.py`](../examples/lifecycle.py)                     | Factories, setup and teardown callbacks, and a lifespan that commits or rolls back |
| [`modules.py`](../examples/modules.py)                         | Several modules, and one module extending another's service |
| [`settings_fields.py`](../examples/settings_fields.py)         | Passing single settings fields with selectors            |
| [`inject_handlers.py`](../examples/inject_handlers.py)         | `@inject` with a container that exists or comes later    |
| [`testing_overrides.py`](../examples/testing_overrides.py)     | Cloning a container and overriding dependencies          |
| [`startup_validation.py`](../examples/startup_validation.py)   | The wiring mistakes that validation catches              |
| [`fastapi_app.py`](../examples/fastapi_app.py)                 | One scope and one unit of work per HTTP request in FastAPI |
