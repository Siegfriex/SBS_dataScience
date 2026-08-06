# Agent 5 user decision packet

`USER_DECISION_REQUIRED`

## D-A5-001

- 질문: 현재 여섯 Notebook을 Crawl Notebook v1 source로 동결할지
- 현재 증거: Source integrity/parity passes, but six P1 defects remain.
- 선택지: Patch P1 then freeze / Freeze observed-dev-only now
- 권고안: Patch P1 then freeze
- 영향: Production lineage and order are trustworthy only after patch.
- 연기 가능: False

## D-A5-002

- 질문: M1.5 의미적 QA를 production crawl 전에 수행할지
- 현재 증거: Structural QA passes while full-corpus semantics and gold validation are NOT_EVALUATED.
- 선택지: Run M1.5 before M2 / Defer to post-crawl
- 권고안: Run M1.5 before M2
- 영향: Prevents structurally valid but semantically weak data from becoming production input.
- 연기 가능: False

## D-A5-003

- 질문: asset 수집을 CRAWL_RELEASE_READY 필수조건으로 유지할지
- 현재 증거: 59 candidates/30 OCR candidates exist, but fetched assets=0 and gate is NOT_EVALUATED.
- 선택지: Keep mandatory / Allow text-only release with explicit eligibility exclusion
- 권고안: Keep mandatory for RQ2-B; permit a separately named text-only release only if needed
- 영향: Determines whether image-only duties can enter RQ2-B.
- 연기 가능: True
