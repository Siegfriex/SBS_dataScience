from __future__ import annotations

from pathlib import Path
from typing import Any

from p4.contracts.validators import assert_duckdb_executable_ddl
from p4.warehouse.connection import connect


DEVELOPMENT_DDL = """
CREATE SCHEMA IF NOT EXISTS raw;
CREATE SCHEMA IF NOT EXISTS core;
CREATE SCHEMA IF NOT EXISTS ncs;
CREATE SCHEMA IF NOT EXISTS mart;
CREATE SCHEMA IF NOT EXISTS qa;

CREATE TABLE IF NOT EXISTS raw.linkareer_posting (
    rawPostingId VARCHAR PRIMARY KEY,
    sourcePostingId VARCHAR,
    sourceUrl VARCHAR NOT NULL,
    fetchedAt TIMESTAMPTZ NOT NULL,
    rawSha256 VARCHAR NOT NULL,
    titleRaw VARCHAR,
    companyRaw VARCHAR,
    postedAtRaw VARCHAR,
    bodyRaw VARCHAR,
    postingKind VARCHAR
);

CREATE TABLE IF NOT EXISTS core.posting_normalized (
    postingId VARCHAR PRIMARY KEY,
    rawPostingId VARCHAR NOT NULL,
    canonicalPostingId VARCHAR NOT NULL,
    sourcePostingId VARCHAR,
    sourceUrl VARCHAR NOT NULL,
    titleText VARCHAR,
    companyName VARCHAR,
    companyKey VARCHAR,
    postedAt TIMESTAMPTZ,
    periodMonth DATE,
    bodyText VARCHAR,
    postingKind VARCHAR,
    activityTypeId VARCHAR,
    jobTypesRawJson JSON,
    dutiesRawJson JSON,
    activityTextHtml VARCHAR,
    activityTextAvailableFlag BOOLEAN NOT NULL,
    externalApplyUrl VARCHAR,
    externalAtsDomain VARCHAR,
    externalApplyFlag BOOLEAN NOT NULL,
    externalDetailOnlyFlag BOOLEAN NOT NULL,
    jobTypeConflictFlag BOOLEAN NOT NULL,
    reviewFlag BOOLEAN NOT NULL,
    resolvedJobTypes JSON,
    jobTypeSource VARCHAR,
    postingEligibleFlag BOOLEAN NOT NULL,
    rq1EligibleFlag BOOLEAN NOT NULL,
    rq2EligibleFlag BOOLEAN NOT NULL,
    ncsEligibleFlag BOOLEAN NOT NULL,
    rq2ExclusionReason VARCHAR,
    rq2ExclusionReasonsJson JSON,
    canonicalRecordFlag BOOLEAN NOT NULL,
    duplicateGroupId VARCHAR
);

CREATE TABLE IF NOT EXISTS core.posting_track (
    trackId VARCHAR PRIMARY KEY,
    postingId VARCHAR NOT NULL,
    trackType VARCHAR NOT NULL,
    trackOrdinal INTEGER NOT NULL,
    mixedResolvedFlag BOOLEAN NOT NULL,
    jobCodeLevel VARCHAR,
    jobCode VARCHAR
);

CREATE TABLE IF NOT EXISTS core.posting_section (
    sectionId VARCHAR PRIMARY KEY,
    trackId VARCHAR NOT NULL,
    sectionType VARCHAR NOT NULL,
    sectionOrdinal INTEGER NOT NULL,
    sectionText VARCHAR,
    boundaryResolvedFlag BOOLEAN NOT NULL
);

CREATE TABLE IF NOT EXISTS core.requirement_fact (
    requirementId VARCHAR PRIMARY KEY,
    sectionId VARCHAR NOT NULL,
    requirementType VARCHAR NOT NULL,
    requirementText VARCHAR NOT NULL,
    mandatoryFlag BOOLEAN NOT NULL,
    minExperienceMonths INTEGER,
    priorExperienceFlag BOOLEAN NOT NULL,
    portfolioFlag BOOLEAN NOT NULL
);

CREATE TABLE IF NOT EXISTS core.career_label (
    trackId VARCHAR PRIMARY KEY,
    careerClass VARCHAR NOT NULL,
    internAccessClass VARCHAR,
    restrictedInternFlag BOOLEAN,
    experiencedInternFlag BOOLEAN,
    boundaryResolvedFlag BOOLEAN NOT NULL
);

CREATE TABLE IF NOT EXISTS ncs.ncs_unit (
    ncsUnitCode VARCHAR PRIMARY KEY,
    ncsUnitName VARCHAR NOT NULL,
    ncsLevel TINYINT NOT NULL,
    ncsBand VARCHAR NOT NULL,
    performanceCriteriaText VARCHAR,
    knowledgeText VARCHAR,
    skillText VARCHAR,
    attitudeText VARCHAR,
    sourceUrl VARCHAR,
    rawSha256 VARCHAR
);

CREATE TABLE IF NOT EXISTS ncs.posting_ncs_match (
    matchId VARCHAR PRIMARY KEY,
    sectionId VARCHAR NOT NULL,
    ncsUnitCode VARCHAR NOT NULL,
    evidenceText VARCHAR NOT NULL,
    mappingBasis VARCHAR NOT NULL,
    matchScore DOUBLE NOT NULL,
    matchRank INTEGER NOT NULL,
    mappingVersion VARCHAR NOT NULL,
    selectedFlag BOOLEAN NOT NULL
);

CREATE TABLE IF NOT EXISTS mart.posting_analysis (
    trackId VARCHAR PRIMARY KEY,
    contractVersion VARCHAR NOT NULL,
    crawlReleaseId VARCHAR NOT NULL,
    dataVersion VARCHAR NOT NULL,
    parseVersion VARCHAR NOT NULL,
    labelVersion VARCHAR NOT NULL,
    ncsMapVersion VARCHAR NOT NULL,
    dedupVersion VARCHAR NOT NULL,
    postingId VARCHAR NOT NULL,
    canonicalPostingId VARCHAR NOT NULL,
    periodMonth DATE NOT NULL,
    cohortType VARCHAR NOT NULL,
    jobCodeLevel VARCHAR NOT NULL,
    jobCode VARCHAR NOT NULL,
    postingEligibleFlag BOOLEAN NOT NULL,
    rq1EligibleFlag BOOLEAN NOT NULL,
    rq2EligibleFlag BOOLEAN NOT NULL,
    ncsEligibleFlag BOOLEAN NOT NULL,
    canonicalRecordFlag BOOLEAN NOT NULL,
    activityTextAvailableFlag BOOLEAN NOT NULL,
    externalApplyFlag BOOLEAN NOT NULL,
    externalDetailOnlyFlag BOOLEAN NOT NULL,
    jobTypeConflictFlag BOOLEAN NOT NULL,
    rq2ExclusionReason VARCHAR,
    rq2ExclusionReasonsJson JSON,
    trackType VARCHAR NOT NULL,
    careerClass VARCHAR,
    internAccessClass VARCHAR,
    restrictedInternFlag BOOLEAN,
    experiencedInternFlag BOOLEAN,
    ncsLevel TINYINT,
    ncsBand VARCHAR,
    ncsMatchScore DOUBLE,
    highDemandScore DOUBLE
);

CREATE TABLE IF NOT EXISTS mart.time_series (
    metricId VARCHAR PRIMARY KEY,
    periodMonth DATE NOT NULL,
    cohortType VARCHAR NOT NULL,
    jobCodeLevel VARCHAR NOT NULL,
    jobCode VARCHAR NOT NULL,
    dedupApplied BOOLEAN NOT NULL,
    totalValidPostingCount BIGINT NOT NULL,
    entryPostingCount BIGINT NOT NULL,
    internPostingCount BIGINT NOT NULL,
    entryPostingRate DOUBLE,
    internPostingRate DOUBLE,
    entryOnlyRate DOUBLE,
    internOnlyRate DOUBLE,
    mixedRate DOUBLE,
    experiencedOnlyRate DOUBLE,
    internRelativeIndex DOUBLE,
    openEntryShare DOUBLE,
    restrictedEntryShare DOUBLE,
    restrictedInternShare DOUBLE,
    experiencedInternShare DOUBLE,
    advancedDutyShare DOUBLE,
    ncsMappingCoverage DOUBLE,
    lowConfidenceNcsShare DOUBLE
    ,rq1EligibilityRate DOUBLE
    ,rq2EligibilityRate DOUBLE
    ,ncsEligibilityRate DOUBLE
    ,externalApplyShare DOUBLE
    ,externalDetailOnlyShare DOUBLE
    ,activityTextAvailabilityRate DOUBLE
    ,jobTypeConflictRate DOUBLE
);

CREATE TABLE IF NOT EXISTS qa.check_result (
    checkId VARCHAR PRIMARY KEY,
    checkedAt TIMESTAMPTZ NOT NULL,
    checkName VARCHAR NOT NULL,
    status VARCHAR NOT NULL,
    observedValue DOUBLE,
    thresholdText VARCHAR,
    detailsJson JSON
);

ALTER TABLE core.posting_normalized ADD COLUMN IF NOT EXISTS activityTypeId VARCHAR;
ALTER TABLE core.posting_normalized ADD COLUMN IF NOT EXISTS jobTypesRawJson JSON;
ALTER TABLE core.posting_normalized ADD COLUMN IF NOT EXISTS dutiesRawJson JSON;
ALTER TABLE core.posting_normalized ADD COLUMN IF NOT EXISTS activityTextHtml VARCHAR;
ALTER TABLE core.posting_normalized ADD COLUMN IF NOT EXISTS activityTextAvailableFlag BOOLEAN DEFAULT FALSE;
ALTER TABLE core.posting_normalized ADD COLUMN IF NOT EXISTS externalApplyUrl VARCHAR;
ALTER TABLE core.posting_normalized ADD COLUMN IF NOT EXISTS externalAtsDomain VARCHAR;
ALTER TABLE core.posting_normalized ADD COLUMN IF NOT EXISTS externalApplyFlag BOOLEAN DEFAULT FALSE;
ALTER TABLE core.posting_normalized ADD COLUMN IF NOT EXISTS externalDetailOnlyFlag BOOLEAN DEFAULT FALSE;
ALTER TABLE core.posting_normalized ADD COLUMN IF NOT EXISTS jobTypeConflictFlag BOOLEAN DEFAULT FALSE;
ALTER TABLE core.posting_normalized ADD COLUMN IF NOT EXISTS reviewFlag BOOLEAN DEFAULT FALSE;
ALTER TABLE core.posting_normalized ADD COLUMN IF NOT EXISTS resolvedJobTypes JSON;
ALTER TABLE core.posting_normalized ADD COLUMN IF NOT EXISTS jobTypeSource VARCHAR;
ALTER TABLE core.posting_normalized ADD COLUMN IF NOT EXISTS rq1EligibleFlag BOOLEAN DEFAULT FALSE;
ALTER TABLE core.posting_normalized ADD COLUMN IF NOT EXISTS rq2EligibleFlag BOOLEAN DEFAULT FALSE;
ALTER TABLE core.posting_normalized ADD COLUMN IF NOT EXISTS ncsEligibleFlag BOOLEAN DEFAULT FALSE;
ALTER TABLE core.posting_normalized ADD COLUMN IF NOT EXISTS rq2ExclusionReason VARCHAR;
ALTER TABLE core.posting_normalized ADD COLUMN IF NOT EXISTS rq2ExclusionReasonsJson JSON;

ALTER TABLE mart.posting_analysis ADD COLUMN IF NOT EXISTS contractVersion VARCHAR DEFAULT 'UNCONTRACTED';
ALTER TABLE mart.posting_analysis ADD COLUMN IF NOT EXISTS crawlReleaseId VARCHAR DEFAULT 'NONE';
ALTER TABLE mart.posting_analysis ADD COLUMN IF NOT EXISTS dataVersion VARCHAR DEFAULT 'generated-structural-fixture-v2';
ALTER TABLE mart.posting_analysis ADD COLUMN IF NOT EXISTS parseVersion VARCHAR DEFAULT 'fixture-parse-v2';
ALTER TABLE mart.posting_analysis ADD COLUMN IF NOT EXISTS labelVersion VARCHAR DEFAULT 'fixture-label-v2';
ALTER TABLE mart.posting_analysis ADD COLUMN IF NOT EXISTS ncsMapVersion VARCHAR DEFAULT 'fixture-ncs-v2';
ALTER TABLE mart.posting_analysis ADD COLUMN IF NOT EXISTS dedupVersion VARCHAR DEFAULT 'fixture-dedup-v2';
ALTER TABLE mart.posting_analysis ADD COLUMN IF NOT EXISTS rq1EligibleFlag BOOLEAN DEFAULT FALSE;
ALTER TABLE mart.posting_analysis ADD COLUMN IF NOT EXISTS rq2EligibleFlag BOOLEAN DEFAULT FALSE;
ALTER TABLE mart.posting_analysis ADD COLUMN IF NOT EXISTS ncsEligibleFlag BOOLEAN DEFAULT FALSE;
ALTER TABLE mart.posting_analysis ADD COLUMN IF NOT EXISTS activityTextAvailableFlag BOOLEAN DEFAULT FALSE;
ALTER TABLE mart.posting_analysis ADD COLUMN IF NOT EXISTS externalApplyFlag BOOLEAN DEFAULT FALSE;
ALTER TABLE mart.posting_analysis ADD COLUMN IF NOT EXISTS externalDetailOnlyFlag BOOLEAN DEFAULT FALSE;
ALTER TABLE mart.posting_analysis ADD COLUMN IF NOT EXISTS jobTypeConflictFlag BOOLEAN DEFAULT FALSE;
ALTER TABLE mart.posting_analysis ADD COLUMN IF NOT EXISTS rq2ExclusionReason VARCHAR;
ALTER TABLE mart.posting_analysis ADD COLUMN IF NOT EXISTS rq2ExclusionReasonsJson JSON;

ALTER TABLE mart.time_series ADD COLUMN IF NOT EXISTS rq1EligibilityRate DOUBLE;
ALTER TABLE mart.time_series ADD COLUMN IF NOT EXISTS rq2EligibilityRate DOUBLE;
ALTER TABLE mart.time_series ADD COLUMN IF NOT EXISTS ncsEligibilityRate DOUBLE;
ALTER TABLE mart.time_series ADD COLUMN IF NOT EXISTS externalApplyShare DOUBLE;
ALTER TABLE mart.time_series ADD COLUMN IF NOT EXISTS externalDetailOnlyShare DOUBLE;
ALTER TABLE mart.time_series ADD COLUMN IF NOT EXISTS activityTextAvailabilityRate DOUBLE;
ALTER TABLE mart.time_series ADD COLUMN IF NOT EXISTS jobTypeConflictRate DOUBLE;
"""


def bootstrap_development_warehouse(path: str | Path) -> list[str]:
    with connect(path) as connection:
        connection.execute(DEVELOPMENT_DDL)
        for table in ("raw.linkareer_posting", "core.posting_normalized"):
            schema, name = table.split(".")
            columns = {
                row[0]
                for row in connection.execute(
                    "SELECT column_name FROM information_schema.columns WHERE table_schema = ? AND table_name = ?",
                    [schema, name],
                ).fetchall()
            }
            if "postingRawId" in columns and "rawPostingId" not in columns:
                connection.execute(f"ALTER TABLE {table} RENAME COLUMN postingRawId TO rawPostingId")
        rows = connection.execute(
            """
            SELECT table_schema || '.' || table_name
            FROM information_schema.tables
            WHERE table_schema IN ('raw', 'core', 'ncs', 'mart', 'qa')
            ORDER BY 1
            """
        ).fetchall()
    return [row[0] for row in rows]


def bootstrap_contract_warehouse(path: str | Path, ddl_path: str | Path) -> list[str]:
    ddl = Path(ddl_path).read_text(encoding="utf-8")
    assert_duckdb_executable_ddl(ddl)
    with connect(path) as connection:
        connection.execute(ddl)
        rows = connection.execute(
            "SELECT table_schema || '.' || table_name FROM information_schema.tables ORDER BY 1"
        ).fetchall()
    return [row[0] for row in rows]


def bootstrap_canonical_warehouse(path: str | Path, ddl_path: str | Path) -> dict[str, Any]:
    ddl = Path(ddl_path).read_text(encoding="utf-8")
    assert_duckdb_executable_ddl(ddl)
    statement_count = len([statement for statement in ddl.split(";") if statement.strip()])
    if statement_count < 36:
        raise ValueError(f"canonical DDL requires at least 36 statements, found {statement_count}")
    with connect(path) as connection:
        connection.execute(ddl)
        first_objects = connection.execute(
            """
            SELECT table_schema, table_name, table_type
            FROM information_schema.tables
            WHERE table_schema IN ('raw', 'core', 'ncs', 'mart', 'qa')
            ORDER BY 1, 2
            """
        ).fetchall()
        connection.execute(ddl)
        second_objects = connection.execute(
            """
            SELECT table_schema, table_name, table_type
            FROM information_schema.tables
            WHERE table_schema IN ('raw', 'core', 'ncs', 'mart', 'qa')
            ORDER BY 1, 2
            """
        ).fetchall()
        if first_objects != second_objects:
            raise ValueError("canonical DDL is not idempotent")
        schemas = [
            row[0]
            for row in connection.execute(
                "SELECT schema_name FROM information_schema.schemata WHERE schema_name IN ('raw','core','ncs','mart','qa') ORDER BY 1"
            ).fetchall()
        ]
        tables = [f"{schema}.{name}" for schema, name, kind in second_objects if kind == "BASE TABLE"]
        views = [f"{schema}.{name}" for schema, name, kind in second_objects if kind == "VIEW"]
        qa_view_results = {}
        for view in views:
            if view.startswith("qa."):
                connection.execute(f"SELECT * FROM {view} LIMIT 1").fetchall()
                qa_view_results[view] = "EXECUTED"
        gate = connection.execute("SELECT analysisReadyStatus FROM qa.vAnalysisReadyGate").fetchone()[0]
    if schemas != ["core", "mart", "ncs", "qa", "raw"] or len(tables) != 26 or len(views) != 6:
        raise ValueError(
            f"canonical warehouse object mismatch: schemas={schemas}, tables={len(tables)}, views={len(views)}"
        )
    if gate != "NOT_EVALUATED":
        raise ValueError(f"empty canonical warehouse must be NOT_EVALUATED, observed {gate}")
    return {
        "ddlStatementCount": statement_count,
        "firstRunSucceeded": True,
        "secondRunSucceeded": True,
        "idempotent": True,
        "schemas": schemas,
        "schemaCount": len(schemas),
        "tables": tables,
        "tableCount": len(tables),
        "views": views,
        "viewCount": len(views),
        "qaViews": qa_view_results,
        "analysisReadyGate": gate,
        "emptyDatabasePass": False,
    }
