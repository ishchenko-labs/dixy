"""Four ways to build and clean up a dependency: factory, setup, teardown, lifespan."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field

from dixy import Container, Module, scoped, singleton


@dataclass
class Settings:
    dsn: str = "postgres://localhost/app"


@dataclass
class Database:
    dsn: str
    connected: bool = False

    async def connect(self) -> None:
        self.connected = True
        print(f"database connected to {self.dsn}")

    async def disconnect(self) -> None:
        self.connected = False
        print("database disconnected")


@dataclass
class EventBus:
    handlers: list[str] = field(default_factory=list)


@dataclass
class Transaction:
    database: Database
    state: str = "open"


async def create_database(settings: Settings) -> Database:
    """Build the instance: a factory's parameters are resolved like a constructor's."""
    database = Database(settings.dsn)
    await database.connect()
    return database


def register_handlers(bus: EventBus, database: Database) -> None:
    """Set up a new instance: it comes first, then whatever else is asked for."""
    bus.handlers.append(f"audit log in {database.dsn}")


@asynccontextmanager
async def transaction(database: Database) -> AsyncIterator[Transaction]:
    """Pair creation and cleanup in one place, as a lifespan."""
    tx = Transaction(database)
    print("transaction opened")
    try:
        yield tx
    finally:
        tx.state = "committed"
        print("transaction committed")


class AppModule(Module):
    settings = singleton(Settings)
    database = singleton(
        Database, factory=create_database, teardown=Database.disconnect
    )
    bus = singleton(EventBus, setup=register_handlers)
    tx = scoped(Transaction, lifespan=transaction)


class AppContainer(Container):
    modules = (AppModule,)


async def main() -> None:
    async with AppContainer() as container:
        container.validate()

        bus = await container.resolve(EventBus)
        print(f"bus handlers: {bus.handlers}")

        async with container.scope() as scope:
            tx = await scope.resolve(Transaction)
            print(f"transaction is {tx.state}")
        print(f"transaction is {tx.state}")


if __name__ == "__main__":
    asyncio.run(main())
