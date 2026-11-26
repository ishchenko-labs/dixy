# Wiring

Dixy fills constructor arguments from type hints. This page says exactly how, so that nothing about
it is a surprise.

## How each argument is filled

For every parameter of a constructor, factory or lifespan, and every parameter of a `setup` callback
after the instance it sets up, the first rule that matches wins:

| The parameter                                    | Gets                                            |
|--------------------------------------------------|-------------------------------------------------|
| Is named in the provider's keyword arguments     | That value                                      |
| Is optional (`T \| None`)                        | `T` if it is registered, otherwise its default or `None` |
| Is a primitive (`int`, `str`, `float`, `bool`, `bytes`) | Its default, if it has one                |
| Has a registered type                            | That dependency, resolved                       |
| Has a default                                    | The default                                     |
| Anything else                                    | `MissingDependencyError`                        |

Regular classes, dataclasses and Pydantic models all work, with or without
`from __future__ import annotations`.

Dependencies of one constructor are resolved concurrently, so two slow async factories that a class
needs do not wait for each other.

## Plain values

A primitive is never looked up in the container: there is no meaningful single `str` to inject.
Pass plain values as keyword arguments of the provider.

```python
cache = singleton(Cache, url="redis://localhost", timeout=5)
```

A required primitive with no default and no keyword argument is the one wiring mistake that
[validation](container.md#validation) cannot see. It fails when the instance is first created, as
an ordinary `TypeError` from the constructor.

## Values from another dependency

Most plain values come from a settings object. `select` passes one field of a registered dependency
instead of the whole object, so a class asks for the `url` it needs and never learns that a
settings class exists.

```python
class InfraModule(Module):
    settings = instance(Settings)
    cache = singleton(Cache, url=select(Settings).redis.url)
```

A selector records what you do to it and replays that on the real object when the dependent
instance is created:

| You write                         | At creation time it does          |
|-----------------------------------|-----------------------------------|
| `select(Settings).redis.url`      | Reads attributes, nested or not   |
| `select(Settings).queues["mail"]` | Reads an item                     |
| `select(Settings).dsn.render()`   | Calls a method, awaiting it if it is async |
| `or_(selector, fallback)`         | Uses the fallback when the value is falsy  |
| `and_(selector, replacement)`     | Uses the replacement when the value is truthy |

A fallback or replacement can be a plain value or another selector.

The dependency a selector reads from is a real dependency of the provider. Validation checks that
it is registered and counts it when looking for cycles and lifetime mistakes.

[`settings_fields.py`](../examples/settings_fields.py) shows each form.

## Cost

Type hints and defaults are read once per class or callable and then cached, so opening a scope for
every request does not repeat the work. The cache does not keep anything alive: a factory created
on the fly and then dropped leaves no entry behind.

Hints are read when a dependency is first needed, not when the module is defined. A forward
reference only has to be resolvable by then.
