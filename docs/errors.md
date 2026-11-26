# Errors

Every error dixy raises about wiring derives from `DixyError` and lives in `dixy.exceptions`. Most
of them appear at startup, from [`validate`](container.md#validation), which is the point of
calling it.

## Wiring errors

| Error                        | Raised                         | Cause                                               | Fix                                                        |
|------------------------------|--------------------------------|-----------------------------------------------------|------------------------------------------------------------|
| `MissingDependencyError`     | Validation, or resolving       | A class or a hook names a type that no module provides, or you asked for one | Add a provider, or list the module that has it in the container |
| `CyclicDependencyError`      | Validation                     | Dependencies form a loop, through constructors, factories, `setup` callbacks or hooks | Break the loop: extract what both sides need into a third class |
| `CaptiveDependencyError`     | Validation                     | A singleton or transient depends on a scoped dependency | Make the owner scoped, or the dependency a singleton   |
| `InstanceNotProvidedError`   | Validation, or resolving       | A dependency declared with `instance` was never bound | Call `bind` before `validate`                            |
| `OutOfScopeError`            | Resolving from the container   | A scoped dependency was asked for outside a scope   | Resolve it from `container.scope()`                        |
| `DuplicateRegistrationError` | Creating the container         | Two modules provide the same interface              | Keep the provider in one module, or use `alias`            |

The message names the types involved. For a cycle it shows the whole chain, and for a missing
dependency it says which class asked for it.

## Why a singleton must not depend on a scoped dependency

A singleton is built once and kept. If it took a scoped dependency, it would hold the one from
whichever scope happened to build it, and keep using it after that scope closed: a database session
that is already returned to the pool, or one request's user in another request. A transient has the
same problem when it is resolved from the container. Dixy refuses the wiring instead of letting it
fail later and far away.

## Errors during cleanup

A failing `teardown` or lifespan exit never skips the cleanups after it. What you see depends on
how the scope or container ended. [Cleanup](container.md#cleanup) has the full rules.

| The work itself | Cleanup failures | What is raised                                                  |
|-----------------|------------------|-----------------------------------------------------------------|
| Succeeded       | One              | That failure                                                    |
| Succeeded       | Several          | An `ExceptionGroup` holding all of them                         |
| Raised          | Any              | The work's error, with each cleanup failure logged and added as a note |

## Usage errors

These are ordinary Python exceptions, raised where the mistake is made.

| Error          | Raised when                                                                    |
|----------------|--------------------------------------------------------------------------------|
| `TypeError`    | `@inject` decorates a function that is not `async`                             |
| `RuntimeError` | An `@inject` accessor returns no container when the function is called         |
| `ValueError`   | A provider combines `lifespan` with `factory`, `setup` or `teardown`, or a hook has no callback |
| `TypeError`    | A constructor needs a [plain value](wiring.md#plain-values) that was never passed |
