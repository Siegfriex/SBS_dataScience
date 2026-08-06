from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterable

import duckdb
import jsonschema

from p4.common.hashing import sha256_file
from p4.contracts.loader import CANONICAL_SCHEMA_FILENAME, ContractBundle, load_contract_yaml


_CHECKSUM_LINE = re.compile(r"^([0-9a-f]{64})\s+\*?(.+)$")
_CROSS_SCHEMA_FK = re.compile(
    r"\bREFERENCES\s+([A-Za-z_][A-Za-z0-9_]*)\s*\.\s*([A-Za-z_][A-Za-z0-9_]*)",
    re.IGNORECASE,
)


def _version_tuple(value: str) -> tuple[int, ...]:
    match = re.search(r"\d+(?:\.\d+)+", value)
    return tuple(int(part) for part in match.group().split(".")) if match else ()


def verify_checksums(bundle: str | Path) -> dict[str, Any]:
    root = Path(bundle).resolve()
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
        if root not in target.parents or not target.is_file():
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
    schema = json.loads((root / CANONICAL_SCHEMA_FILENAME).read_text(encoding="utf-8"))
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


def _table_specs(contract: dict[str, Any]) -> list[dict[str, Any]]:
    tables = contract.get("tables", [])
    if isinstance(tables, dict):
        return [{"name": name, **(spec or {})} for name, spec in tables.items()]
    return [item for item in tables if isinstance(item, dict)]


def compare_contract_to_ddl(contract: dict[str, Any], ddl: str) -> dict[str, list[str]]:
    ddl_lower = ddl.casefold()
    missing_tables: list[str] = []
    missing_columns: list[str] = []
    for table in _table_specs(contract):
        name = table.get("name")
        if name and name.casefold() not in ddl_lower:
            missing_tables.append(name)
        columns = table.get("columns", [])
        if isinstance(columns, dict):
            columns = [{"name": key, **(value or {})} for key, value in columns.items()]
        for column in columns:
            column_name = column.get("name") if isinstance(column, dict) else str(column)
            if name and column_name and column_name.casefold() not in ddl_lower:
                missing_columns.append(f"{name}.{column_name}")
    return {"missingTables": missing_tables, "missingColumns": missing_columns}


def _required_fields(contract: dict[str, Any]) -> Iterable[str]:
    required = contract.get("requiredFields", [])
    if isinstance(required, dict):
        for table, fields in required.items():
            for field in fields:
                yield f"{table}.{field}"
    else:
        yield from (str(value) for value in required)


def audit_contract_bundle(bundle_path: str | Path) -> dict[str, Any]:
    bundle = ContractBundle.from_path(bundle_path)
    checksums = verify_checksums(bundle.root)
    if not checksums["passed"]:
        raise ValueError(f"contract checksum validation failed: {checksums}")
    contract = validate_contract_schema(bundle.root)
    manifest = validate_contract_manifest(bundle.root)
    contract_version = str(contract.get("contractVersion") or "")
    if contract_version != bundle.contract_version or str(manifest["contractVersion"]) != bundle.contract_version:
        raise ValueError("contractVersion mismatch between directory, contract, and manifest")
    if "CONTRACT_MANIFEST.json" not in checksums["checked"]:
        raise ValueError("CHECKSUMS.sha256 must include CONTRACT_MANIFEST.json")

    ddl_path = bundle.root / "warehouse_duckdb.sql"
    ddl = ddl_path.read_text(encoding="utf-8")
    assert_duckdb_executable_ddl(ddl)
    manifest_ddl_hash = manifest.get("ddlSha256")
    if manifest_ddl_hash and manifest_ddl_hash != sha256_file(ddl_path):
        raise ValueError("DDL hash does not match CONTRACT_MANIFEST.json")
    conformance = compare_contract_to_ddl(contract, ddl)
    required_tables = set(contract.get("requiredTables", []))
    ddl_lower = ddl.casefold()
    missing_required_tables = sorted(name for name in required_tables if str(name).casefold() not in ddl_lower)
    missing_required_fields = sorted(field for field in _required_fields(contract) if field.split(".")[-1].casefold() not in ddl_lower)

    reserved = contract.get("reservedFields", {})
    if isinstance(reserved, list):
        reserved = {name: {} for name in reserved}
    if "highDemandScore" not in reserved:
        raise ValueError("reservedFields must declare highDemandScore")

    required_duckdb = str(manifest.get("duckdbVersion") or contract.get("duckdbVersion") or "")
    if required_duckdb and _version_tuple(duckdb.__version__) < _version_tuple(required_duckdb):
        raise ValueError(f"DuckDB {duckdb.__version__} is older than contract requirement {required_duckdb}")
    if conformance["missingTables"] or conformance["missingColumns"] or missing_required_tables or missing_required_fields:
        raise ValueError(
            "contract/DDL conformance failed: "
            + json.dumps(
                {
                    **conformance,
                    "missingRequiredTables": missing_required_tables,
                    "missingRequiredFields": missing_required_fields,
                },
                ensure_ascii=False,
            )
        )
    return {
        "contractVersion": bundle.contract_version,
        "contractSha256": sha256_file(bundle.root / "p4_contract.yaml"),
        "manifestSha256": sha256_file(bundle.root / "CONTRACT_MANIFEST.json"),
        "ddlSha256": sha256_file(ddl_path),
        "schemaFilename": CANONICAL_SCHEMA_FILENAME,
        "duckdbRuntimeVersion": duckdb.__version__,
        "checksums": checksums,
        "requiredTables": sorted(required_tables),
        "requiredFields": sorted(_required_fields(contract)),
        "reservedFields": sorted(reserved),
        "passed": True,
    }

