# CRAWL_20260806_03

- agentId: `P4-A1-SOURCE` / contractVersion: **2.1.2**
- 이전 release: `CRAWL_20260806_02` (동결)

## 이번 릴리스 핵심 진전

1. **월별 pagination: 21/79개월 완전검증** (11 → 21, +10). **2022년 전체 12개월 100% 완료.** distinct posting id 합계 **40,551건**.
2. **APQ range 결합 의미론 확정**: `recruitStartAt`/`recruitCloseAt`는 **OR(합집합)**. 6개 대조실험으로 실증(`APQ_RANGE_SEMANTICS_FINAL.md`). 기존 completeness 판정 로직(bucket별 exhaustion)은 이미 옳았음을 재확인.
3. **NCS KSA API 진전**: 사용자 제공 인증키로 실호출 — `openapi14`가 유효 엔드포인트임을 확정(HTTP 200, 코드009). 단 필수 파라미터명은 15개 이상 시도에도 미확정. `UNVERIFIED`→`ENDPOINT_CONFIRMED_PARAM_SCHEMA_UNKNOWN`으로 좁혀짐.
4. **실제 raw HTML 저장 시작**: 2021-03 첫 주 29건, gzip 저장(`.gitignore` 처리, git에 올라가지 않음), fetch_manifest에 rawSha256/bytes/elapsedMs 포함.
5. **manifest 분리**: `fetch_manifest.jsonl`(요청 단위, raw가 실제로 저장된 것만) / `posting_manifest.parquet`(레코드 단위, 상세데이터 확보된 137건만).
6. **Wayback 생존율 2020-2023 4개년**: 전부 100% 생존(연도별 15건 표본).
7. **PII 마스킹 감사**: `reports/PII_MASKING_AUDIT.csv` — 추적 아티팩트 전체에서 raw PII 노출 0건 확인.

## 🔴 규모 격차 — 반드시 알아야 할 것

**79개월 목표 중 21개월만 완전, 발견된 40,551개 공고 ID 중 상세 데이터를 실제로 확보한 건 137건뿐입니다.** 전체 코퍼스(추정 수만~십만 건) 상세 raw HTML 수집은 이번 패스에서 시도하지 않았습니다 — 이미 발견된 21개월분만 전량 상세수집해도 1초당 1건 정책 기준 10시간+ 연속 수집이 필요하고, 79개월 전체는 그 몇 배 규모로 예상됩니다. 이건 "누락"이 아니라 **이 세션의 물리적 한계를 정직하게 인정**하는 것입니다.

## 상태

`status = CRAWL_RELEASE_CANDIDATE` (PARTIALLY_READY에서 상향 — 계약 연결, 21개월 검증, range 의미론 확정, 실제 raw lineage 착수 등 실질 진전 반영. 그러나 `CRAWL_RELEASE_READY`는 아직 아님 — Agent 2 validator 미실행, 전체 코퍼스 상세수집 미완료).
