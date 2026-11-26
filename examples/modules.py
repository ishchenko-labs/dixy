"""Split registrations across modules, and let one module extend another's service."""

import asyncio
from collections.abc import Callable

from dixy import Container, Module, hook, scoped, singleton


class EventBus:
    def __init__(self) -> None:
        self.handlers: dict[str, Callable[[str], str]] = {}

    def publish(self, event: str, payload: str) -> str:
        return self.handlers[event](payload)


class OrderService:
    def __init__(self, bus: EventBus) -> None:
        self.bus = bus

    def place(self, item: str) -> str:
        return self.bus.publish("order.placed", item)


def subscribe_emails(bus: EventBus) -> None:
    bus.handlers["order.placed"] = lambda item: f"emailed a receipt for {item}"


class InfraModule(Module):
    bus = singleton(EventBus)


class OrdersModule(Module):
    orders = scoped(OrderService)


class NotificationsModule(Module):
    """Adds its handlers to the shared bus without owning the bus registration."""

    emails = hook(EventBus, setup=subscribe_emails)


class AppContainer(Container):
    modules = (InfraModule, OrdersModule, NotificationsModule)


async def main() -> None:
    async with AppContainer() as container:
        container.validate()

        async with container.scope() as scope:
            orders = await scope.resolve(OrderService)
            print(orders.place("a notebook"))


if __name__ == "__main__":
    asyncio.run(main())
