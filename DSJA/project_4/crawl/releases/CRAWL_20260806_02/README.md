# CRAWL_20260806_02

- agentId: `P4-A1-SOURCE` / contractVersion: **2.1.2** (vendored, checksums PASS)
- 이전 release: `CRAWL_20260806_01` (동결, 변경 없음)

## 이번 릴리스 핵심

1. **P4_CONTRACT_v2.1.2 연결 완료** — cherry-pick 2건, `shared/contracts/P4_CONTRACT_v2.1.2/` 11개 파일 체크섬 전부 PASS.
2. **월별 페이지네이션: 11/79개월 완전 검증** (2020-01,02,04,05,06 / 2021-01,02,03,04 / 2022-01,02). 나머지는 정직하게 `unverified`.
3. **층화표본 n=126** (연도별 18건 × 7년, 2020-2026) — 핵심 수치:
   - externalApplyShare 99.2%, **externalDetailOnlyShare 19.0%**(외부지원=본문없음이 아님을 확인 — 이전 추정보다 훨씬 낮음)
   - rq2EligibilityRate 81.0%, ncsEligibilityRate 21.4%
   - **imageOcrRoutingRate 89.7% vs hasPosterFile 0%** — 포스터 파일 기준 OCR 라우팅은 이 표본에서 전혀 안 걸리고, 본문 내 임베디드 이미지가 압도적 다수. 기존 라우팅 가정 폐기 필요(A1-A3-009 P0 격상).
4. **Wayback 생존율 2020/2021/2022 각 15건 샘플 = 전부 100% 생존**.
5. **NCS 능력단위 CSV 실제 다운로드 완료**(13,442행, 수준 1~8 분포 확인, data.go.kr/15083321). KSA 원천(15157542)은 여전히 키 필요로 미수집.
6. **Agent 3 계약과의 정합성 발견**: `SOURCE_POLICY_GATE.md`가 구식 curl_cffi(impersonate) 근거로 `REVIEW_REQUIRED` 판정 중인데, CRAWL_20260806_01에서 이미 httpx(위장없음) 검증 완료 — 갱신 요청함(A1-A3-012).
7. `crawl_manifest.jsonl` 필드명을 Agent 2 요청대로 `contentSha256`→`rawSha256`으로 수정.

## 아직 안 한 것 (명시적 보류)

- 79개월 중 68개월 pagination 미검증 (침묵 누락 아님, monthly_coverage.csv에 전부 명시)
- 상세 공고 raw HTML per-record lineage 미보존(파생 필드만 저장 — n=126 표본은 요약 JSON만 있음, 이건 알려진 gap)
- NCS KSA API(15157542) 미확인 — 사람이 API 키 발급해야 진행 가능
- 정식 사전설계 층화(n=126은 연도 축만 사전설계, 나머지 축은 사후 보고)

## 상태

`status = PARTIALLY_READY`. `CRAWL_RELEASE_READY` 미선언 — 79개월 중 11개월만 완전검증, 상세 raw lineage 미보존.
