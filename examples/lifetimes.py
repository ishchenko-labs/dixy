"""How long each kind of provider lives, and when it is torn down."""

import asyncio

from dixy import Container, Module, alias, scoped, singleton, transient


class ConnectionPool:
    """One per application: expensive to create, safe to share."""


class ReadOnlySession:
    """What code that must not write is allowed to see."""


class Session(ReadOnlySession):
    """One per unit of work, such as a request."""

    def __init__(self, pool: ConnectionPool) -> None:
        self.pool = pool


class RequestId:
    """A fresh value every time someone asks for one."""


def close(resource: object) -> None:
    print(f"closed {type(resource).__name__}")


class AppModule(Module):
    pool = singleton(ConnectionPool, teardown=close)
    session = scoped(Session, teardown=close)
    read_only = alias(ReadOnlySession, Session)
    request_id = transient(RequestId)


class AppContainer(Container):
    modules = (AppModule,)


async def main() -> None:
    async with AppContainer() as container:
        container.validate()

        async with container.scope() as first, container.scope() as second:
            session = await first.resolve(Session)

            same_scope = await first.resolve(Session)
            other_scope = await second.resolve(Session)
            print(f"scoped, same scope: {session is same_scope}")
            print(f"scoped, other scope: {session is other_scope}")

            print(f"singleton, across scopes: {session.pool is other_scope.pool}")

            read_only = await first.resolve(ReadOnlySession)
            print(f"alias, same instance as its source: {read_only is session}")

            ids = await first.resolve(RequestId), await first.resolve(RequestId)
            print(f"transient, same scope: {ids[0] is ids[1]}")

        print("scopes closed")
    print("container closed")


if __name__ == "__main__":
    asyncio.run(main())
