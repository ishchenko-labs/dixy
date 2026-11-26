"""One container per FastAPI app, one scope per HTTP request.

Serve it with any ASGI server, for example: uvicorn fastapi_app:app
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import Depends, FastAPI, HTTPException, Request

from dixy import Container, Module, Scope, instance, scoped, singleton


@dataclass
class Settings:
    greeting: str


class UserRepository:
    def __init__(self) -> None:
        self.names = {1: "Ada", 2: "Grace"}

    def find(self, user_id: int) -> str | None:
        return self.names.get(user_id)


class AuditLog:
    """Singleton: outlives requests and records how each one ended."""

    def __init__(self) -> None:
        self.outcomes: list[str] = []


class UnitOfWork:
    """Scoped: one per request, shared by everything resolved in that request."""

    def __init__(self) -> None:
        self.lookups = 0


@asynccontextmanager
async def unit_of_work(audit: AuditLog) -> AsyncIterator[UnitOfWork]:
    """Commit when the request succeeds, roll back when it raises."""
    try:
        yield UnitOfWork()
    except BaseException:
        audit.outcomes.append("rolled back")
        raise
    else:
        audit.outcomes.append("committed")


class UserService:
    def __init__(
        self, settings: Settings, users: UserRepository, work: UnitOfWork
    ) -> None:
        self.settings = settings
        self.users = users
        self.work = work

    def greet(self, user_id: int) -> str | None:
        self.work.lookups += 1
        name = self.users.find(user_id)
        return f"{self.settings.greeting}, {name}!" if name else None


class AppModule(Module):
    settings = instance(Settings)
    users = singleton(UserRepository)
    audit = singleton(AuditLog)
    work = scoped(UnitOfWork, lifespan=unit_of_work)
    service = scoped(UserService)


class AppContainer(Container):
    modules = (AppModule,)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    async with AppContainer() as container:
        container.bind(Settings, Settings(greeting="Hello"))
        container.validate()
        app.state.container = container
        yield


async def request_scope(request: Request) -> AsyncIterator[Scope]:
    """Open the request's scope. FastAPI caches it, so one request gets one scope."""
    async with request.app.state.container.scope() as scope:
        yield scope


def resolved[T](interface: type[T]) -> Any:
    """Resolve interface from the request's scope, as a FastAPI dependency."""

    async def dependency(scope: Annotated[Scope, Depends(request_scope)]) -> T:
        return await scope.resolve(interface)

    return Depends(dependency)


app = FastAPI(lifespan=lifespan)


@app.get("/users/{user_id}")
async def greet_user(
    user_id: int,
    service: Annotated[UserService, resolved(UserService)],
    work: Annotated[UnitOfWork, resolved(UnitOfWork)],
) -> dict[str, str | int]:
    greeting = service.greet(user_id)
    if greeting is None:
        raise HTTPException(status_code=404, detail="No such user")
    return {"greeting": greeting, "lookups_in_this_request": work.lookups}
