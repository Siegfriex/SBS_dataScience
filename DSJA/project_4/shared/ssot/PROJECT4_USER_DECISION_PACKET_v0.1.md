# PROJECT4_USER_DECISION_PACKET_v0.1

- state: `USER_DECISION_REQUIRED`
- immediate decisions: 3
- before M2: 2
- before M3: 2
- 기술적으로 자동 진행 가능한 읽기 전용 문서·테스트 보강: `AUTO_PROCEED_RECOMMENDED`

## A. 즉시 결정

### D-ORCH-001

질문: 어느 authority를 P4 Notebook Observed v1.0 snapshot으로 동결할 것인가?

현재 상태: 네 원격 HEAD와 24-source bundle은 재현 가능하지만 동일 observed bundle ID의 crawl/pipeline lineage가 108행 갈리고 76 runtime artifact가 원격에 없다.

선택지:

- A. 원격 HEAD + crawl export를 동결하고 pipeline copy는 superseded로 표시 — 현재 지정 감사 대상을 authority로 고정하나 observed DB를 재생성해야 한다.

- B. 원격 HEAD + pipeline/observed DB copy를 동결하고 crawl copy는 superseded로 표시 — 현재 DB와 일치하지만 지정 crawl export를 대체해야 한다.

- C. 동결을 보류하고 새 dataVersion으로 두 copy를 재조정 — 가장 명확하지만 snapshot 확정이 늦어진다.

권고안: **C**

권고 이유: 동일 ID에 서로 다른 lineage를 남긴 채 A/B를 선택하면 provenance가 왜곡된다. 새 dataVersion으로 authority를 명시하는 것이 가장 안전하다.

결정을 미룰 수 있는지: 아니오, 다음 통제 작업 전 필요

### D-ORCH-002

질문: Agent 3 remote HEAD b64270b를 canonical integration base로 유지할 것인가?

현재 상태: 계약 v2.1.2와 control evidence가 remote parity이며 오케스트레이터 branch도 이 HEAD에서 분기했다.

선택지:

- A. b64270b 유지 — 현재 계약/Notebook control을 안정된 기준으로 사용한다.

- B. 다른 Agent branch를 base로 변경 — 계약·control의 재감사가 필요하다.

권고안: **A**

권고 이유: 현재 계약 checksum과 docs repo parity가 검증됐고 다른 Agent 코드는 아직 merge 대상이 아니다.

결정을 미룰 수 있는지: 아니오, 다음 통제 작업 전 필요

### D-ORCH-003

질문: M1.5 semantic QA를 M2 full crawl보다 먼저 수행할 것인가?

현재 상태: 날짜 0/137, career resolved 0/137, enum 불일치가 있어 같은 결함을 full corpus로 확대할 위험이 있다.

선택지:

- A. M1.5를 먼저 수행 — 소규모 표본에서 contract/semantic 결함을 수정한 뒤 M2 비용을 집행한다.

- B. M2를 먼저 수행 — 수집은 빨라지지만 대규모 재처리 가능성이 높다.

권고안: **A**

권고 이유: 현재 blocker는 표본 크기보다 변수 정의와 lineage authority다.

결정을 미룰 수 있는지: 아니오, 다음 통제 작업 전 필요

## B. M2 전 결정

### D-ORCH-004

질문: production crawl의 source-policy, 기간, 2019 처리 원칙을 승인할 것인가?

현재 상태: robots allowed/reviewedConditional/transparent-client evidence는 있으나 production 승인 record가 없고 2020-01~2026-07 중 58개월이 미검증이다. 2019는 platform pre-launch다.

선택지:

- A. 2020-01~2026-07만 승인, 2019 제외 — 현재 operational window와 일치하고 79개월 gate를 명확히 한다.

- B. 2019 포함 — 별도 pre-launch regime과 결측 처리 규칙이 필요하다.

- C. production crawl 승인 보류 — M2는 시작하지 않고 policy evidence만 보강한다.

권고안: **A**

권고 이유: 2019 recruit category는 operational 비교기간으로 방어하기 어렵다. 실제 실행 전 qa.sourcePolicyAudit human approval을 필수로 한다.

결정을 미룰 수 있는지: 예, 해당 milestone 전까지

### D-ORCH-005

질문: asset/OCR 범위와 NCS API key custody를 어떻게 확정할 것인가?

현재 상태: asset lineage 0, period 하드코딩 결함이 있고 Agent4 ignored .env에 비공개 키가 있다. tracked secret은 발견되지 않았다.

선택지:

- A. Linkareer-hosted 핵심 자산만 수집/OCR, 키 회전 후 secret store 사용 — 범위를 제한하고 provenance·보안을 통제한다.

- B. 외부 ATS 자산까지 확대 — source-policy와 라이선스 검토 범위가 크게 늘어난다.

- C. asset/OCR과 KSA API를 M2에서 제외 — 텍스트 기반 M2는 가능하나 이미지 공고와 KSA enrichment가 남는다.

권고안: **A**

권고 이유: 현재 collector 정책과 최소수집 원칙에 맞고 로컬 키의 장기 보관 위험을 줄인다.

결정을 미룰 수 있는지: 예, 해당 milestone 전까지

## C. M3 전 결정

### D-ORCH-006

질문: core AI·IT 범위를 69 included/51 excluded로 동결하고 middle 20-02 통신, 20-03 방송을 제외할 것인가?

현재 상태: 현재 review candidate는 120개이며 20-01의 69개만 included, 20-02 38개와 20-03 13개는 excluded다.

선택지:

- A. 현재 69/51 동결 — 명확한 ICT-core 분석을 유지한다.

- B. 통신 20-02 포함 — 범위가 107 subcategories로 확대돼 gold strata와 해석이 달라진다.

- C. 통신·방송 모두 포함 — 120 전체가 포함되어 AI·IT core 개념이 가장 넓어진다.

권고안: **A**

권고 이유: 현재 명칭은 일부 derived이며 gold가 없으므로 보수적 core부터 동결하는 편이 해석 가능하다.

결정을 미룰 수 있는지: 예, 해당 milestone 전까지

### D-ORCH-007

질문: D-023 KSA optional 정책과 gold n=300, 30% 이중코딩, 검수 책임자를 승인할 것인가?

현재 상태: KSA는 미수집/optional 제안 상태이고 gold template는 0행이며 precision, coverage, low-confidence는 NOT_EVALUATED다.

선택지:

- A. KSA optional + n=300 + 30% 이중코딩 + 사용자 지정 검수자 — base lexical mapping 품질을 먼저 평가하고 KSA를 enrichment로 둔다.

- B. KSA를 blocking prerequisite로 지정 — KSA API schema가 해결될 때까지 M3가 중단된다.

- C. gold 규모/이중코딩 축소 — 비용은 줄지만 precision/coverage 주장 신뢰도가 낮아진다.

권고안: **A**

권고 이유: D-023 취지와 현재 계약 게이트에 맞으며 빈 gold에서 성능을 제조하지 않는다. 단 검수 담당자 실명/역할은 사용자가 지정해야 한다.

결정을 미룰 수 있는지: 예, 해당 milestone 전까지
