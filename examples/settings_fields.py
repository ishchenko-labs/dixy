"""Pass single settings fields to constructors instead of the whole settings object."""

import asyncio
from dataclasses import dataclass, field

from dixy import Container, Module, and_, instance, or_, select, singleton


@dataclass
class RedisSettings:
    url: str


@dataclass
class Settings:
    bucket: str
    redis: RedisSettings
    region: str = ""
    api_key: str = ""
    queues: dict[str, str] = field(default_factory=dict)

    def auth_header(self) -> str:
        return f"Bearer {self.api_key}"


class Storage:
    def __init__(self, bucket: str, region: str) -> None:
        self.bucket = bucket
        self.region = region


class Cache:
    def __init__(self, url: str) -> None:
        self.url = url


class Mailer:
    def __init__(self, queue: str, auth_header: str) -> None:
        self.queue = queue
        self.auth_header = auth_header


class AppModule(Module):
    settings = instance(Settings)
    storage = singleton(
        Storage,
        bucket=select(Settings).bucket,
        region=or_(select(Settings).region, "eu-central-1"),
    )
    cache = singleton(Cache, url=select(Settings).redis.url)
    mailer = singleton(
        Mailer,
        queue=select(Settings).queues["mail"],
        auth_header=and_(select(Settings).api_key, select(Settings).auth_header()),
    )


class AppContainer(Container):
    modules = (AppModule,)


async def main() -> None:
    settings = Settings(
        bucket="uploads",
        redis=RedisSettings(url="redis://localhost"),
        api_key="secret",
        queues={"mail": "mail-queue"},
    )

    async with AppContainer() as container:
        container.bind(Settings, settings)
        container.validate()

        storage = await container.resolve(Storage)
        print(f"storage: {storage.bucket} in {storage.region}")

        cache = await container.resolve(Cache)
        print(f"cache: {cache.url}")

        mailer = await container.resolve(Mailer)
        print(f"mailer: {mailer.queue}, auth header {mailer.auth_header}")


if __name__ == "__main__":
    asyncio.run(main())
