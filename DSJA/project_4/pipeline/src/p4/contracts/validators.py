from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterable

import duckdb
import jsonschema
import yaml

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


def _manifest_hash(manifest: dict[str, Any], filename: str) -> str | None:
    for item in manifest.get("files", []):
        if isinstance(item, dict) and item.get("path") == filename:
            return item.get("sha256")
    return None


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


def _column_specs(table: dict[str, Any]) -> Iterable[tuple[str, dict[str, Any]]]:
    columns = table.get("columns", {})
    if isinstance(columns, dict):
        yield from ((name, spec or {}) for name, spec in columns.items())
    else:
        for column in columns:
            if isinstance(column, dict) and column.get("name"):
                yield str(column["name"]), column


def validate_metric_metadata(bundle: str | Path, contract_version: str) -> dict[str, Any]:
    path = Path(bundle) / "metrics.yaml"
    registry = yaml.safe_load(path.read_text(encoding="utf-8"))
    if registry.get("contractVersion") != contract_version:
        raise ValueError("metrics.yaml contractVersion mismatch")
    required = {
        "grain",
        "numerator",
        "denominator",
        "eligiblePopulation",
        "unknownHandling",
        "dedupApplied",
        "unit",
        "interpretation",
        "prohibitedInterpretation",
    }
    metrics = registry.get("metrics", {})
    missing = {
        metric: sorted(required - set(spec))
        for metric, spec in metrics.items()
        if isinstance(spec, dict) and required - set(spec)
    }
    if not metrics or missing:
        raise ValueError(f"metric metadata is incomplete: {missing}")
    return {"metricCount": len(metrics), "requiredMetadata": sorted(required)}


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
    contract_sha256 = sha256_file(bundle.root / "p4_contract.yaml")
    manifest_contract_hash = manifest.get("sourceContractSha256") or _manifest_hash(manifest, "p4_contract.yaml")
    if manifest_contract_hash != contract_sha256:
        raise ValueError("contract hash does not match CONTRACT_MANIFEST.json")
    if "CONTRACT_MANIFEST.json" not in checksums["checked"]:
        raise ValueError("CHECKSUMS.sha256 must include CONTRACT_MANIFEST.json")

    ddl_path = bundle.root / "warehouse_duckdb.sql"
    ddl = ddl_path.read_text(encoding="utf-8")
    assert_duckdb_executable_ddl(ddl)
    manifest_ddl_hash = manifest.get("ddlSha256") or _manifest_hash(manifest, "warehouse_duckdb.sql")
    if manifest_ddl_hash and manifest_ddl_hash != sha256_file(ddl_path):
        raise ValueError("DDL hash does not match CONTRACT_MANIFEST.json")
    conformance = compare_contract_to_ddl(contract, ddl)
    required_tables = set(contract.get("requiredTables", [])) or set(contract.get("tables", {}))
    ddl_lower = ddl.casefold()
    missing_required_tables = sorted(name for name in required_tables if str(name).casefold() not in ddl_lower)
    configured_required_fields = list(_required_fields(contract))
    if not configured_required_fields:
        configured_required_fields = [
            f"{table_name}.{column_name}"
            for table_name, table in contract.get("tables", {}).items()
            for column_name, _ in _column_specs(table)
        ]
    missing_required_fields = sorted(
        field for field in configured_required_fields if field.split(".")[-1].casefold() not in ddl_lower
    )

    reserved = contract.get("reservedFields") or contract.get("rules", {}).get("reservedFields", {})
    if isinstance(reserved, list):
        reserved = {name: {} for name in reserved}
    if "highDemandScore" not in reserved:
        raise ValueError("reservedFields must declare highDemandScore")

    expected_schemas = set(contract.get("schemas", []))
    table_count = len(contract.get("tables", {}))
    view_names = re.findall(r"CREATE\s+OR\s+REPLACE\s+VIEW\s+([\w.]+)", ddl, re.IGNORECASE)
    statement_count = len([statement for statement in ddl.split(";") if statement.strip()])
    if expected_schemas != {"raw", "core", "ncs", "mart", "qa"} or table_count != 26 or len(view_names) != 6:
        raise ValueError(
            f"canonical object counts mismatch: schemas={sorted(expected_schemas)}, tables={table_count}, views={len(view_names)}"
        )
    manifest_counts = (manifest.get("schemaCount"), manifest.get("tableCount"), manifest.get("viewCount"))
    if manifest_counts != (len(expected_schemas), table_count, len(view_names)):
        raise ValueError(f"manifest object counts mismatch: {manifest_counts}")
    if statement_count < 36:
        raise ValueError(f"canonical DDL has too few statements: {statement_count}")

    key_contract = contract.get("rules", {}).get("keyContract", {})
    expected_keys = {
        "algorithm": "SHA-256",
        "encoding": "UTF-8",
        "separator": "|",
        "truncationHexChars": 20,
    }
    if any(key_contract.get(key) != value for key, value in expected_keys.items()):
        raise ValueError(f"canonical key contract mismatch: {key_contract}")

    lineage_missing = [
        f"{table_name}.{column_name}"
        for table_name, table in contract.get("tables", {}).items()
        for column_name, spec in _column_specs(table)
        if not all(spec.get(field) for field in ("source", "derivation", "qualityRule"))
    ]
    if lineage_missing:
        raise ValueError(f"field lineage metadata missing: {lineage_missing[:10]}")
    metrics = validate_metric_metadata(bundle.root, bundle.contract_version)

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
        "contractSha256": contract_sha256,
        "manifestSha256": sha256_file(bundle.root / "CONTRACT_MANIFEST.json"),
        "ddlSha256": sha256_file(ddl_path),
        "schemaFilename": CANONICAL_SCHEMA_FILENAME,
        "duckdbRuntimeVersion": duckdb.__version__,
        "checksums": checksums,
        "schemaCount": len(expected_schemas),
        "tableCount": table_count,
        "viewCount": len(view_names),
        "ddlStatementCount": statement_count,
        "crossSchemaForeignKeyCount": len(find_cross_schema_foreign_keys(ddl)),
        "keyContract": key_contract,
        "fieldLineageCount": sum(
            1 for table in contract.get("tables", {}).values() for _ in _column_specs(table)
        ),
        "metricMetadata": metrics,
        "requiredTables": sorted(required_tables),
        "requiredFields": sorted(configured_required_fields),
        "reservedFields": sorted(reserved),
        "passed": True,
    }
