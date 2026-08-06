# CRAWL_20260806_01

- agentId: `P4-A1-SOURCE` / agentName: `P4 Source Acquisition & Coverage Engineer`
- 이전 단계: `RECON_20260806_01` (`../RECON_20260806_01/`)
- contractVersion: 없음 (P4_CONTRACT_v2.1.x 물리 번들이 `DSJA/project_4/shared/contracts/`에 아직 존재하지 않음 — `BLOCKED_BY_CONTRACT`)

## 이 릴리스가 담고 있는 것

1. **HTTP client 정책 재검증(§7) 완료** — `httpx` + 명시적 연구용 User-Agent만으로 목록(APQ)·상세(SSR) 전부 200 정상. TLS impersonation 불필요. Production client = `httpx`.
2. **일자별 완전 페이지네이션 메커니즘 검증 및 실측** — `nodePagination.page`가 월 응답 전체에 전역 적용됨을 확인(일자별 개별 파라미터 아님). 2021-03을 완전 검증(1381/1381, 12회 요청), 2026-08은 26페이지 캡에서 중단(1947/1959=99.4%, **미완료로 정직하게 기록**).
3. **`monthly_coverage.csv`/`.parquet`** — 2020-01~2026-07 79개월 + 2019 스팟체크 5개월을 **전부 명시적으로 나열**(무음 누락 없음). 실제 완전검증된 건 1개월(2021-03)뿐이며 나머지는 `coverageReason=paginationUnverified`로 정직하게 표시.
4. **Masked fixture 3종(SSR) + 1종(APQ)** — Agent 2의 P0 blocking 요청(`A2-A1-P0-002`) 대응. `managerName/managerPhoneNumber/managerEmail`은 해시 마스킹.
5. **신규 발견**: `activity/339737`(제일약품) 케이스 재확인 결과 `ActivityText`는 실제로 존재하며, 외부 ATS 페이지의 **스크린샷 이미지를 `<img>`로 직접 임베드**하는 패턴이 있음 — OCR 라우팅 규칙이 `posting.files[].type='포스터'`뿐 아니라 `ActivityText.text` 내부 `<img>` 태그도 봐야 함 (신규 이슈로 Agent 3에 전달).

## 아직 안 한 것 (침묵 누락 아님, 명시적 보류)

- 2020-01~2026-07 전체 79개월 완전 페이지네이션 감사 (현재 1/79만 완전검증)
- Wayback CDX 생존편향 감사
- NCS 원천(data.go.kr) API 실측
- 정식 층화표본(n≥100)
- asset_manifest.jsonl / ncs_manifest.jsonl은 이번 패스에 수집한 게 없어 빈 파일로 존재

## 상태

`status = PARTIALLY_READY` (아래 HANDOFF.json 참조). `CRAWL_RELEASE_READY`로 선언하지 않음 — contractVersion 부재 + pagination 79개월 중 1개월만 완전검증.
