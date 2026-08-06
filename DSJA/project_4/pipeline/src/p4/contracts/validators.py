from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import jsonschema

from p4.common.hashing import sha256_file
from p4.contracts.loader import load_contract_yaml


_CHECKSUM_LINE = re.compile(r"^([0-9a-f]{64})\s+\*?(.+)$")
_CROSS_SCHEMA_FK = re.compile(
    r"\bREFERENCES\s+([A-Za-z_][A-Za-z0-9_]*)\s*\.\s*([A-Za-z_][A-Za-z0-9_]*)",
    re.IGNORECASE,
)


def verify_checksums(bundle: str | Path) -> dict[str, Any]:
    root = Path(bundle)
    checked: list[str] = []
    mismatches: list[str] = []
    malformed: list[str] = []
    for line in (root / "CHECKSUMS.sha256").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        match = _CHECKSUM_LINE.match(line.strip())
        if not match:
            malformed.append(line)
            continue
        expected, relative = match.groups()
        target = (root / relative).resolve()
        if root.resolve() not in target.parents or not target.is_file():
            mismatches.append(relative)
            continue
        checked.append(relative)
        if sha256_file(target) != expected:
            mismatches.append(relative)
    return {
        "checked": checked,
        "mismatches": mismatches,
        "malformed": malformed,
        "passed": bool(checked) and not mismatches and not malformed,
    }


def validate_contract_schema(bundle: str | Path) -> dict[str, Any]:
    root = Path(bundle)
    contract = load_contract_yaml(root)
    schema = json.loads((root / "contract.schema.json").read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.validate(contract, schema)
    return contract


def validate_contract_manifest(bundle: str | Path) -> dict[str, Any]:
    root = Path(bundle)
    manifest = json.loads((root / "CONTRACT_MANIFEST.json").read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise TypeError("CONTRACT_MANIFEST.json must contain an object")
    if not manifest.get("contractVersion"):
        raise ValueError("CONTRACT_MANIFEST.json missing contractVersion")
    return manifest


def find_cross_schema_foreign_keys(ddl: str) -> list[str]:
    return [f"{schema}.{table}" for schema, table in _CROSS_SCHEMA_FK.findall(ddl)]


def assert_duckdb_executable_ddl(ddl: str) -> None:
    references = find_cross_schema_foreign_keys(ddl)
    if references:
        raise ValueError(
            "CONTRACT_NOT_EXECUTABLE: cross-schema FOREIGN KEY references found: "
            + ", ".join(references)
        )


def compare_contract_to_ddl(contract: dict[str, Any], ddl: str) -> dict[str, list[str]]:
    ddl_lower = ddl.casefold()
    missing_tables: list[str] = []
    missing_columns: list[str] = []
    for table in contract.get("tables", []):
        name = table.get("name")
        if name and name.casefold() not in ddl_lower:
            missing_tables.append(name)
        for column in table.get("columns", []):
            column_name = column.get("name")
            if name and column_name and column_name.casefold() not in ddl_lower:
                missing_columns.append(f"{name}.{column_name}")
    return {"missingTables": missing_tables, "missingColumns": missing_columns}

