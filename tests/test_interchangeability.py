"""The claim Activity 4 is graded on, turned into a test.

"Completely interchangeable services through dependency injection" is easy to
assert in a report and easy to get wrong in code: one adapter quietly grows a
method the other lacks, the container is edited, and the swap stops working.

These tests check the property mechanically instead:

1. Every adapter implements the full protocol, with matching signatures.
2. The domain never imports a concrete adapter, so swapping one cannot
   require touching business logic.
3. The composition roots are the only place that names concrete classes.

They need no database, no Redis and no MinIO: the point is structural.
"""

import ast
import inspect
from pathlib import Path

import pytest

from app.authentication.domain.ports import Sessions
from app.authentication.persistence.redis_sessions import RedisSessions
from app.authentication.persistence.repositories import PostgresSessions
from app.files.domain.ports import ContentStorage
from app.files.persistence.content import LocalContentStorage
from app.files.persistence.s3 import S3ContentStorage


def protocol_methods(protocol):
    return [name for name in vars(protocol) if not name.startswith("_")]


def parameter_names(function):
    # `self` is dropped so bound and unbound definitions compare equally.
    return [p for p in inspect.signature(function).parameters if p != "self"]


@pytest.mark.parametrize("adapter", [PostgresSessions, RedisSessions])
def test_every_session_adapter_implements_the_port(adapter):
    for name in protocol_methods(Sessions):
        assert hasattr(adapter, name), f"{adapter.__name__} is missing {name}()"

        expected = parameter_names(getattr(Sessions, name))
        actual = parameter_names(getattr(adapter, name))
        # The adapter may add defaulted extras, but every parameter the port
        # declares has to be accepted or the swap breaks at runtime.
        assert (
            actual[: len(expected)] == expected
        ), f"{adapter.__name__}.{name}{tuple(actual)} does not match the port {tuple(expected)}"


@pytest.mark.parametrize("adapter", [LocalContentStorage, S3ContentStorage])
def test_every_content_adapter_implements_the_port(adapter):
    for name in protocol_methods(ContentStorage):
        assert hasattr(adapter, name), f"{adapter.__name__} is missing {name}()"

        expected = parameter_names(getattr(ContentStorage, name))
        actual = parameter_names(getattr(adapter, name))
        assert (
            actual[: len(expected)] == expected
        ), f"{adapter.__name__}.{name}{tuple(actual)} does not match the port {tuple(expected)}"


def imported_modules(path):
    for node in ast.walk(ast.parse(Path(path).read_text())):
        if isinstance(node, ast.Import):
            yield from (alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            yield node.module or ""


def test_domain_never_imports_a_concrete_adapter():
    """If the domain imported Redis or boto3, the swap would be a lie."""
    forbidden = ("redis", "boto3", "botocore", "tortoise")
    files = list(Path("app").glob("*/domain/*.py")) + [Path("app/core/domain.py")]
    assert files
    for path in files:
        for module in imported_modules(path):
            assert not module.startswith(forbidden), f"{path} imports {module}"
            assert ".persistence" not in module, f"{path} imports {module}"


def test_only_the_composition_roots_name_concrete_storage():
    """The containers are the seam. Nothing else may name an adapter, or the
    choice of backend would be scattered across the codebase."""
    allowed = {
        Path("app/authentication/dependency_injection/container.py"),
        Path("app/files/dependency_injection/container.py"),
        Path("app/authentication/main.py"),
        Path("app/files/main.py"),
    }
    for path in Path("app").rglob("*.py"):
        if path in allowed or "persistence" in path.parts:
            continue
        for module in imported_modules(path):
            assert "redis_sessions" not in module, f"{path} names the Redis adapter"
            assert not module.endswith(".s3"), f"{path} names the S3 adapter"
