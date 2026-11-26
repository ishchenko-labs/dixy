from dataclasses import dataclass


class SampleDbPool:
    def __init__(self, dsn: str = "test://") -> None:
        self.dsn = dsn


class SampleRepo:
    def __init__(self, db: SampleDbPool) -> None:
        self.db = db


class SampleFakeRepo(SampleRepo): ...


@dataclass
class SampleService:
    repo: SampleRepo
    timeout: int = 30


class SampleSession:
    def __init__(self) -> None:
        self.open = True


class SampleStorage:
    def __init__(self, dsn: str) -> None:
        self.dsn = dsn


class SampleSettings:
    def __init__(
        self,
        db_dsn: str = "postgres://localhost",
        hosts: list[str] | None = None,
    ) -> None:
        self.db_dsn = db_dsn
        self.hosts = hosts or ["host1", "host2"]
