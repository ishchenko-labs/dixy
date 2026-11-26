# Dixy

[![PyPI](https://img.shields.io/pypi/v/dixy?label=pypi)](https://pypi.org/project/dixy/)
[![Python](https://img.shields.io/pypi/pyversions/dixy?label=python)](https://pypi.org/project/dixy/)
[![CI](https://github.com/ishchenko-labs/dixy/actions/workflows/ci.yaml/badge.svg)](https://github.com/ishchenko-labs/dixy/actions/workflows/ci.yaml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue)](https://github.com/ishchenko-labs/dixy/blob/main/LICENSE)

> Minimalist, type-driven dependency injection for async Python. Zero dependencies, fully typed.

## Highlights

- **Five lifetimes**: `singleton`, `scoped`, `transient`, `instance`, `alias`
- **Auto-resolve**: dependencies are inferred from `__init__` type hints
- **Async-first**: async factories, setup and teardown callbacks, and lifespans work out of the box
- **Validated upfront**: cyclic, missing, and captive dependencies are caught at startup, not on the
  first request
- **No magic**: modules are plain classes, and your own classes need no decorators or base classes
- **Typed**: `resolve(UserService)` returns a `UserService` to mypy and pyright, no casts needed

## Install

```bash
uv add dixy
# or
pip install dixy
```

Requires Python 3.12 or newer.

## Quick start

```python
import asyncio
from dataclasses import dataclass

from dixy import Container, Module, instance, scoped, singleton


@dataclass
class Settings:
    greeting: str


class UserRepository:
    async def name_of(self, user_id: int) -> str:
        raise NotImplementedError


class InMemoryUserRepository(UserRepository):
    async def name_of(self, user_id: int) -> str:
        return {1: "Ada"}[user_id]


class Greeter:
    # Dependencies come from the type hints: no decorators, no container in sight.
    def __init__(self, settings: Settings, users: UserRepository) -> None:
        self.settings = settings
        self.users = users

    async def greet(self, user_id: int) -> str:
        return f"{self.settings.greeting}, {await self.users.name_of(user_id)}!"


class AppModule(Module):
    settings = instance(Settings)
    users = singleton(UserRepository, InMemoryUserRepository)
    greeter = scoped(Greeter)


class AppContainer(Container):
    modules = (AppModule,)


async def main() -> None:
    async with AppContainer() as container:
        container.bind(Settings, Settings(greeting="Hello"))
        container.validate()

        async with container.scope() as scope:
            greeter = await scope.resolve(Greeter)
            print(await greeter.greet(1))  # Hello, Ada!


if __name__ == "__main__":
    asyncio.run(main())
```

## Injecting into handlers

`@inject` opens a scope per call and fills every `Inject[T]` parameter, which suits request
handlers, background jobs, and workflow activities:

```python
from dixy import Inject, inject

container = AppContainer()


@inject(container)
async def handle(user_id: int, greeter: Inject[Greeter]) -> str:
    return await greeter.greet(user_id)
```

## Testing

Clone the container and override what the test needs to fake. The original stays untouched:

```python
test = container.clone()
test.override(interface=UserRepository, implementation=FakeUserRepository)
test.validate()
```

## Documentation

The [documentation](https://github.com/ishchenko-labs/dixy/blob/main/docs/README.md) covers every
provider, the container and scope API, auto-resolve rules, selectors, FastAPI and Temporal
integration, and testing recipes. Every file in
[`examples/`](https://github.com/ishchenko-labs/dixy/tree/main/examples) is a small application that
runs on its own.

## Contributing

Bug reports and pull requests are welcome. See
[CONTRIBUTING.md](https://github.com/ishchenko-labs/dixy/blob/main/CONTRIBUTING.md) for the
development setup, and [SECURITY.md](https://github.com/ishchenko-labs/dixy/blob/main/SECURITY.md)
for reporting a vulnerability.

## License

[MIT](https://github.com/ishchenko-labs/dixy/blob/main/LICENSE)
