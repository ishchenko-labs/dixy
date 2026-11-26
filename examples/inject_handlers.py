"""Fill handler parameters with @inject, with a container that exists or comes later."""

import asyncio

from dixy import Container, Inject, Module, inject, scoped, singleton


class Clock:
    def now(self) -> str:
        return "12:00"


class Greeter:
    def __init__(self, clock: Clock) -> None:
        self.clock = clock

    def greet(self, name: str) -> str:
        return f"Hello, {name}! It is {self.clock.now()}."


class AppModule(Module):
    clock = singleton(Clock)
    greeter = scoped(Greeter)


class AppContainer(Container):
    modules = (AppModule,)


container = AppContainer()


@inject(container)
async def greet(name: str, greeter: Inject[Greeter]) -> str:
    return greeter.greet(name)


class Active:
    """Holds the container for handlers that are defined before it is created."""

    container: Container | None = None


@inject(lambda: Active.container)
async def greet_later(name: str, greeter: Inject[Greeter]) -> str:
    return greeter.greet(name)


class FixedGreeter(Greeter):
    def greet(self, name: str) -> str:
        return f"Hi, {name}."


async def main() -> None:
    print(await greet("Ada"))

    Active.container = AppContainer()
    print(await greet_later("Grace"))

    print(await greet("Linus", greeter=FixedGreeter(Clock())))


if __name__ == "__main__":
    asyncio.run(main())
