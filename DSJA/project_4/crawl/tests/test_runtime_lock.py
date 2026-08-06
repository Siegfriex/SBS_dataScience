from __future__ import annotations

import json
import sys
import tomllib
from importlib.metadata import version
from pathlib import Path


CRAWL_ROOT = Path(__file__).resolve().parents[1]


def test_runtime_lock_matches_interpreter_and_installed_packages() -> None:
    lock = json.loads((CRAWL_ROOT / "RUNTIME_DEPENDENCY_LOCK.json").read_text(encoding="utf-8"))
    assert lock["python"] == ".".join(map(str, sys.version_info[:3]))
    for package, expected in lock["packages"].items():
        assert version(package) == expected


def test_declared_runtime_dependencies_are_exactly_pinned() -> None:
    project = tomllib.loads((CRAWL_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    dependencies = project["project"]["dependencies"]
    assert dependencies
    assert all("==" in dependency for dependency in dependencies)
    declared = {dependency.split("==", 1)[0].casefold() for dependency in dependencies}
    required = {"beautifulsoup4", "duckdb", "httpx", "ipykernel", "jsonschema", "nbclient", "nbformat", "pandas", "pyarrow", "pyyaml"}
    assert declared == required
