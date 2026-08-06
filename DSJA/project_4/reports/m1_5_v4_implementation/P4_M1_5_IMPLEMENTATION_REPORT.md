# P4 M1.5 v4.0 Implementation Report

## Executive verdict

`P4_M1_5_IMPLEMENTATION_READY_FOR_INDEPENDENT_AUDIT`

이 판정은 코드·schema·offline fixture·tests·observed replay가 독립감사에 넘길 수 있다는 뜻이다. production 데이터 또는 분석 준비 완료를 뜻하지 않는다.

## Authority

- Project root: `DSJA/project_4`
- SSOT: `shared/ssot/v4.0/P4_final_design_v4.0.md`
- SSOT SHA-256: `409866c166ce3874ce587ad3b1230bc530c036e9682be01bf3466aa1fd37a05a`
- Implementation evidence Git HEAD: `a2fe4fe61e1e9cda578e36ddb5ec0452850a5501`
- Run ID: `M1_5_V4_IMPLEMENTATION_20260806_01`

## Verified implementation

- Control: 12 schemas, 6 stages, 26 gates, 11 dependency edges; validator PASS.
- Crawl: fail-closed validator, topology/current-run binding, ActivityText fallback, source-policy kill switches; 38 tests PASS.
- Pipeline: deterministic semantic/OCR/structure/RQ2-B contract; 116 tests PASS.
- NCS: API/corpus/retrieval/reference/temporal/calibration implementation; 84 tests PASS.
- API fixtures: 8 synthetic success/empty/auth/parameter fixtures. Live calls 0; live probe NOT_EVALUATED.
- NCS candidate corpus: 13,442 units, 14,930 nodes, 14,906 edges; bridge/crosswalk 0; promotionAllowed=false.

## Observed replay

- postings: 137
- authoritative dates: 29/137 (21.17%)
- period mismatch: 0
- invalid canonical enums: 0
- raw SSR: 29; raw SHA mismatch: 0; declared/existence mismatch: 18
- requirement facts: 41; source blocks: 84; semantic chunks: 277
- OCR candidates: 30 rows / 29 postings; asset bytes: 0
- production Linkareer calls: 0; live API probes: 0; article numbers: 0

## Gate interpretation

M1.5-P is PARTIAL, M1.5-0 is PASS_WITH_FINDINGS, and M1.5-A through D remain BLOCKED or NOT_EVALUATED where evidence is absent. `highDemandScore` remains NULL. No production or analysis promotion is made.

Notebook이 실행됐다는 것은 분석데이터가 준비됐다는 뜻이 아니다.

구조적 QA 통과는 의미적 변수 완성도를 보장하지 않는다.

Observed-development 결과는 기사 결과가 아니다.

CSV는 canonical source가 아니다.

NCS candidate 생성은 NCS mapping 품질게이트 통과가 아니다.

## Roadmap

M1 snapshot freeze → M1.5 semantic QA → M2 full crawl → production preprocess → M3 gold/reference → analysis → article.
