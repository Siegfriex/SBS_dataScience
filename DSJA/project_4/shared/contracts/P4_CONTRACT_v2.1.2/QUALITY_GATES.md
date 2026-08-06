# P4 Quality Gates

- Status: `canonical`
- Contract version: `2.1.2`

| Gate | Requirement | Failure action |
|---|---|---|
| CONTRACT_SCHEMA | YAML validates; no duplicate tables or columns | stop |
| FIELD_LINEAGE | Every column has non-empty `source`, `derivation`, and `qualityRule` | stop |
| METRIC_METADATA | Every metric has explicit grain and `dedupApplied` | stop |
| DDL_BOOTSTRAP | DuckDB 1.5.x executes twice in one in-memory database | stop |
| PK_QA | `qa.vPrimaryKeyViolations` total is zero | stop |
| FK_QA | `qa.vForeignKeyViolations` total is zero | stop |
| ENUM_QA | `qa.vEnumViolations` total is zero | stop |
| NULL_QA | `qa.vNullabilityViolations` total is zero | stop |
| RESERVED_SCORE | Every `highDemandScore` is NULL and score status is reserved | stop |
| SOURCE_COVERAGE | All primary trend months are complete or explicitly excluded | stop |
| CAREER_LABEL | Macro F1 >= 0.85 and E0 precision >= 0.90 | review/stop |
| BOUNDARY | Required-preferred boundary precision >= 0.90 | review/stop |
| NCS_MAPPING | Precision >= 0.85, coverage >= 0.80, low confidence <= 0.20 | review/stop |
| OCR_BIAS | Monthly/company/job OCR coverage and failure concentration reported | review/stop |
| RESULT_LINEAGE | Every published number has code SHA and input mart SHA | stop |
| HANDOFF | Required producer handoff exists and hashes match | stop |
| SOURCE_ARCHITECTURE | APQ operations, hashes, SSR paths, and frontend build are versioned | review/stop |
| PAGINATION | Page progression and total-count reconciliation verified | stop |
| SOURCE_POLICY | Terms and robots status verified for the actual routes | stop |
| XLSX_SEMANTIC | Committed and regenerated workbooks have the same cell/formula/style signature | stop |
| HANDOFF_SCHEMA | Agent 3 handoffs validate, match contract version, and are checksummed | stop |
| SECRET_SCAN | No credential or private-key pattern in tracked files | stop |

Empty data tables make analytical gates `NOT_EVALUATED`, never PASS.
