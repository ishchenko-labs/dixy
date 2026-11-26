# Providers

A provider is one line in a module. It names an interface, says how to get an instance of it, and
fixes how long that instance lives.

## Lifetimes

| Provider    | Created                     | Shared within     | Cleaned up when           |
|-------------|-----------------------------|-------------------|---------------------------|
| `singleton` | On first use                | The container     | The container closes      |
| `scoped`    | On first use in a scope     | That scope        | The scope closes          |
| `transient` | On every use                | Nothing           | Never: the caller owns it |
| `instance`  | By you, before startup      | The container     | Never: you own it         |
| `alias`     | Never: it points at another | Same as its source| With its source           |

Pick the shortest lifetime that is still correct. Connection pools and clients are singletons. A
database session, a unit of work, or anything that carries one request's state is scoped. A value
that must be fresh every time is transient.

A longer-lived dependency must not depend on a shorter-lived one: a singleton holding a scoped
object would keep it alive after its scope closed. [Validation](container.md#validation) rejects
this.

[`lifetimes.py`](../examples/lifetimes.py) shows every row of the table.

## Interface and implementation

The first argument is the interface: the type other code asks for. The optional second argument is
the class that implements it.

```python
class DomainModule(Module):
    service = scoped(UserService)                    # interface and implementation are the same
    users = scoped(UserRepository, PgUserRepository)  # ask for the first, get the second
```

An interface can be a concrete class, a base class, an abstract class, or a `Protocol`. For an
abstract class or a `Protocol`, mypy cannot infer the result of `resolve`, so annotate the variable
you assign it to.

## Building and cleaning up

By default dixy calls the implementation's constructor and [fills its arguments](wiring.md). Four
options change that. Each accepts a sync or async callable.

| Option     | Use it when                                             | Receives                                        |
|------------|---------------------------------------------------------|-------------------------------------------------|
| `factory`  | Construction is more than a constructor call            | Its own parameters, filled like a constructor's |
| `setup`    | A new instance needs one more step before use           | The instance first, then any other dependencies |
| `teardown` | The instance must be closed                             | The instance                                    |
| `lifespan` | Creation and cleanup belong together in one `with` block| Its own parameters; what it yields is the instance |

`lifespan` takes a context manager, sync or async, and replaces the other three: it cannot be
combined with them. `transient` accepts neither `teardown` nor `lifespan`, because nothing tracks a
transient instance after it is handed out.

[Cleanup](container.md#cleanup) runs in reverse order of creation, so a dependency is always closed
after whatever uses it.

[`lifecycle.py`](../examples/lifecycle.py) uses all four.

### Reacting to how the work ended

A lifespan is exited the way a `with` block exits it: when an error ends the scope, the lifespan
receives that error. This is where a transaction or a unit of work decides between commit and
rollback.

```python
@asynccontextmanager
async def transaction(pool: Pool) -> AsyncIterator[Transaction]:
    tx = await pool.begin()
    try:
        yield tx
    except BaseException:
        await tx.rollback()
        raise
    else:
        await tx.commit()
```

| Callback   | Knows whether the work failed | Can stop the error                         |
|------------|-------------------------------|--------------------------------------------|
| `lifespan` | Yes                           | No: the error propagates whatever it does  |
| `teardown` | No                            | No                                         |

A singleton's lifespan gets the error that ended the container's `with` block, by the same rule.

## Sharing one instance under two interfaces

`alias` makes a second interface resolve to the same instance as the first. Use it to hand some
code a narrower view of an object, such as a read-only interface of a repository.

```python
users = scoped(UserRepository, PgUserRepository)
readers = alias(UserReader, UserRepository)
```

An alias has no lifetime of its own. Every rule that applies to its source applies to it.

## Instances built outside the container

`instance` declares a dependency that you create yourself and hand over with `bind` before the
application starts. Settings loaded from the environment are the usual case.

```python
class InfraModule(Module):
    settings = instance(Settings)

container.bind(Settings, load_settings())
```

The container never creates or closes such an object.

## Modules

A module is a way to keep providers next to the code they belong to. A container lists its modules.
Their order decides only one thing: the order in which hooks on the same service run.

Three rules keep modules predictable:

- A module's providers are the ones written in its own body. Subclassing a module does not inherit
  them: compose modules in the container instead.
- An interface has one owner. Two modules that provide the same interface is an error, raised when
  the container is created. The exceptions are `instance` declarations and aliases with the same
  source, which may repeat.
- A module can extend a service it does not own with `hook`, which adds a `setup` or `teardown`
  callback to another module's provider. This is how a feature module registers its handlers on a
  shared bus without the bus knowing about it.

A hook follows the instance it is attached to:

| The hook names                    | What happens                                                       |
|-----------------------------------|--------------------------------------------------------------------|
| A singleton or scoped dependency  | `setup` runs when it is built, `teardown` when it is cleaned up    |
| An alias                          | The same, for the instance behind the alias                        |
| A transient                       | `setup` runs for every new instance. `teardown` never runs: nobody tracks a transient |
| An `instance`                     | Nothing: dixy neither builds nor closes it                         |
| An interface nobody provides      | [Validation](container.md#validation) reports it                   |

[`modules.py`](../examples/modules.py) shows a hook across modules.
