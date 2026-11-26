from collections.abc import Callable

import pytest

from dixy.exceptions import (
    CaptiveDependencyError,
    CyclicDependencyError,
    InstanceNotProvidedError,
    MissingDependencyError,
    OutOfScopeError,
)


class Dummy:
    pass


class Other:
    pass


def make_dummy() -> Dummy:
    return Dummy()


@pytest.mark.parametrize(
    ("factory", "expected_substrings"),
    [
        (
            lambda: MissingDependencyError(Dummy, required_by=Other),
            ["Dummy", "Other"],
        ),
        (
            lambda: MissingDependencyError(Dummy, required_by=make_dummy),
            ["Dummy", "required by make_dummy"],
        ),
        (lambda: CyclicDependencyError([Dummy, Other, Dummy]), ["Dummy", "Other"]),
        (
            lambda: CaptiveDependencyError(
                owner_type=Dummy, owner_strategy="singleton", scoped_type=Other
            ),
            ["Dummy", "Other"],
        ),
    ],
)
def test_message_contains_class_names(
    factory: Callable[[], Exception],
    expected_substrings: list[str],
) -> None:
    err = factory()

    message = str(err)

    for substring in expected_substrings:
        assert substring in message


class TestResolutionHints:
    def test_out_of_scope_points_to_container_scope(self) -> None:
        err = OutOfScopeError(Dummy)

        actual = str(err)

        assert actual == (
            "Cannot resolve scoped dependency Dummy without a scope. "
            "Use container.scope()."
        )

    def test_instance_not_provided_points_to_bind(self) -> None:
        err = InstanceNotProvidedError(Dummy)

        actual = str(err)

        assert actual == (
            "Instance for Dummy was declared but never provided via container.bind()"
        )
