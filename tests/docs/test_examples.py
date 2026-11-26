import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest
from fastapi.testclient import TestClient

EXAMPLES = Path(__file__).parents[2] / "examples"

EXPECTED_OUTPUT = {
    "quickstart.py": ["Hello, Ada!"],
    "lifetimes.py": [
        "scoped, same scope: True",
        "scoped, other scope: False",
        "singleton, across scopes: True",
        "alias, same instance as its source: True",
        "transient, same scope: False",
        "closed Session",
        "closed Session",
        "scopes closed",
        "closed ConnectionPool",
        "container closed",
    ],
    "lifecycle.py": [
        "database connected to postgres://localhost/app",
        "bus handlers: ['audit log in postgres://localhost/app']",
        "transaction opened",
        "transaction is open",
        "transaction committed",
        "transaction is committed",
        "database disconnected",
    ],
    "settings_fields.py": [
        "storage: uploads in eu-central-1",
        "cache: redis://localhost",
        "mailer: mail-queue, auth header Bearer secret",
    ],
    "inject_handlers.py": [
        "Hello, Ada! It is 12:00.",
        "Hello, Grace! It is 12:00.",
        "Hi, Linus.",
    ],
    "testing_overrides.py": [
        "fake charge of 500 cents on 2030-01-01",
        "the app still uses PaymentGateway",
    ],
    "startup_validation.py": [
        (
            "MissingDependencyError: "
            "No registration found for Database (required by Session)"
        ),
        "CyclicDependencyError: Cyclic dependency detected: Orders → Billing → Orders",
        (
            "CaptiveDependencyError: "
            "Captive dependency: singleton Cache depends on scoped Session"
        ),
        (
            "InstanceNotProvidedError: "
            "Instance for Settings was declared but never provided via container.bind()"
        ),
    ],
    "modules.py": ["emailed a receipt for a notebook"],
}

SERVED_EXAMPLES = {"fastapi_app.py"}


def load(example: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        Path(example).stem, EXAMPLES / example
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_every_example_is_covered() -> None:
    examples = {path.name for path in EXAMPLES.glob("*.py")}

    assert examples == EXPECTED_OUTPUT.keys() | SERVED_EXAMPLES


@pytest.mark.parametrize("example", EXPECTED_OUTPUT)
def test_example_prints_its_expected_output(example: str) -> None:
    result = subprocess.run(  # noqa: S603 - runs this repository's own example
        [sys.executable, str(EXAMPLES / example)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
        timeout=30,
    )

    assert result.stdout.splitlines() == EXPECTED_OUTPUT[example]


class TestFastApiExample:
    @pytest.fixture
    def client(self) -> TestClient:
        return TestClient(load("fastapi_app.py").app)

    def test_greets_a_user_through_the_request_scope(self, client: TestClient) -> None:
        with client:
            response = client.get("/users/1")

        assert response.status_code == 200
        assert response.json() == {
            "greeting": "Hello, Ada!",
            "lookups_in_this_request": 1,
        }

    def test_every_request_gets_a_fresh_scope(self, client: TestClient) -> None:
        with client:
            client.get("/users/1")
            response = client.get("/users/2")

        assert response.json()["lookups_in_this_request"] == 1

    def test_unknown_user_is_not_found(self, client: TestClient) -> None:
        with client:
            response = client.get("/users/3")

        assert response.status_code == 404
