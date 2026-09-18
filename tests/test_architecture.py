import ast
from pathlib import Path

import pytest

from app.files.schemas import MergeFilesRequest


def test_domain_has_no_framework_or_infrastructure_imports():
    forbidden = ("fastapi", "tortoise", "httpx", "pypdf", "pydantic")
    files = list(Path("app").glob("*/domain/*.py")) + [Path("app/core/domain.py")]
    assert files
    for path in files:
        for node in ast.walk(ast.parse(path.read_text())):
            names = (
                [n.name for n in node.names]
                if isinstance(node, ast.Import)
                else [node.module or ""] if isinstance(node, ast.ImportFrom) else []
            )
            for name in names:
                assert not name.startswith(forbidden), (path, name)
                assert ".persistence" not in name and ".api" not in name and ".models" not in name


@pytest.mark.parametrize("payload", [{"file_ids": [1, 2, 3]}, {"file_id_1": 1, "file_id_2": 2}])
def test_merge_contract(payload):
    assert len(MergeFilesRequest(**payload).source_ids()) >= 2


@pytest.mark.parametrize(
    "payload",
    [
        {"file_ids": [1, 1]},
        {"file_ids": [1]},
        {"file_ids": [0, 2]},
        {"file_ids": list(range(1, 12))},
        {"file_ids": [1, 2], "file_id_1": 1},
        {},
    ],
)
def test_merge_rejects_invalid_sources(payload):
    with pytest.raises(ValueError):
        MergeFilesRequest(**payload)
