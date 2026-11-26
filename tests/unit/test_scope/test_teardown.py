from collections.abc import Callable

from tests.samples import SampleDbPool

from dixy.scope import Scope
from dixy.types import Registration, Strategy


class TestScopeTeardown:
    async def test_teardown_calls_async_callback(
        self, db_registration_factory: Callable[..., Registration]
    ) -> None:
        closed: list[object] = []

        async def teardown(x: object) -> None:
            closed.append(x)

        registry: dict[type, Registration] = {
            SampleDbPool: db_registration_factory(
                strategy=Strategy.SCOPED, teardown=teardown
            ),
        }
        scope = Scope(registry=registry, singletons={})
        instance = await scope.resolve(SampleDbPool)

        await scope.teardown()

        assert closed == [instance]

    async def test_scope_does_not_teardown_singletons(
        self, db_registration_factory: Callable[..., Registration]
    ) -> None:
        closed: list[object] = []
        registry: dict[type, Registration] = {
            SampleDbPool: db_registration_factory(
                strategy=Strategy.SINGLETON,
                teardown=lambda x: closed.append(x),
            ),
        }
        scope = Scope(registry=registry, singletons={})
        await scope.resolve(SampleDbPool)

        await scope.teardown()

        assert closed == []

    async def test_teardown_in_reverse_order(self) -> None:
        order: list[str] = []

        class A:
            pass

        class B:
            pass

        registry: dict[type, Registration] = {
            A: Registration(
                interface=A,
                implementation=A,
                strategy=Strategy.SCOPED,
                teardown=lambda _: order.append("A"),
            ),
            B: Registration(
                interface=B,
                implementation=B,
                strategy=Strategy.SCOPED,
                teardown=lambda _: order.append("B"),
            ),
        }
        scope = Scope(registry=registry, singletons={})
        await scope.resolve(A)
        await scope.resolve(B)

        await scope.teardown()

        assert order == ["B", "A"]
