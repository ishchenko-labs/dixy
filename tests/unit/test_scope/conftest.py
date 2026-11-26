from collections.abc import Callable
from typing import Any

import pytest
from tests.samples import SampleDbPool

from dixy.types import Registration, Strategy


@pytest.fixture
def db_registration_factory() -> Callable[..., Registration]:
    def make(
        *,
        strategy: Strategy = Strategy.SINGLETON,
        factory: Callable[..., Any] | None = None,
        setup: Callable[..., Any] | None = None,
        teardown: Callable[..., Any] | None = None,
    ) -> Registration:
        return Registration(
            interface=SampleDbPool,
            implementation=SampleDbPool,
            strategy=strategy,
            kwargs={} if factory else {"dsn": "test://"},
            factory=factory,
            setup=setup,
            teardown=teardown,
        )

    return make
