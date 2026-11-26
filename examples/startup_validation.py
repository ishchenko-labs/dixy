"""Wiring mistakes that validate() reports at startup, not on the first request."""

import logging

from dixy import Container, Module, instance, scoped, singleton
from dixy.exceptions import DixyError


class Settings: ...


class Database: ...


class Session:
    def __init__(self, database: Database) -> None:
        self.database = database


class Cache:
    def __init__(self, session: Session) -> None:
        self.session = session


class Orders:
    def __init__(self, billing: "Billing") -> None:
        self.billing = billing


class Billing:
    def __init__(self, orders: Orders) -> None:
        self.orders = orders


class MissingModule(Module):
    session = scoped(Session)


class CyclicModule(Module):
    orders = scoped(Orders)
    billing = scoped(Billing)


class CaptiveModule(Module):
    database = singleton(Database)
    session = scoped(Session)
    cache = singleton(Cache)


class UnboundModule(Module):
    settings = instance(Settings)


def report(*modules: type[Module]) -> None:
    class Checked(Container): ...

    Checked.modules = modules
    try:
        Checked().validate()
    except DixyError as error:
        print(f"{type(error).__name__}: {error}")


def main() -> None:
    # dixy also logs a failed validation as a warning; this example prints it itself.
    logging.getLogger("dixy").setLevel(logging.ERROR)

    report(MissingModule)
    report(CyclicModule)
    report(CaptiveModule)
    report(UnboundModule)


if __name__ == "__main__":
    main()
