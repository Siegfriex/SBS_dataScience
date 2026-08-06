from __future__ import annotations

from pathlib import Path

from p4.contracts.validators import assert_duckdb_executable_ddl
from p4.warehouse.connection import connect


DEVELOPMENT_DDL = """
CREATE SCHEMA IF NOT EXISTS raw;
CREATE SCHEMA IF NOT EXISTS core;
CREATE SCHEMA IF NOT EXISTS ncs;
CREATE SCHEMA IF NOT EXISTS mart;
CREATE SCHEMA IF NOT EXISTS qa;

CREATE TABLE IF NOT EXISTS raw.linkareer_posting (
    postingRawId VARCHAR PRIMARY KEY,
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
    postingRawId VARCHAR NOT NULL,
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
    postingEligibleFlag BOOLEAN NOT NULL,
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
    postingId VARCHAR NOT NULL,
    canonicalPostingId VARCHAR NOT NULL,
    periodMonth DATE NOT NULL,
    cohortType VARCHAR NOT NULL,
    jobCodeLevel VARCHAR NOT NULL,
    jobCode VARCHAR NOT NULL,
    postingEligibleFlag BOOLEAN NOT NULL,
    canonicalRecordFlag BOOLEAN NOT NULL,
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
"""


def bootstrap_development_warehouse(path: str | Path) -> list[str]:
    with connect(path) as connection:
        connection.execute(DEVELOPMENT_DDL)
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

