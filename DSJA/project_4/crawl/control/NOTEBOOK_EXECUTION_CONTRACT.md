# P4 Notebook Execution Contract

- contract version: `2.1.2`
- control version: `notebook-execution-contract-v1`
- M1 promotion target: `OBSERVED_DEV_CSV_READY`
- scope: Notebook orchestration and stage termination artifacts

This contract makes the M1 control draft executable. Notebook code orchestrates
versioned modules; it does not become the only implementation or the only data
store. Machine-readable run parameters are validated by
`NOTEBOOK_EXECUTION_CONTRACT.schema.json`, stage manifests by
`STAGE_MANIFEST.schema.json`, and metrics by `STAGE_METRICS.schema.json`.

## 1. M1 observed-development constants

Every M1 stage MUST use these values without override:

```text
RUN_MODE = observed-dev
CONTRACT_VERSION = 2.1.2
CRAWL_RELEASE_ID = CRAWL_20260806_03
DATA_PROVENANCE = OBSERVED_DEVELOPMENT_ONLY
EMPIRICAL_ANALYSIS_ALLOWED = false
PROMOTION_ALLOWED = false
RANDOM_SEED = 20260806
```

The observed input is partial evidence, not a population release. An M1 run
MUST use an isolated observed-dev database and output root. It MUST NOT write to
the production DuckDB, publish a production crawl release, compute gold
performance claims, or enable an RQ/analysis stage.

## 2. Required parameter and metadata contract

The first executable code cell is the parameter cell and declares, at minimum:

```python
RUN_MODE = "observed-dev"
CONTRACT_VERSION = "2.1.2"
CRAWL_RELEASE_ID = "CRAWL_20260806_03"
DATA_VERSION = ""
AS_OF_DATE = "2026-08-06"
RANDOM_SEED = 20260806
```

Before processing, each stage resolves and validates these metadata fields:

```text
agentId, branch, gitHead, contractVersion, crawlReleaseId, dataVersion,
runMode, dataProvenance, startedAt, empiricalAnalysisAllowed, promotionAllowed
```

Paths in parameters, manifests, metrics, and outputs are repository-relative.
Absolute paths, home-directory shortcuts, parent traversal, credentials,
cookies, authorization headers, session values, and complete query strings are
not permitted in committed or exported artifacts.

## 3. Notebook construction and execution

- A Notebook only declares parameters, validates inputs, calls `src/` modules,
  displays summaries, writes versioned artifacts, runs QA, and records a run.
- A Notebook does not copy a collector/parser implementation or pass Python
  memory to the next Notebook. Downstream stages read files or DuckDB tables.
- Source Notebooks have deterministic cell IDs and zero stored outputs.
- The parameter cell is first. Hidden mutable global state and manual path
  edits are prohibited.
- Rendering is registry-driven and supports separate `--check`, `--render`, and
  `--force` operations. The default operation never overwrites a differing
  source Notebook. `--check` is read-only and a render shows the diff before a
  forced replacement.
- Interactive Jupyter and parameterized `papermill`/`nbclient` execution use the
  same parameter and artifact contracts.
- Identical input hashes, parameter hash, code revision, contract version, and
  seed produce semantically identical canonical output.
- The zero-byte `P4 Notebook-First.ipynb` is checksummed and archived as
  `crawl/archive/invalid_notebooks/P4 Notebook-First.ipynb.zero-byte.invalid`.
  The executable master is `crawl/notebooks/P4_Notebook_First_Master.ipynb`.

## 4. Stage termination contract

Every stage, including a failed stage, closes its run directory with exactly
these control artifacts:

```text
stage_manifest.json
stage_metrics.json
stage_quality.csv
CHECKSUMS.sha256
```

Data outputs are first written to a temporary run location. A required gate
failure, schema/checksum mismatch, duplicate primary key, missing lineage, or
invalid denominator prevents canonical publication. A failed run retains its
failure manifest and evidence but does not leave partial data at the canonical
path. Empty input is `NOT_EVALUATED`, never an automatic pass.

`stage_quality.csv` uses these columns:

```text
gateId,ruleId,severity,status,observedValue,threshold,evidencePath
```

`CHECKSUMS.sha256` covers every persisted stage artifact except itself. Paths
in the checksum file are relative to the run directory.

## 5. Canonical data and export policy

```text
DuckDB / Parquet = machine canonical
CSV              = human inspection and delivery export
```

CSV is generated from canonical Parquet using `utf-8-sig` and comma delimiter.
The export manifest records both hashes, row and column counts, column order,
null encoding, line ending, and exporter hash. CSV-to-Parquet semantic equality
is a required export gate; CSV is not accepted as a canonical machine input.

The canonical eligibility columns are:

```text
postingEligibleFlag
rq1EligibleFlag
rq2EligibleFlag
ncsEligibleFlag
```

No compatibility eligibility alias is included in canonical M1 exports.
`highDemandScore`, if present, is nullable and every M1 value MUST be null.

## 6. NCS and D-023

M1 NCS output is a development-only lexical baseline:

```text
mappingMode = LEXICAL_BASELINE
codeSetStatus = REVIEW_REQUIRED
goldValidatedFlag = false
denseScore = null
```

The 120-code candidate set (69 included, 51 excluded) is a review input, not a
production freeze. Precision, final coverage, final low-confidence judgments,
RQ2-B results, and production readiness claims are prohibited in M1.

Decision `D-023` is `PROVISIONAL`: KSA is optional enrichment and does not block
M1. It is reconsidered only if production base mapping fails its precision,
coverage, or low-confidence quality gates.

## 7. Promotion semantics

Passing observed-development rows of `NOTEBOOK_GATE_MATRIX.csv`, together with
checksum, lineage, semantic equality, secret/PII, clean-source-Notebook, and
canonical-database-contamination checks, allows Agent 3 to declare:

```text
OBSERVED_DEV_CSV_READY
```

That declaration does not imply a production crawl release, RQ data readiness,
gold validation, or analysis readiness. `promotionAllowed` remains `false`
inside every M1 artifact; the declaration is a development handoff status, not
a production promotion.
