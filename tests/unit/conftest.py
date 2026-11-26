from collections.abc import Callable

import pytest
from tests.samples import SampleDbPool


@pytest.fixture
def closed() -> list[object]:
    return []


@pytest.fixture(params=["sync", "async"])
def close_pool(
    request: pytest.FixtureRequest, closed: list[object]
) -> Callable[[SampleDbPool], object]:
    def close(pool: SampleDbPool) -> None:
        closed.append(pool)

    async def aclose(pool: SampleDbPool) -> None:
        closed.append(pool)

    return close if request.param == "sync" else aclose
