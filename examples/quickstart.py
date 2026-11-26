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
