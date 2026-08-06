# P4 Claude Code 프롬프트 팩

- 버전: `v2.0.0` / 기준일: `2026-08-06`
- 준거: `P4_PROJECT_SSOT_v2.md`, `USER_REVIEW_DECISIONS.md`, `P4_DATASET_SPEC_v2.0.md`, `P4_WAREHOUSE_DDL_v2.0.sql`
- 사용법: `docs/ssot/`에 위 4개 문서를 넣고 **P0부터 한 단계씩** 붙여넣는다
- 운영 정책은 별도 CLAUDE.md 문서로 고정하지 않고, 담당 에이전트(인세인서치 에이전트)의 판단에 따라 단계별로 결정한다

## 붙여넣기 순서

```text
→ PROMPT 0  정찰 (검색 중심, 코드 없음)      → 사람 승인
→ PROMPT 1  스키마 부트스트랩
→ PROMPT 2  수집기 골격 + 파일럿 100건        → 사람 승인
→ PROMPT 3  인덱스 전량 수집
→ PROMPT 4  ID 열거 백필 + coverage 감사      → 사람 승인 (분석 구간 확정)
→ PROMPT 5  상세·에셋 수집
→ PROMPT 6  OCR
→ PROMPT 7  정규화·트랙분리·섹션·요건추출
→ PROMPT 8  90일 중복 처리
→ PROMPT 9  골드셋 구축                       → 사람이 직접 라벨
→ PROMPT 10 라벨러 + 게이트 측정              → 게이트 통과까지 반복
→ PROMPT 11 NCS 원천 수집
→ PROMPT 12 NCS 매핑 + 게이트 측정            → 게이트 통과까지 반복
→ PROMPT 13 마트 구축
→ PROMPT 14 RQ1·RQ2 분석 + resultManifest
→ PROMPT 15 RQ4 / PROMPT 16 RQ3 / PROMPT 17 릴리스
```

---

# PROMPT 0 — 정찰 (코드 작성 없음, 검색·확인만)

```text
docs/ssot/ 의 4개 문서를 먼저 전부 읽어라. 이 단계에서는 수집 코드를 작성하지 않는다.
목표는 "링커리어를 어떻게, 어디까지 수집할 수 있는가"를 숫자로 확정하는 것이다.

조사 항목:

A. 접근 허용성
   1. https://linkareer.com/robots.txt 원문을 가져와 docs/audit/robots_20260806.txt 로 저장하고
      calendar, activity, list 경로의 허용 여부를 표로 정리
   2. 이용약관에서 자동수집·크롤링 관련 조항을 찾아 원문 위치와 요지를 기록
   3. 판단이 애매하면 "애매하다"고 쓰고 사람 결정 항목으로 올려라. 임의로 허용 판정하지 않는다

B. 페이지 구조
   4. 캘린더 목록이 SSR인지 CSR인지, 페이지네이션인지 무한스크롤인지
   5. 목록·상세가 내부 JSON 또는 GraphQL 요청을 쓰는지. 쓴다면 엔드포인트, 메서드,
      요청 본문 형태, 페이지네이션 파라미터, 응답 필드 목록을 schemas/ 아래 JSON으로 저장
   6. 상세 페이지에서 다음 필드가 어디에 있는지 셀렉터 또는 JSON 경로로 매핑:
      제목 / 기업명 / 게시일 / 마감일 / 채용유형 / 경력요건 / 학력 / 담당업무 / 필수요건 / 우대요건 / 이미지

C. 과거분 접근성 — 가장 중요
   7. /activity/{id} 가 순차 정수인지 확인
   8. 서로 다른 시기 공고 30건 이상에서 (id, 게시일) 앵커를 수집해
      docs/audit/id_date_anchors.csv 로 저장하고 단조성을 검증
   9. 이 앵커로 2019·2020·2021·2022·2023·2024·2025·2026 각 연도 경계 id를 추정
  10. 각 연도에서 무작위 30개 id를 실제로 조회해 생존율(200 + 본문 존재)을 측정하고
      docs/audit/survival_by_year.csv 로 저장
  11. web.archive.org CDX API로 2019~2022 linkareer.com/activity/* 스냅샷 목록을 받아
      "존재했으나 현재 삭제된 공고" 규모를 추정

D. 표본 성격
  12. 무작위 100건에서 다음 비율을 측정:
      본문 텍스트만 / 이미지 포함 / 이미지 전용
      그리고 postingKind 분포(인턴·신입·경력·공모전·대외활동·교육과정)를 사람이 눈으로 세어 기록
  13. 텍스트 길이 분포(중앙값, p10, p90)를 측정해 validPosting의 120자 임계값이 타당한지 검토

E. 참고 자료 조사
  14. 공공데이터포털에서 NCS 능력단위 수준(1~8) 파일데이터, NCS 기준정보 조회 API,
      고교직업교육과정 정보 서비스(능력단위요소·KSA·레벨)의 현재 데이터셋 ID와 필드를 확인해
      docs/audit/ncs_sources.md 로 정리. 데이터셋 ID는 변경될 수 있으니 반드시 실제 확인한다

산출물: docs/audit/P0_RECON_REPORT.md
반드시 포함할 결론:
  - 수집 방식 권고 (내부 JSON / HTML / 렌더링) 와 근거
  - 연도별 확보 가능 추정 공고 수와 생존율
  - RQ1 분석 구간 권고안: 2019~2026 그대로 가능한가, 아니면 하한을 올려야 하는가
  - 이미지 전용 공고 비율에 따른 OCR 필요 규모와 예상 비용
  - 사람의 결정이 필요한 항목 목록

작업 후 멈추고 승인을 기다려라. 승인 없이 PROMPT 1로 진행하지 않는다.
```

---

# PROMPT 1 — 스키마 부트스트랩

```text
docs/ssot/P4_WAREHOUSE_DDL_v2.0.sql 를 그대로 적용해 data/warehouse/p4.duckdb 를 생성하라.

작업:
1. src/p4/warehouse/bootstrap.py — DDL 실행, 멱등(존재하면 스킵), --recreate 옵션
2. src/p4/common/keys.py — P4_DATASET_SPEC §3 의 결정적 키 생성식 전부 구현
   (postingId, rawPostingId, trackId, sectionId, requirementId, assetId, ocrId, matchId,
    duplicateGroupId, companyKey, metricId, normalize, normalizeCompany)
3. src/p4/common/versions.py — 버전 상수와 dataVersion 계산(구성 버전 해시 기반)
4. src/p4/common/time.py — Asia/Seoul 고정, periodMonth(월 1일) 변환
5. configs/ 하위 yaml 스켈레톤 생성: project, sources, selectors, labels, ncsBands,
   coreAiItNcsCodes, dedup, paths.local.example
6. raw.sourceRegistry 에 linkareer, ncsFile, ncsApi 초기 행 삽입.
   robotsAllowed 와 accessMode 는 P0 결과를 그대로 반영

테스트 (tests/unit/):
- 동일 입력에 대한 키 생성 결과가 항상 같다
- 모든 ENUM 값이 SSOT 문서와 일치한다 (문서 파싱해서 대조)
- highDemandScore 에 값을 넣으면 CHECK 위반으로 실패한다
- bootstrap 을 두 번 실행해도 테이블 수·컬럼 수가 동일하다

수락 기준: pytest 전부 통과, `SELECT * FROM qa.vAnalysisReadyGate` 가 에러 없이 실행됨.
금지: DDL의 컬럼·제약 임의 변경. 필요하면 제안하고 멈춘다.
```

---

# PROMPT 2 — 수집기 골격 + 파일럿 100건

```text
P0 리포트가 권고한 수집 방식으로 수집기 골격을 만들고, 파일럿 100건만 수집하라.

구조 (하나의 파일에 몰아넣지 말 것):
  src/p4/ingest/linkareer/discovery.py  # 후보 URL을 raw.crawlFrontier에 넣는 일만 한다
  src/p4/ingest/linkareer/fetcher.py    # frontier 소비, raw 파일 저장, manifest append, 색인 INSERT
  src/p4/ingest/linkareer/store.py      # 경로 규칙, gzip, sha256, manifest jsonl
  src/p4/ingest/linkareer/policy.py     # rate limit, 지터, 백오프, robots, kill switch
  src/p4/cli.py                         # p4 ingest linkareer index|detail|asset

정책 구현:
- 동시성 2, 요청 간 0.7~1.5초 지터
- 재시도는 429/5xx만 지수 백오프 2·4·8·16초 최대 5회
- 403 또는 최근 200건 성공률 90% 미만 → 즉시 전체 중단, crawlRun.abortReason 기록, 종료코드 2
- User-Agent: "SBS-P4-Research-Bot/0.1 (+연구목적; 연락처는 .env의 CONTACT_EMAIL)"
- 모든 요청은 fetch_manifest.jsonl 에 1줄 append

파일럿 실행: `p4 ingest linkareer detail --limit 100 --sample stratified-by-year`
그리고 tests/fixtures/ 에 대표 10건을 골든 샘플로 고정 저장.

보고:
- 성공률, 평균 응답시간, 저장 용량
- 100건의 필드 추출 성공률을 필드별로 표로
- 실패 원인 분류
- 셀렉터·JSON 경로가 시기별로 다른 경우가 있는지 (링커리어 리뉴얼 이력 탐지)

작업 후 멈춰라. 파일럿 결과를 사람이 승인하기 전에 전량 수집을 시작하지 않는다.
```

---

# PROMPT 3 — 인덱스 전량 수집

```text
캘린더 인덱스를 2019-01부터 2026-08-06까지 전량 수집해 raw.linkareerIndexRaw 를 채워라.

- activityType=activity 와 activityType=recruit 두 경로를 모두 수집한다
- indexCategoryRaw 는 원문 그대로 보존한다. 이 값을 postingKind 라벨로 쓰지 않는다
- 중단·재시작이 가능해야 한다. frontier state 만 보고 이어서 진행한다
- 월별 발견 건수를 qa.monthlyCoverageAudit.discoveredCount 에 기록한다

보고: 월별 발견 건수 시계열, 인덱스가 비어 있는 구간, 두 경로의 중복률.
인덱스가 특정 시점 이전부터 비어 있으면 그 사실을 명확히 보고하고 PROMPT 4의 우선순위를 높여라.
```

---

# PROMPT 4 — ID 열거 백필 + coverage 감사 (분석 구간을 확정하는 단계)

```text
인덱스로 닿지 않는 과거 공고를 /activity/{id} 순차 열거로 백필하고, 월별 신뢰도를 확정하라.

작업:
1. docs/audit/id_date_anchors.csv 를 사용해 id↔게시일 단조 보간 모델을 만든다
   (선형 보간 + 이상치 제거. 모델과 잔차를 docs/audit/id_date_model.md 에 기록)
2. 2019-01~2026-08 구간의 id 범위를 추정하고 discoveryRoute='idEnumeration' 으로 frontier 적재
3. wayback CDX 결과에서 얻은 id 를 discoveryRoute='waybackCdx' 로 추가 적재
4. 열거 수집을 실행한다. 404/410 은 state='DEAD' 로 기록하되 삭제하지 않는다
5. postedAt 을 확정한다. 우선순위: 상세 명시 > 인덱스 명시 > id 보간 > wayback 스냅샷
   postedAtSource 와 postedAtConfidence 를 반드시 채운다
6. qa.monthlyCoverageAudit 을 전 구간 채운다.
   coverageStatus 규칙: survivalRate ≥ 0.85 complete / 0.60~0.85 partial / < 0.60 insufficient

산출물: docs/audit/P4_COVERAGE_DECISION.md
  - 월별 생존율 곡선과 coverageStatus 표
  - RQ1 분석 구간 확정안 (예: 2021-01~2026-07 로 축소)
  - 생존편향이 entryPostingRate·internPostingRate 를 어느 방향으로 왜곡할 수 있는지 서술

이 단계의 결론이 기사 전체의 기간을 결정한다. 반드시 멈추고 승인을 받아라.
승인 결과는 qa.decisionLog 에 기록한다.
```

---

# PROMPT 5 — 상세·에셋 수집

```text
승인된 분석 구간의 상세 공고와 첨부 이미지를 전량 수집하라.

- raw.linkareerPostingRaw, raw.postingAsset 을 채운다
- 이미지는 assetSha256 기준으로 중복 저장하지 않는다 (재게시 포스터가 많다)
- bodyTextLength, imageCount 를 수집 시점에 계산해 저장한다
- 대용량이므로 배치 단위로 커밋하고, 중단 후 재시작을 실제로 한 번 테스트해 보고하라

보고: 총 공고 수, 이미지 전용 추정 건수, 고유 이미지 수, 저장 용량, OCR 대상 예상 건수.
```

---

# PROMPT 6 — OCR

```text
이미지 공고에서 텍스트와 구조를 추출해 raw.ocrResult 를 채워라.

라우팅: bodyTextLength < 300 또는 hasImageOnlyBody 인 공고를 OCR 큐에 넣는다.

엔진은 adapter 패턴으로 분리한다: src/p4/ocr/adapters/{visionLlm,clovaOcr,upstage,paddleOcr}.py
파일럿 골드 50건으로 엔진을 비교해 docs/audit/ocr_benchmark.md 를 만든다.
비교 지표: 한글 문자 정확도, 섹션 헤더 인식률, 표 구조 복원률, 건당 비용, 건당 지연.

추출 방식은 단순 텍스트 덩어리가 아니라 구조 직접 추출을 우선한다.
ocrStructJson 스키마:
  {"title":str,"duties":[str],"required":[str],"preferred":[str],
   "employmentType":str,"minCareerMonths":int|null,"degree":str|null,"confidence":float}
ocrText 와 ocrBlocksJson 도 함께 보존한다. 좌표가 있어야 섹션 복원이 가능하다.

비용 통제: 긴 변 1600px 리사이즈, assetSha256 캐시, ocrCostUsd 기록.
ocrConfidence 하위 10% 는 ocrReviewFlag=TRUE 로 표시한다.

보고: 엔진 선택 근거, 처리 건수, 총비용, 검수 필요 건수.
```

---

# PROMPT 7 — 정규화·트랙분리·섹션·요건추출

```text
raw 를 core 레이어로 변환하라. raw 를 절대 수정하지 않는다.

7-1. core.postingNormalized
 - html 텍스트와 ocrText 를 병합하되 blockSource 로 출처를 보존
 - postingKind 판정. 판정 우선순위와 recruitUnknown/other 구분은 DATASET_SPEC §2 를 그대로 따른다
   공모전·대외활동·교육과정·서포터즈는 절대 recruit* 로 분류하지 않는다
 - companyKey, 마스킹(담당자 이름·전화·이메일), validPosting, invalidReason 계산
 - recruitmentScope 판정. 링커리어 URL 종류를 라벨 근거로 쓰지 않는다

7-2. core.postingTrack
 - 섹션 헤더·표·모집분야 목록을 근거로 신입·인턴·경력 트랙을 분리
 - 분리 실패 시 trackType='mixedUnresolved', mixedResolvedFlag=FALSE
 - 같은 공고를 여러 건으로 과대계산하지 않는다. 공고 수는 항상 distinct postingId

7-3. core.postingSection
 - sectionType 분류. 담당업무와 필수요건과 우대요건을 반드시 분리한다

7-4. core.requirementFact
 - obligation(required/preferred/unknown) 을 문장 위치와 문말 표현으로 판정
 - evidenceText 를 비운 행을 만들지 않는다
 - certificateClass 는 기능사·산업기사·기사·기능장·기술사 정규식만 사용, 미매칭은 NULL
 - requiredDegreeLevel 은 highSchool/associate/bachelor/master/doctor, 요구 없음은 NULL
 - 도구·언어는 requiredToolCount 에만 반영하고 NCS 수준을 부여하지 않는다

수락 기준:
- 골든 10건에 대한 섹션 분리 결과가 fixtures 기대값과 일치
- 재실행 시 행수·키가 동일 (멱등성 통합테스트)
- validPosting 집계가 monthlyCoverageAudit 과 모순 없음

보고: postingKind 분포, 트랙 분리 성공률, mixedUnresolved 비율,
      obligation 판정 불가(unknown) 비율. unknown 이 15% 를 넘으면 규칙을 먼저 고쳐라.
```

---

# PROMPT 8 — 90일 중복·재게시 처리

```text
SSOT §12 를 구현하라.

1. 후보 생성: 동일 companyKey, 게시일 차이 90일 이하, 동일·유사 jobCode
2. 유사도: 정규화 제목 유사도 + 본문 SimHash 64bit(해밍 ≤ 3) 또는 MinHash LSH
3. 판정: 날짜 연장·재게시는 같은 duplicateGroupId. 요구조건·모집직무가 실질 변경되면 별도 공고
4. canonicalPostedAt = 그룹 최초 게시일. 가장 완전한 원문에 canonicalRecordFlag=1
5. repostCount 보존. 원본 행은 삭제하지 않는다
6. 모든 판정 근거를 core.postingDedupEdge 에 남긴다

임계값은 configs/dedup.yaml 로 외부화하고, 무작위 100쌍을 사람이 검수할 수 있게
reports/tables/dedup_review_sample.csv 를 출력하라.

보고: 그룹 수, 최대 그룹 크기, 월별 dedup 전후 공고 수 변화율.
dedup 이 특정 월에 20% 넘게 영향을 주면 그 사실을 강조해 보고하라.
```

---

# PROMPT 9 — 골드셋 구축 (사람이 라벨할 파일을 만드는 단계)

```text
DATASET_SPEC §6 표에 따라 골드셋 표본을 층화추출하고, 사람이 라벨할 CSV를 생성하라.

- 시드 고정, samplingFrame·samplingSeed 를 qa.goldSample 에 기록
- 각 CSV에는 판정에 필요한 원문(해당 섹션 텍스트)을 함께 넣어 사람이 창을 옮기지 않게 한다
- 이중코딩 구간을 표시하고, 라벨 정의 요약을 CSV 상단 주석과 별도 지침 파일로 제공
- data/gold/ 아래에 저장하고 라벨 컬럼은 비워둔다

절대 하지 말 것: 골드 라벨을 모델이나 규칙으로 미리 채우는 것.
채우면 게이트 측정이 무의미해진다. 빈 칸으로 두고 멈춰라.

산출물: data/gold/*.csv, docs/ssot/ANNOTATION_GUIDE.md
```

---

# PROMPT 10 — 라벨러 + 게이트 측정

```text
core.careerLabel 을 산출하고 골드셋으로 게이트를 측정하라.

10-1. 규칙 라벨러
 - SSOT §5.1 의 CareerClass 조건식을 그대로 구현. 조건 순서를 바꾸지 않는다
 - 지시변수 I,N,R,P,B,Y,C 를 각각 컬럼으로 저장한다. 최종 라벨만 저장하면 감사가 불가능하다
 - internAccessClass 는 인턴 트랙만 산출. restrictedInternFlag 와 experiencedInternFlag 를 분리
 - 포트폴리오 제출 단독으로 experiencedInternFlag=1 이 되지 않아야 한다 (테스트로 고정)
 - 우대조건만으로 제한형 인턴이 되지 않아야 한다 (테스트로 고정)

10-2. LLM 보조 라벨러
 - 규칙이 U 로 떨어진 건과 boundaryResolvedFlag=FALSE 인 건에만 적용
 - 규칙과 불일치하면 ruleLlmDisagreeFlag=TRUE, reviewFlag=TRUE. 자동으로 LLM 편을 들지 않는다
 - labelSource 를 정확히 기록

10-3. 게이트 측정
 - qa.evalRun 에 careerClass, internAccessClass, boundary, postingKind 결과를 기록
 - 게이트: careerClass MacroF1 ≥ 0.85, E0 precision ≥ 0.90, boundary precision ≥ 0.90,
           postingKind precision ≥ 0.95
 - 이중코딩 Cohen κ 를 계산. κ < 0.70 이면 규칙 튜닝을 멈추고 라벨 정의 수정을 제안하라
 - 미달 시 오분류 상위 유형 10개를 원문과 함께 보고하고, 규칙 수정안을 제시한 뒤 멈춰라

금지: 게이트를 맞추려고 골드 라벨을 수정하거나, 어려운 표본을 골드셋에서 제외하는 것.
```

---

# PROMPT 11 — NCS 원천 수집

```text
docs/audit/ncs_sources.md 에 확인된 경로로 ncs 스키마를 채워라.

1. ncs.ncsUnit — 능력단위코드·명칭·수준(1~8)·훈련시간·분류계층.
   ncsBand 는 1~2/3~4/5~6/7~8 로 계산해 함께 저장. 원 수준(ncsLevel)은 절대 삭제하지 않는다
2. ncs.ncsUnitElement — 능력단위요소, 수행준거, KSA(지식·기술·태도), 요소 레벨
3. ncs.ncsLearningModule — 학습·학습내용·과업 문장. localFilePath 로 로컬 참조만 하고
   redistributable=FALSE 고정. 원본 PDF를 레포에 커밋하지 않는다 (저작권 고지 준수)
4. ncs.coreAiItCodeSet — AI·IT 세분류 코드 집합을 확정하고 codeSetVersion 을 박는다
   포함 근거(inclusionBasis)를 각 행에 남긴다
5. 서로 다른 원천의 수준값이 충돌하면 sourceDataset·sourceVersion 별로 모두 남기고
   우선순위를 configs/ncsBands.yaml 에 명시한다. 임의로 하나를 지우지 않는다

수락 기준: ncsLevel 이 전 행에서 1~8 범위, ncsBand 가 ncsLevel 과 항상 정합.
경고: coreAiItCodeSet 은 이후 결과를 보고 수정하지 않는다. 수정하면 RQ1이 순환논리가 된다.
```

---

# PROMPT 12 — NCS 매핑 + 게이트 측정

```text
담당업무·필수요건을 NCS 능력단위에 매핑해 ncs.postingNcsMatch 를 채워라.

매핑 우선순위는 SSOT §7.3 의 6단계를 그대로 따르고 mappingBasis 에 기록한다.
1 ncsUnitDirect → 2 ncsPerformanceCriteria → 3 ncsLearningModule → 4 dictionaryRule
→ 5 semanticMatch → 6 unmapped

규칙:
- 임베딩 매칭은 동일 세분류 후보 안에서만 수행한다. 전역 검색 금지
- 상위 k=5 를 matchRank 와 함께 보존한다. 최고점 하나만 남기지 않는다
- evidenceText 없는 매칭은 만들지 않는다
- 도구명 단독("Python 능숙자")은 매핑하지 않는다. 과업 문맥이 있을 때만 매핑한다
- 근거가 부족하면 unmapped 로 남긴다. 커버리지를 채우려 억지 매핑하지 않는다
- 트랙 단위 집계: ncsLevelMax, ncsLevelMedian, ncsLevelWeightedMedian, ncsBandPrimary,
  mappedDutyCount, ncsMappingCoverage. 주 결과는 신뢰도 가중 중앙값 기반 ncsBandPrimary

게이트: mappingPrecision ≥ 0.85, coverage ≥ 0.80, lowConfidenceShare ≤ 0.20.
미달 시 사전(ncsAliasDictionary) 보강을 우선하고, 임계값을 낮추는 방식은 제안하지 않는다.
결과를 qa.evalRun 에 기록하고, 미달이면 오분류 유형과 함께 멈춰라.
```

---

# PROMPT 13 — 마트 구축

```text
mart.postingAnalysisMart 와 mart.timeSeriesMart 를 구축하라.

postingAnalysisMart: grain 은 trackId. DDL 컬럼 순서·타입을 그대로 지킨다.
 - highDemandScore 는 NULL, scoreStatus='reserved'
 - cohortType 은 coreAiIt 와 allJobs 두 값으로 각각 산출
 - 단일 dataVersion 으로 채운다. 버전이 섞이면 빌드를 실패시켜라

timeSeriesMart:
 - grain: periodMonth × cohortType × jobCodeLevel × jobCode × dedupApplied
 - 분모는 mart.vValidPostingMonthly 뷰만 사용한다. 다른 방식으로 세면 안 된다
 - dedupApplied TRUE/FALSE 두 버전을 모두 산출한다 (민감도)
 - entryPostingRate 와 internPostingRate 의 합이 1이 아닌 것은 정상이다.
   합을 1로 맞추는 보정을 절대 넣지 않는다
 - internRelativeIndex 는 SSOT §15.4 수식 그대로
 - RQ2 지표는 mart.vRq2Eligible 뷰 기준(mixedUnresolved·boundary 미해결 제외)으로 계산
 - coverageStatus 를 monthlyCoverageAudit 에서 조인해 넣고, 2026-08 은 partialMonthFlag=TRUE

검증 쿼리를 tests/integration/ 에 넣어라:
 - 모든 비율이 0~1
 - entryPostingCount ≤ totalValidPostingCount
 - countE0+countE1+countE2+countE3+countU = 비인턴 트랙 수
 - 재실행 시 모든 값이 동일

보고: 월별 분모 시계열, coverage 미달 월 목록, dedup 전후 차이가 가장 큰 월 5개.
```

---

# PROMPT 14 — RQ1·RQ2 분석 + resultManifest

```text
승인된 분석 구간에 대해 RQ1·RQ2를 산출하라. 기사 숫자는 전부 qa.resultManifest 에 등재한다.

RQ1:
 - 월별 entryPostingRate, internPostingRate, 배타적 4비율, internRelativeIndex
 - 2023년 전후 분절 회귀 (SSOT §16). 월 계절성 γ_m, 직무 고정효과 δ_j 포함,
   sourceFixedEffect 는 제거(단일 플랫폼)
 - 표준오차는 HAC 또는 직무 군집. 어느 것을 썼는지 표에 명시
 - 기준점 민감도: 2022-12, 2023-01, 2023-04 세 버전 모두 산출

RQ2:
 - RQ2-A: E0/E1 비중, 제한형 인턴 비중, 필수요건별 비율, minCareerMonths 분포 변화
 - RQ2-B: NCS 밴드 구성비, advancedDutyShare, medianNcsLevel, 직무별 상승폭,
          unmapped 비율의 시점 안정성

필수 처리:
 - coverageStatus='insufficient' 월은 주 추세선에서 제외하고 그림에 음영으로 표시
 - 2026 은 YTD, 1~7월 동기간 비교만. 연간 합계 그래프에서 완결 연도처럼 연결하지 않는다
 - dedup 전/후 두 버전을 T08_sensitivity_dedup.csv 로 대조
 - 모든 수치에 분모 n 을 함께 기록. 분모가 30 미만인 셀은 값을 내지 말고 '-' 로 마스킹

산출물: reports/tables/T01~T08.csv, reports/figures/F01~F08,
        qa.resultManifest 전량 등재(scriptPath, scriptGitSha, inputMartSha256 포함)

서술 규칙: "AI가 신입 채용을 줄였다" 류의 인과 단정을 어떤 형태로도 쓰지 않는다.
결과 해석문 초안을 쓸 때는 관찰된 구조 변화와 대안 설명(플랫폼 구성 변화, 생존편향,
경기 요인)을 함께 제시하라.
```

---

# PROMPT 15 — RQ4 (독립 기술분석)

```text
cohortType='allJobs' 로 제한형 인턴과 높은 NCS 밴드가 어느 직무에 집중되는지 기술하라.

- coreAiIt 결과와 같은 그림·같은 축에 겹쳐 그리지 않는다. 별도 섹션·별도 파일로 분리
- 기사 본문에서 이 결과를 AI·IT 코호트의 일반화 근거로 쓰지 않는다는 주석을 캡션에 넣는다
- 산출물: reports/tables/T09_alljobs_concentration.csv, reports/figures/F09_*
```

---

# PROMPT 16 — RQ3 (보조 유사도, 선택)

```text
RQ1·RQ2가 확정된 뒤에만 실행한다.

- 같은 NCS 세분류 또는 능력단위, 같은 연도 또는 ±1년으로 짝을 만든다
- 회사명·복지·지원절차·보일러플레이트를 제거한 뒤 자격요건과 담당업무를 분리 임베딩
- senioritySimilarityGap = sim(intern, experienced) − sim(intern, entry)
- mart.similarityPair 에 저장, embeddingModel·boilerplateRemoved 기록
- 결과는 AUX 로 명시. 주 결론을 대체하지 않는다
```

---

# PROMPT 17 — 릴리스

```text
RELEASE/p4_release_20260806/ 을 만들어라. 구성은 DATASET_SPEC §7.4 를 그대로 따른다.

- 원문 공고 텍스트·이미지는 포함하지 않는다
- CHECKSUMS.sha256 생성
- REPRODUCE.md: 클린 환경에서 마트를 재생성하는 최소 절차와 필요한 인증키 목록
- qa.vAnalysisReadyGate 결과를 T07_quality_gates.csv 로 첨부하고, 미충족 항목이 있으면
  릴리스를 만들지 말고 미충족 목록만 보고하라
```

---

# 공통 거부 조건 (에이전트가 스스로 멈춰야 하는 상황)

```text
다음 중 하나라도 발생하면 작업을 중단하고 사람에게 보고한다. 우회하지 않는다.

1. HTTP 403, 캡차, 계정 차단, robots.txt Disallow 대상 접근 필요
2. 성공률이 최근 200건에서 90% 미만
3. 게이트 수치 미달 (라벨·매핑·postingKind)
4. coverageStatus='insufficient' 월이 분석 구간의 20% 초과
5. SSOT 문서 간 충돌, 또는 문서에 없는 설계를 추가해야 하는 상황
6. 로그인·유료 접근이 필요한 데이터
7. 개인정보가 마스킹 없이 저장될 위험
8. highDemandScore 를 채워야 결과가 나오는 상황
9. 재실행 멱등성 테스트 실패
10. 기사 숫자가 resultManifest 없이 만들어지는 상황
```
