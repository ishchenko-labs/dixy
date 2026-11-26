"""Swap real dependencies for fakes in a test, without touching the app's container."""

import asyncio

from dixy import Container, Module, scoped, singleton


class PaymentGateway:
    async def charge(self, cents: int) -> str:
        raise RuntimeError(f"cannot charge {cents} cents: no gateway in tests")


class FakePaymentGateway(PaymentGateway):
    async def charge(self, cents: int) -> str:
        return f"fake charge of {cents} cents"


class Clock:
    def today(self) -> str:
        return "the real date"


class FrozenClock(Clock):
    def __init__(self, day: str) -> None:
        self.day = day

    def today(self) -> str:
        return self.day


class Checkout:
    def __init__(self, gateway: PaymentGateway, clock: Clock) -> None:
        self.gateway = gateway
        self.clock = clock

    async def pay(self, cents: int) -> str:
        return f"{await self.gateway.charge(cents)} on {self.clock.today()}"


class AppModule(Module):
    gateway = singleton(PaymentGateway)
    clock = singleton(Clock)
    checkout = scoped(Checkout)


class AppContainer(Container):
    modules = (AppModule,)


async def main() -> None:
    app = AppContainer()

    test = app.clone()
    test.override(interface=PaymentGateway, implementation=FakePaymentGateway)
    test.override(interface=Clock, implementation=FrozenClock("2030-01-01"))
    test.validate()

    async with test.scope() as scope:
        checkout = await scope.resolve(Checkout)
        print(await checkout.pay(500))

    async with app.scope() as scope:
        checkout = await scope.resolve(Checkout)
        print(f"the app still uses {type(checkout.gateway).__name__}")


if __name__ == "__main__":
    asyncio.run(main())
