-- =====================================================================
-- P4 AI 확산과 인턴 채용시장 변화 — Warehouse DDL
-- 대상 엔진: DuckDB 1.x  (파일: data/warehouse/p4.duckdb)
-- 준거 문서: P4_PROJECT_SSOT_v2.md (v2.0.0), USER_REVIEW_DECISIONS.md
-- DDL 버전: v2.0.0 / 기준일: 2026-08-06
--
-- 규칙
--  1) 명명은 SSOT와 동일하게 camelCase. DuckDB는 대소문자를 구분하지 않으나 원형을 보존한다.
--  2) raw 레이어는 파일이 정본이고 이 테이블은 색인이다. 원문 텍스트를 여기에 저장하지 않는다.
--  3) 모든 파생 테이블은 버전 컬럼을 갖는다. 버전 없는 산출물은 마트에 넣지 않는다.
--  4) 모든 시각 컬럼은 KST(Asia/Seoul) 기준 TIMESTAMPTZ.
-- =====================================================================

PRAGMA enable_checkpoint_on_shutdown;
SET TimeZone = 'Asia/Seoul';

CREATE SCHEMA IF NOT EXISTS raw;
CREATE SCHEMA IF NOT EXISTS core;
CREATE SCHEMA IF NOT EXISTS ncs;
CREATE SCHEMA IF NOT EXISTS mart;
CREATE SCHEMA IF NOT EXISTS qa;

-- =====================================================================
-- 0. ENUM 타입
-- =====================================================================

CREATE TYPE sourceTypeEnum AS ENUM ('web', 'api', 'fileDownload');

CREATE TYPE accessModeEnum AS ENUM (
  'httpHtml', 'internalJson', 'renderedDom', 'publicApi', 'fileDownload', 'waybackSnapshot'
);

CREATE TYPE discoveryRouteEnum AS ENUM (
  'calendarIndex',   -- 링커리어 캘린더 목록
  'internalJson',    -- 내부 JSON/GraphQL 목록 응답
  'idEnumeration',   -- /activity/{id} 순차 열거 (과거분 백필)
  'waybackCdx',      -- web.archive.org CDX
  'sitemap',
  'manualSeed'
);

CREATE TYPE frontierStateEnum AS ENUM ('NEW','FETCHING','FETCHED','PARSED','DEAD','SKIPPED');

CREATE TYPE entityTypeEnum AS ENUM ('index','detail','asset','ncsFile');

CREATE TYPE runStatusEnum AS ENUM ('running','completed','aborted','failed');

-- 공고의 성격. 링커리어 캘린더에는 공모전·대외활동·교육과정·동아리가 섞여 있으므로
-- recruit* 이외의 값은 절대 RQ1 분모에 들어가지 않는다. (SSOT §9.1 주의사항의 구현)
CREATE TYPE postingKindEnum AS ENUM (
  'recruitIntern',
  'recruitNewGrad',
  'recruitExperienced',
  'recruitUnknown',
  'contest',          -- 공모전
  'extracurricular',  -- 대외활동
  'education',        -- 교육과정·부트캠프
  'club',
  'volunteer',
  'other'
);

CREATE TYPE recruitmentScopeEnum AS ENUM (
  'entryOnly','internOnly','experiencedOnly',
  'entryInternMixed','entryExperiencedMixed','internExperiencedMixed',
  'allMixed','mixedUnresolved','unknown'
);

CREATE TYPE trackTypeEnum AS ENUM ('entry','intern','experienced','mixedUnresolved');

CREATE TYPE sectionTypeEnum AS ENUM (
  'title','duties','required','preferred','qualification',
  'process','condition','benefit','company','etc'
);

CREATE TYPE blockSourceEnum AS ENUM ('html','ocr','merged');

CREATE TYPE careerClassEnum AS ENUM ('E0','E1','E2','E3','U');

CREATE TYPE internAccessClassEnum AS ENUM ('I0','I1','IU');

CREATE TYPE obligationEnum AS ENUM ('required','preferred','unknown');

CREATE TYPE requirementTypeEnum AS ENUM (
  'careerMonths','priorExperience','portfolio','project','certificate',
  'degree','major','skill','tool','language','duty','other'
);

CREATE TYPE certificateClassEnum AS ENUM (
  'craftsman','industrialEngineer','engineer','masterCraftsman',
  'professionalEngineer','otherNational'
);

CREATE TYPE degreeLevelEnum AS ENUM ('highSchool','associate','bachelor','master','doctor');

CREATE TYPE ncsBandEnum AS ENUM ('level1to2','level3to4','level5to6','level7to8');

CREATE TYPE mappingBasisEnum AS ENUM (
  'ncsUnitDirect',            -- 1순위
  'ncsPerformanceCriteria',   -- 2순위
  'ncsLearningModule',        -- 3순위
  'dictionaryRule',           -- 4순위
  'semanticMatch',            -- 5순위
  'unmapped'                  -- 6순위
);

CREATE TYPE confidenceTierEnum AS ENUM ('high','medium','low');

CREATE TYPE labelSourceEnum AS ENUM ('rule','llm','ruleLlmAgreed','human','humanAdjudicated');

CREATE TYPE cohortTypeEnum AS ENUM ('coreAiIt','allJobs');

CREATE TYPE coverageStatusEnum AS ENUM ('complete','partial','insufficient','excluded');

CREATE TYPE postedAtSourceEnum AS ENUM (
  'explicitDetail','explicitIndex','inferredIdInterpolation','inferredWayback','unknown'
);

CREATE TYPE dedupDecisionEnum AS ENUM ('sameGroup','distinct','undecided');

CREATE TYPE evalTargetEnum AS ENUM ('careerClass','internAccessClass','boundary','ncsMapping','postingKind','trackSplit');

-- =====================================================================
-- 1. 수집 통제 (raw)
-- =====================================================================

CREATE TABLE raw.sourceRegistry (
  sourceName        VARCHAR PRIMARY KEY,          -- 'linkareer' | 'ncsFile' | 'ncsApi'
  sourceType        sourceTypeEnum NOT NULL,
  baseUrl           VARCHAR,
  accessMode        accessModeEnum NOT NULL,
  robotsCheckedAt   TIMESTAMPTZ,
  robotsAllowed     BOOLEAN,
  robotsSnapshotSha VARCHAR,                      -- robots.txt 원문 해시 (변경 감지)
  termsReviewedAt   TIMESTAMPTZ,
  termsNote         VARCHAR,
  rateLimitRps      DOUBLE NOT NULL DEFAULT 1.0,
  maxConcurrency    SMALLINT NOT NULL DEFAULT 2,
  licenseNote       VARCHAR,                      -- 예: NCS 학습모듈은 재배포 금지, 로컬 참조만
  registeredAt      TIMESTAMPTZ NOT NULL
);

CREATE TABLE raw.crawlRun (
  crawlRunId       VARCHAR PRIMARY KEY,           -- ULID
  sourceName       VARCHAR NOT NULL REFERENCES raw.sourceRegistry(sourceName),
  runPhase         VARCHAR NOT NULL,              -- 'P0_audit'|'index'|'detail'|'asset'|'ncs'
  collectorVersion VARCHAR NOT NULL,
  configSha256     VARCHAR NOT NULL,              -- configs/*.yaml 해시. 설정 변경 추적
  targetScopeJson  VARCHAR,                       -- 대상 기간·id 구간 등
  startedAt        TIMESTAMPTZ NOT NULL,
  endedAt          TIMESTAMPTZ,
  requestCount     INTEGER DEFAULT 0,
  successCount     INTEGER DEFAULT 0,
  failCount        INTEGER DEFAULT 0,
  status           runStatusEnum NOT NULL,
  abortReason      VARCHAR,                       -- 403 발생 등 즉시 중단 사유
  gitCommitSha     VARCHAR
);

-- APQ(Persisted Query) 해시는 프런트엔드 배포로 바뀔 수 있어 코드에 하드코딩하지 않는다.
-- 수집기는 이 레지스트리에서 sha256Hash를 조회해서 쓴다. (RECON_20260806_01 근거, docs/audit/P0_RECON_REPORT_FINAL.md §6)
CREATE TABLE raw.queryRegistry (
  operationName         VARCHAR NOT NULL,
  sha256Hash            VARCHAR NOT NULL,
  transportType         VARCHAR NOT NULL,             -- 'apq_get'|'graphql_post'
  httpMethod            VARCHAR NOT NULL,
  frontendBuildId       VARCHAR,                       -- __NEXT_DATA__.buildId 관측값
  discoveredAt          TIMESTAMPTZ NOT NULL,
  lastVerifiedAt        TIMESTAMPTZ,
  responseSchemaVersion VARCHAR,
  activeFlag            BOOLEAN NOT NULL DEFAULT TRUE,
  verificationStatus    VARCHAR NOT NULL DEFAULT 'unverified',  -- 'verified'|'stale'|'broken'|'unverified'
  PRIMARY KEY (operationName, sha256Hash)
);

-- 재시작 가능성의 핵심. SSOT v2에 없던 테이블이며 필수다.
CREATE TABLE raw.crawlFrontier (
  url             VARCHAR PRIMARY KEY,
  sourceName      VARCHAR NOT NULL,
  entityType      entityTypeEnum NOT NULL,
  discoveryRoute  discoveryRouteEnum NOT NULL,
  sourcePostingId VARCHAR,
  state           frontierStateEnum NOT NULL DEFAULT 'NEW',
  attempts        SMALLINT NOT NULL DEFAULT 0,
  httpStatus      INTEGER,
  contentSha256   VARCHAR,
  lastError       VARCHAR,
  priority        SMALLINT DEFAULT 100,
  discoveredAt    TIMESTAMPTZ NOT NULL,
  fetchedAt       TIMESTAMPTZ,
  crawlRunId      VARCHAR
);
CREATE INDEX idxFrontierState ON raw.crawlFrontier(state, priority);

-- =====================================================================
-- 2. 원천 색인 (raw). 원문 본체는 data/raw/** 파일이 정본.
-- =====================================================================

CREATE TABLE raw.linkareerIndexRaw (
  indexRowId        VARCHAR PRIMARY KEY,          -- sha1(crawlRunId|sourceUrl|rowOrdinal)[:16]
  crawlRunId        VARCHAR NOT NULL REFERENCES raw.crawlRun(crawlRunId),
  sourceUrl         VARCHAR NOT NULL,
  discoveryRoute    discoveryRouteEnum NOT NULL,
  listCursor        VARCHAR,                      -- page/offset/cursor 원문
  rowOrdinal        INTEGER NOT NULL,
  fetchedAt         TIMESTAMPTZ NOT NULL,
  httpStatus        INTEGER NOT NULL,
  contentType       VARCHAR,
  rawPath           VARCHAR NOT NULL,
  rawSha256         VARCHAR NOT NULL,
  collectorVersion  VARCHAR NOT NULL,
  sourcePostingId   VARCHAR,                      -- 링커리어 activity id
  detailUrl         VARCHAR,
  indexTitleRaw     VARCHAR,
  indexCategoryRaw  VARCHAR,                      -- activityType/tab 원문. 라벨로 쓰지 않는다
  indexCompanyRaw   VARCHAR,
  indexPostedAtRaw  VARCHAR,
  indexDeadlineRaw  VARCHAR
);

CREATE TABLE raw.linkareerPostingRaw (
  rawPostingId      VARCHAR PRIMARY KEY,          -- sha1(sourceName|sourcePostingId|rawSha256)[:20]
  sourceName        VARCHAR NOT NULL DEFAULT 'linkareer',
  sourcePostingId   VARCHAR NOT NULL,
  sourceUrl         VARCHAR NOT NULL,
  crawlRunId        VARCHAR NOT NULL REFERENCES raw.crawlRun(crawlRunId),
  captureMode       accessModeEnum NOT NULL,
  snapshotTimestamp VARCHAR,                      -- wayback 14자리. 그 외 NULL
  fetchedAt         TIMESTAMPTZ NOT NULL,
  httpStatus        INTEGER NOT NULL,
  contentType       VARCHAR,
  rawPath           VARCHAR NOT NULL,
  rawSha256         VARCHAR NOT NULL,
  collectorVersion  VARCHAR NOT NULL,
  isAlive           BOOLEAN NOT NULL,             -- 200이며 본문 존재
  bodyTextLength    INTEGER,
  imageCount        SMALLINT,
  UNIQUE (sourceName, sourcePostingId, rawSha256)
);
CREATE INDEX idxRawPostingSrcId ON raw.linkareerPostingRaw(sourcePostingId);

CREATE TABLE raw.postingAsset (
  assetId       VARCHAR PRIMARY KEY,              -- sha1(assetSha256)[:20]
  rawPostingId  VARCHAR NOT NULL REFERENCES raw.linkareerPostingRaw(rawPostingId),
  sourcePostingId VARCHAR NOT NULL,
  assetType     VARCHAR NOT NULL,                 -- 'image'|'pdf'|'attachment'
  assetUrl      VARCHAR NOT NULL,
  assetOrdinal  SMALLINT NOT NULL,
  rawPath       VARCHAR NOT NULL,
  assetSha256   VARCHAR NOT NULL,                 -- 동일 포스터 재게시 캐시 키
  widthPx       INTEGER,
  heightPx      INTEGER,
  bytes         BIGINT,
  fetchedAt     TIMESTAMPTZ NOT NULL,
  crawlRunId    VARCHAR NOT NULL
);
CREATE INDEX idxAssetSha ON raw.postingAsset(assetSha256);

CREATE TABLE raw.ocrResult (
  ocrId          VARCHAR PRIMARY KEY,             -- sha1(assetSha256|ocrEngine|ocrModel|ocrVersion)[:20]
  assetId        VARCHAR NOT NULL REFERENCES raw.postingAsset(assetId),
  assetSha256    VARCHAR NOT NULL,
  ocrEngine      VARCHAR NOT NULL,                -- 'visionLlm'|'clovaOcr'|'upstage'|'paddleOcr'
  ocrModel       VARCHAR NOT NULL,
  ocrVersion     VARCHAR NOT NULL,
  ocrText        VARCHAR,                         -- 전체 텍스트
  ocrBlocksJson  VARCHAR,                         -- 줄·블록 좌표 보존 (섹션 복원용)
  ocrStructJson  VARCHAR,                         -- 스키마 직접 추출 결과 (duties/required/...)
  ocrConfidence  DOUBLE,
  ocrReviewFlag  BOOLEAN NOT NULL DEFAULT FALSE,  -- 사람 검수 필요
  ocrCostUsd     DOUBLE,
  producedAt     TIMESTAMPTZ NOT NULL,
  UNIQUE (assetSha256, ocrEngine, ocrModel, ocrVersion)
);

-- =====================================================================
-- 3. 정규화·라벨 (core)
-- =====================================================================

CREATE TABLE core.postingNormalized (
  postingId          VARCHAR PRIMARY KEY,         -- 'lk_' || sha1(sourceName|sourcePostingId)[:16]
  sourceName         VARCHAR NOT NULL,
  sourcePostingId    VARCHAR NOT NULL,
  sourceUrl          VARCHAR NOT NULL,
  rawPostingId       VARCHAR NOT NULL REFERENCES raw.linkareerPostingRaw(rawPostingId),

  postingKind        postingKindEnum NOT NULL,
  postingKindBasis   VARCHAR,                     -- 판정 근거 텍스트
  recruitmentScope   recruitmentScopeEnum NOT NULL,

  companyKey         VARCHAR,                     -- 정규화 상호 기반 안정 키
  companyNameRaw     VARCHAR,
  companyNameNorm    VARCHAR,
  companySizeRaw     VARCHAR,
  industryNameRaw    VARCHAR,
  jobTitleRaw        VARCHAR,

  postedAt           TIMESTAMPTZ,
  postedAtSource     postedAtSourceEnum NOT NULL,
  postedAtConfidence DOUBLE,
  deadlineAt         TIMESTAMPTZ,

  employmentTypeRaw  VARCHAR,
  careerRequirementRaw VARCHAR,
  educationRaw       VARCHAR,
  locationRaw        VARCHAR,

  bodyText           VARCHAR,                     -- html+ocr 병합 결과
  bodySource         blockSourceEnum NOT NULL,
  bodyTextLength     INTEGER,
  hasImageOnlyBody   BOOLEAN NOT NULL DEFAULT FALSE,

  -- 분모 자격. 아래 4조건 모두 참일 때만 1.
  --  (a) postingKind IN ('recruitIntern','recruitNewGrad','recruitExperienced','recruitUnknown')
  --  (b) postedAt IS NOT NULL AND postedAtSource <> 'unknown'
  --  (c) bodyTextLength >= 120  (파싱 실패·빈 본문 배제)
  --  (d) canonicalRecordFlag = 1 (90일 재게시 그룹의 대표행)
  validPosting       BOOLEAN NOT NULL,
  invalidReason      VARCHAR,

  -- 분모 4분리 (RECON_20260806_01 근거: 표본 35건 중 35건이 외부 ATS 링크만 갖고
  -- 자체 자격요건 원문이 없음. validPosting 하나로 묶으면 RQ1 분모까지 텍스트 보존
  -- 여부에 종속되어 왜곡된다. docs/audit/P0_RECON_REPORT_FINAL.md §6 참조)
  postingEligibleFlag BOOLEAN NOT NULL,            -- 채용공고 확인 + 게시일 존재 + 기본 메타데이터 존재
  rq1EligibleFlag     BOOLEAN NOT NULL,             -- postingEligibleFlag + 채용형태 판정가능 + canonical 여부 결정됨
  rq2EligibleFlag     BOOLEAN NOT NULL,             -- postingEligibleFlag + 필수/우대 경계 판정가능한 원문 존재 + 트랙 분리 가능
  ncsEligibleFlag     BOOLEAN NOT NULL,             -- postingEligibleFlag + 담당업무 문장 존재 + NCS 매핑 가능한 최소 텍스트

  externalApplyUrl        VARCHAR,                  -- applyDetail이 링커리어 외부인 경우 원문 URL 보존(따라가 수집하지 않음)
  externalAtsDomain       VARCHAR,                   -- 예: 'saramin.co.kr', 'jobkorea.co.kr'
  externalDetailOnlyFlag  BOOLEAN NOT NULL DEFAULT FALSE, -- 지원 절차가 전적으로 외부에서만 진행되는지
  linkareerBodyAvailableFlag BOOLEAN NOT NULL DEFAULT FALSE, -- ActivityText 등 링커리어 자체 본문 존재 여부
  rq2ExclusionReason      VARCHAR,                  -- 예: 'externalAtsBodyUnavailable'. rq2EligibleFlag=FALSE일 때만 채움

  duplicateGroupId   VARCHAR,
  canonicalPostingId VARCHAR,
  canonicalPostedAt  TIMESTAMPTZ,
  canonicalRecordFlag BOOLEAN NOT NULL DEFAULT TRUE,
  repostCount        SMALLINT NOT NULL DEFAULT 0,

  personalDataMasked BOOLEAN NOT NULL DEFAULT TRUE, -- 담당자 연락처 마스킹 완료
  rawSha256          VARCHAR NOT NULL,
  parseVersion       VARCHAR NOT NULL,
  dataVersion        VARCHAR NOT NULL,
  normalizedAt       TIMESTAMPTZ NOT NULL,
  UNIQUE (sourceName, sourcePostingId)
);
CREATE INDEX idxPostingMonth ON core.postingNormalized(canonicalPostedAt);
CREATE INDEX idxPostingValid ON core.postingNormalized(validPosting, postingKind);

CREATE TABLE core.postingTrack (
  trackId        VARCHAR PRIMARY KEY,             -- postingId || '#t' || lpad(trackIndex,2,'0')
  postingId      VARCHAR NOT NULL REFERENCES core.postingNormalized(postingId),
  trackIndex     SMALLINT NOT NULL,
  trackType      trackTypeEnum NOT NULL,
  trackTitleRaw  VARCHAR,
  trackJobTitleRaw VARCHAR,
  splitBasis     VARCHAR NOT NULL,                -- 'sectionHeader'|'table'|'llmSegment'|'wholeBody'
  splitConfidence DOUBLE,
  mixedResolvedFlag BOOLEAN NOT NULL,             -- FALSE면 RQ2 분석에서 제외
  charSpanStart  INTEGER,
  charSpanEnd    INTEGER,
  trackVersion   VARCHAR NOT NULL,
  UNIQUE (postingId, trackIndex)
);

CREATE TABLE core.postingSection (
  sectionId    VARCHAR PRIMARY KEY,               -- trackId || '#s' || lpad(sectionOrder,2,'0')
  trackId      VARCHAR NOT NULL REFERENCES core.postingTrack(trackId),
  postingId    VARCHAR NOT NULL,
  sectionType  sectionTypeEnum NOT NULL,
  sectionOrder SMALLINT NOT NULL,
  headerTextRaw VARCHAR,
  sectionText  VARCHAR NOT NULL,
  blockSource  blockSourceEnum NOT NULL,
  charLength   INTEGER NOT NULL,
  parseVersion VARCHAR NOT NULL
);
CREATE INDEX idxSectionTrackType ON core.postingSection(trackId, sectionType);

CREATE TABLE core.requirementFact (
  requirementId   VARCHAR PRIMARY KEY,            -- sha1(sectionId|requirementType|normalizedEvidence)[:20]
  sectionId       VARCHAR NOT NULL REFERENCES core.postingSection(sectionId),
  trackId         VARCHAR NOT NULL,
  postingId       VARCHAR NOT NULL,
  requirementType requirementTypeEnum NOT NULL,
  obligation      obligationEnum NOT NULL,        -- 필수·우대 경계. 주 결과는 required만 사용
  valueNum        DOUBLE,                         -- 예: 경력 개월 수
  valueUnit       VARCHAR,                        -- 'month'|'year'|'count'
  valueText       VARCHAR,                        -- 예: '정보처리기사'
  certificateNameRaw VARCHAR,
  certificateClass certificateClassEnum,          -- 정규식 미매칭 시 NULL. 추정 금지
  degreeLevel     degreeLevelEnum,
  evidenceText    VARCHAR NOT NULL,               -- 원문 근거. 비워둘 수 없다
  extractorRule   VARCHAR NOT NULL,
  extractorVersion VARCHAR NOT NULL,
  confidence      DOUBLE,
  reviewFlag      BOOLEAN NOT NULL DEFAULT FALSE
);
CREATE INDEX idxReqTrackType ON core.requirementFact(trackId, requirementType, obligation);

CREATE TABLE core.careerLabel (
  trackId               VARCHAR PRIMARY KEY REFERENCES core.postingTrack(trackId),
  postingId             VARCHAR NOT NULL,

  -- 판정 지시변수 (SSOT §5.1 기호)
  internFlagI           BOOLEAN NOT NULL,         -- I_j
  entryMarkFlagN        BOOLEAN NOT NULL,         -- N_j
  requiredCareerFlagR   BOOLEAN NOT NULL,         -- R_j
  priorExperienceFlagP  BOOLEAN NOT NULL,         -- P_j
  boundaryResolvedFlagB BOOLEAN NOT NULL,         -- B_j
  minCareerYearsY       DOUBLE,                   -- Y_j
  explicitCareerFlagC   BOOLEAN NOT NULL,         -- C_j

  careerClass           careerClassEnum NOT NULL,
  internAccessClass     internAccessClassEnum,    -- 비인턴 트랙은 NULL

  nominalEntryFlag      BOOLEAN NOT NULL,         -- E0 + E1
  openEntryFlag         BOOLEAN NOT NULL,
  restrictedEntryFlag   BOOLEAN NOT NULL,
  openInternFlag        BOOLEAN NOT NULL,
  restrictedInternFlag  BOOLEAN NOT NULL,         -- 필수경력 또는 필수 사전경험
  experiencedInternFlag BOOLEAN NOT NULL,         -- 엄격 정의. 포트폴리오 단독은 0

  labelSource           labelSourceEnum NOT NULL,
  labelConfidence       DOUBLE,
  ruleLlmDisagreeFlag   BOOLEAN NOT NULL DEFAULT FALSE,
  reviewFlag            BOOLEAN NOT NULL DEFAULT FALSE,
  labelVersion          VARCHAR NOT NULL,
  labeledAt             TIMESTAMPTZ NOT NULL
);

CREATE TABLE core.postingDedupEdge (
  edgeId         VARCHAR PRIMARY KEY,
  leftPostingId  VARCHAR NOT NULL,
  rightPostingId VARCHAR NOT NULL,
  companyKey     VARCHAR,
  dayDiff        INTEGER NOT NULL,                -- <= 90 만 후보
  titleSim       DOUBLE,
  bodySim        DOUBLE,
  simhashDistance SMALLINT,
  jobCodeMatch   BOOLEAN,
  decision       dedupDecisionEnum NOT NULL,
  decisionBasis  VARCHAR,
  dedupVersion   VARCHAR NOT NULL,
  UNIQUE (leftPostingId, rightPostingId, dedupVersion)
);

-- =====================================================================
-- 4. NCS 앵커 (ncs)
-- =====================================================================

CREATE TABLE ncs.ncsUnit (
  ncsUnitCode    VARCHAR PRIMARY KEY,             -- 분류번호(능력단위코드)
  ncsUnitName    VARCHAR NOT NULL,
  ncsLevel       SMALLINT NOT NULL CHECK (ncsLevel BETWEEN 1 AND 8),
  ncsBand        ncsBandEnum NOT NULL,            -- 1~2 / 3~4 / 5~6 / 7~8
  majorCode      VARCHAR, majorName  VARCHAR,
  middleCode     VARCHAR, middleName VARCHAR,
  minorCode      VARCHAR, minorName  VARCHAR,
  subCode        VARCHAR, subName    VARCHAR,     -- 세분류
  unitDefinition VARCHAR,
  trainingHours  DOUBLE,
  developYear    SMALLINT,
  revisionYear   SMALLINT,
  sourceDataset  VARCHAR NOT NULL,                -- 예: 'dataGoKr:국가직무능력표준정보'
  sourceVersion  VARCHAR NOT NULL,
  ingestedAt     TIMESTAMPTZ NOT NULL
);
CREATE INDEX idxNcsSub ON ncs.ncsUnit(subCode);

CREATE TABLE ncs.ncsUnitElement (
  elementId        VARCHAR PRIMARY KEY,
  ncsUnitCode      VARCHAR NOT NULL REFERENCES ncs.ncsUnit(ncsUnitCode),
  elementNo        VARCHAR,
  elementName      VARCHAR,
  elementDesc      VARCHAR,                       -- 능력단위요소 설명
  performanceCriteria VARCHAR,                    -- 수행준거
  ksaType          VARCHAR,                       -- 'knowledge'|'skill'|'attitude'
  ksaName          VARCHAR,
  ksaDesc          VARCHAR,
  elementLevel     SMALLINT,
  sourceDataset    VARCHAR NOT NULL,
  ingestedAt       TIMESTAMPTZ NOT NULL
);

CREATE TABLE ncs.ncsLearningModule (
  moduleId       VARCHAR PRIMARY KEY,
  ncsUnitCode    VARCHAR NOT NULL REFERENCES ncs.ncsUnit(ncsUnitCode),
  moduleName     VARCHAR NOT NULL,
  learningName   VARCHAR,                         -- 학습(대단원)
  learningUnitName VARCHAR,                       -- 학습내용(중단원)
  taskText       VARCHAR,                         -- 과업 문장. 매핑 근거로 사용
  trainingHours  DOUBLE,
  localFilePath  VARCHAR,                         -- 재배포 금지. 로컬 참조 전용
  redistributable BOOLEAN NOT NULL DEFAULT FALSE,
  sourceDataset  VARCHAR NOT NULL,
  ingestedAt     TIMESTAMPTZ NOT NULL
);

CREATE TABLE ncs.ncsAliasDictionary (
  aliasId      VARCHAR PRIMARY KEY,
  alias        VARCHAR NOT NULL,
  aliasType    VARCHAR NOT NULL,                  -- 'dutyPhrase'|'term'|'tool'|'jobTitle'
  ncsUnitCode  VARCHAR REFERENCES ncs.ncsUnit(ncsUnitCode),
  subCode      VARCHAR,
  -- 도구명 단독은 수준을 부여하지 않는다 (SSOT §6.2). aliasType='tool'은 levelBearing=FALSE.
  levelBearing BOOLEAN NOT NULL,
  weight       DOUBLE NOT NULL DEFAULT 1.0,
  addedBy      VARCHAR NOT NULL,
  addedAt      TIMESTAMPTZ NOT NULL,
  dictVersion  VARCHAR NOT NULL,
  UNIQUE (alias, aliasType, dictVersion)
);

CREATE TABLE ncs.coreAiItCodeSet (
  subCode      VARCHAR PRIMARY KEY,
  subName      VARCHAR NOT NULL,
  majorName    VARCHAR,
  inclusionBasis VARCHAR NOT NULL,                -- 사전등록 근거. 사후 변경 금지
  registeredAt TIMESTAMPTZ NOT NULL,
  codeSetVersion VARCHAR NOT NULL
);

CREATE TABLE ncs.postingNcsMatch (
  matchId         VARCHAR PRIMARY KEY,            -- sha1(trackId|ncsUnitCode|mappingBasis|evidenceHash)[:20]
  postingId       VARCHAR NOT NULL,
  trackId         VARCHAR NOT NULL REFERENCES core.postingTrack(trackId),
  sectionId       VARCHAR,
  requirementId   VARCHAR,
  matchTargetType VARCHAR NOT NULL,               -- 'duty'|'requirement'
  ncsUnitCode     VARCHAR NOT NULL REFERENCES ncs.ncsUnit(ncsUnitCode),
  ncsLevel        SMALLINT NOT NULL,
  ncsBand         ncsBandEnum NOT NULL,
  mappingBasis    mappingBasisEnum NOT NULL,
  matchScore      DOUBLE,
  matchRank       SMALLINT NOT NULL,              -- 상위 k 보존
  confidenceTier  confidenceTierEnum NOT NULL,
  evidenceText    VARCHAR NOT NULL,
  mappingVersion  VARCHAR NOT NULL,
  matchedAt       TIMESTAMPTZ NOT NULL
);
CREATE INDEX idxMatchTrack ON ncs.postingNcsMatch(trackId, matchRank);

-- =====================================================================
-- 5. 마트 (mart)
-- =====================================================================

-- grain: trackId 1행. 공고 수는 항상 distinct canonicalPostingId로 센다.
CREATE TABLE mart.postingAnalysisMart (
  trackId              VARCHAR PRIMARY KEY,
  postingId            VARCHAR NOT NULL,
  canonicalPostingId   VARCHAR NOT NULL,
  canonicalPostedAt    TIMESTAMPTZ NOT NULL,
  periodMonth          DATE NOT NULL,             -- 해당 월 1일
  year                 SMALLINT NOT NULL,
  month                SMALLINT NOT NULL,
  quarter              SMALLINT NOT NULL,
  asOfDate             DATE NOT NULL,

  sourceName           VARCHAR NOT NULL,
  sourceUrl            VARCHAR NOT NULL,
  companyKey           VARCHAR,
  companyName          VARCHAR,
  industryName         VARCHAR,
  jobTitle             VARCHAR,

  cohortType           cohortTypeEnum NOT NULL,
  coreAiItFlag         BOOLEAN NOT NULL,
  ncsMajorCode         VARCHAR,
  ncsMiddleCode        VARCHAR,
  ncsMinorCode         VARCHAR,
  ncsSubCode           VARCHAR,

  postingKind          postingKindEnum NOT NULL,
  validPosting         BOOLEAN NOT NULL,
  postingEligibleFlag  BOOLEAN NOT NULL,
  rq1EligibleFlag      BOOLEAN NOT NULL,
  rq2EligibleFlag      BOOLEAN NOT NULL,
  ncsEligibleFlag      BOOLEAN NOT NULL,
  externalApplyUrl        VARCHAR,
  externalAtsDomain       VARCHAR,
  externalDetailOnlyFlag  BOOLEAN NOT NULL DEFAULT FALSE,
  linkareerBodyAvailableFlag BOOLEAN NOT NULL DEFAULT FALSE,
  rq2ExclusionReason      VARCHAR,
  trackType            trackTypeEnum NOT NULL,
  recruitmentScope     recruitmentScopeEnum NOT NULL,
  hasEntryFlag         BOOLEAN NOT NULL,
  hasInternFlag        BOOLEAN NOT NULL,
  hasExperiencedFlag   BOOLEAN NOT NULL,
  mixedResolvedFlag    BOOLEAN NOT NULL,

  careerClass          careerClassEnum NOT NULL,
  internAccessClass    internAccessClassEnum,
  nominalEntryFlag     BOOLEAN NOT NULL,
  openEntryFlag        BOOLEAN NOT NULL,
  restrictedEntryFlag  BOOLEAN NOT NULL,
  openInternFlag       BOOLEAN NOT NULL,
  restrictedInternFlag BOOLEAN NOT NULL,
  experiencedInternFlag BOOLEAN NOT NULL,
  boundaryResolvedFlag BOOLEAN NOT NULL,

  minCareerMonths      SMALLINT,
  requiredExperienceFlag BOOLEAN NOT NULL,
  requiredPriorExperienceFlag BOOLEAN NOT NULL,
  requiredPortfolioFlag BOOLEAN NOT NULL,
  preferredPortfolioFlag BOOLEAN NOT NULL,
  requiredProjectFlag  BOOLEAN NOT NULL,
  requiredCertificateFlag BOOLEAN NOT NULL,
  certificateClass     certificateClassEnum,
  requiredDegreeLevel  degreeLevelEnum,
  requiredSkillCount   SMALLINT NOT NULL DEFAULT 0,
  requiredToolCount    SMALLINT NOT NULL DEFAULT 0,

  ncsLevelMax          SMALLINT,
  ncsLevelMedian       DOUBLE,
  ncsLevelWeightedMedian DOUBLE,
  ncsBandPrimary       ncsBandEnum,
  mappedDutyCount      SMALLINT NOT NULL DEFAULT 0,
  ncsMappingCoverage   DOUBLE,
  ncsMatchConfidence   DOUBLE,

  highDemandScore      FLOAT,                     -- 예약. 항상 NULL
  scoreStatus          VARCHAR NOT NULL DEFAULT 'reserved',

  duplicateGroupId     VARCHAR,
  repostCount          SMALLINT NOT NULL DEFAULT 0,
  canonicalRecordFlag  BOOLEAN NOT NULL,

  rawSha256            VARCHAR NOT NULL,
  parseVersion         VARCHAR NOT NULL,
  labelVersion         VARCHAR NOT NULL,
  ncsMapVersion        VARCHAR NOT NULL,
  dataVersion          VARCHAR NOT NULL,
  builtAt              TIMESTAMPTZ NOT NULL,
  CHECK (highDemandScore IS NULL)                 -- 산식 확정 전 사용 차단
);
CREATE INDEX idxMartPeriod ON mart.postingAnalysisMart(periodMonth, cohortType);

-- grain: periodMonth × cohortType × jobCodeLevel × jobCode
CREATE TABLE mart.timeSeriesMart (
  periodMonth              DATE NOT NULL,
  cohortType               cohortTypeEnum NOT NULL,
  jobCodeLevel             VARCHAR NOT NULL,      -- 'all'|'major'|'middle'|'sub'
  jobCode                  VARCHAR NOT NULL,      -- 'ALL' 또는 NCS 코드
  dedupApplied             BOOLEAN NOT NULL,      -- 민감도용 이중 산출

  totalValidPostingCount   INTEGER NOT NULL,
  entryPostingCount        INTEGER NOT NULL,
  internPostingCount       INTEGER NOT NULL,
  experiencedPostingCount  INTEGER NOT NULL,
  mixedPostingCount        INTEGER NOT NULL,
  mixedUnresolvedCount     INTEGER NOT NULL,

  entryPostingRate         DOUBLE,
  internPostingRate        DOUBLE,
  entryOnlyRate            DOUBLE,
  internOnlyRate           DOUBLE,
  experiencedOnlyRate      DOUBLE,
  mixedRate                DOUBLE,
  internRelativeIndex      DOUBLE,

  countE0 INTEGER, countE1 INTEGER, countE2 INTEGER, countE3 INTEGER, countU INTEGER,
  openEntryShare           DOUBLE,
  restrictedEntryShare     DOUBLE,
  countI0 INTEGER, countI1 INTEGER, countIU INTEGER,
  restrictedInternShare    DOUBLE,
  experiencedInternShare   DOUBLE,
  mappedInternCount        INTEGER,

  requiredCareerShare      DOUBLE,
  requiredPriorExperienceShare DOUBLE,
  portfolioRequiredShare   DOUBLE,
  projectRequiredShare     DOUBLE,
  certificateRequiredShare DOUBLE,
  medianMinCareerMonths    DOUBLE,

  level1to2Share           DOUBLE,
  level3to4Share           DOUBLE,
  level5to6Share           DOUBLE,
  level7to8Share           DOUBLE,
  advancedDutyShare        DOUBLE,
  medianNcsLevel           DOUBLE,
  ncsMappingCoverage       DOUBLE,

  coverageStatus           coverageStatusEnum NOT NULL,
  partialMonthFlag         BOOLEAN NOT NULL,      -- 2026-08 등
  asOfDate                 DATE NOT NULL,
  dataVersion              VARCHAR NOT NULL,
  builtAt                  TIMESTAMPTZ NOT NULL,
  PRIMARY KEY (periodMonth, cohortType, jobCodeLevel, jobCode, dedupApplied)
);

CREATE TABLE mart.caseStudyRegistry (
  caseId          VARCHAR PRIMARY KEY,
  postingId       VARCHAR NOT NULL,
  trackId         VARCHAR,
  companyName     VARCHAR,
  selectionReason VARCHAR NOT NULL,
  selectionMetric VARCHAR,                        -- 어떤 RQ1/RQ2 지표에서 선별됐는지
  evidenceQuote   VARCHAR,                        -- 짧은 인용만. 전문 전재 금지
  manualNote      VARCHAR,
  reviewedBy      VARCHAR NOT NULL,
  reviewedAt      TIMESTAMPTZ NOT NULL
);

CREATE TABLE mart.similarityPair (
  pairId            VARCHAR PRIMARY KEY,
  internTrackId     VARCHAR NOT NULL,
  comparisonTrackId VARCHAR NOT NULL,
  comparisonType    VARCHAR NOT NULL,             -- 'entry'|'experienced'
  ncsSubCode        VARCHAR,
  yearGap           SMALLINT,
  qualificationSimilarity DOUBLE,
  dutySimilarity    DOUBLE,
  embeddingModel    VARCHAR NOT NULL,
  boilerplateRemoved BOOLEAN NOT NULL,
  auxVersion        VARCHAR NOT NULL
);

-- =====================================================================
-- 6. 품질·감사 (qa) — ANALYSIS_READY 게이트의 근거 테이블
-- =====================================================================

-- SSOT의 '월별 Linkareer coverage status 확정'을 담는 테이블
CREATE TABLE qa.monthlyCoverageAudit (
  periodMonth        DATE NOT NULL,
  sourceName         VARCHAR NOT NULL,
  discoveredCount    INTEGER NOT NULL,            -- 발견된 후보 URL
  fetchedCount       INTEGER NOT NULL,
  aliveCount         INTEGER NOT NULL,            -- 200 + 본문 존재
  deadCount          INTEGER NOT NULL,            -- 404/410/삭제
  parsedCount        INTEGER NOT NULL,
  validPostingCount  INTEGER NOT NULL,
  idRangeStart       BIGINT,
  idRangeEnd         BIGINT,
  survivalRate       DOUBLE NOT NULL,             -- aliveCount / discoveredCount
  imageOnlyShare     DOUBLE,
  coverageStatus     coverageStatusEnum NOT NULL, -- survivalRate<0.60 이면 insufficient
  auditNote          VARCHAR,
  auditVersion       VARCHAR NOT NULL,
  auditedAt          TIMESTAMPTZ NOT NULL,
  PRIMARY KEY (periodMonth, sourceName, auditVersion)
);

CREATE TABLE qa.goldSample (
  goldId        VARCHAR PRIMARY KEY,
  goldSetName   VARCHAR NOT NULL,                 -- 'careerClass_v1'|'ncsMapping_v1'|'boundary_v1'
  targetType    evalTargetEnum NOT NULL,
  postingId     VARCHAR NOT NULL,
  trackId       VARCHAR,
  samplingFrame VARCHAR NOT NULL,                 -- 층화 정의 (연도×trackType 등)
  samplingSeed  INTEGER NOT NULL,
  goldValue     VARCHAR NOT NULL,
  annotator     VARCHAR NOT NULL,
  doubleCoded   BOOLEAN NOT NULL DEFAULT FALSE,
  secondAnnotator VARCHAR,
  secondValue   VARCHAR,
  adjudicated   BOOLEAN NOT NULL DEFAULT FALSE,
  evidenceText  VARCHAR,
  goldVersion   VARCHAR NOT NULL,
  labeledAt     TIMESTAMPTZ NOT NULL
);

CREATE TABLE qa.evalRun (
  evalRunId      VARCHAR PRIMARY KEY,
  targetType     evalTargetEnum NOT NULL,
  goldSetName    VARCHAR NOT NULL,
  goldVersion    VARCHAR NOT NULL,
  predictorVersion VARCHAR NOT NULL,              -- labelVersion 또는 mappingVersion
  n              INTEGER NOT NULL,
  precisionMacro DOUBLE,
  recallMacro    DOUBLE,
  macroF1        DOUBLE,
  precisionE0    DOUBLE,
  boundaryPrecision DOUBLE,
  mappingPrecision  DOUBLE,
  coverage       DOUBLE,
  lowConfidenceShare DOUBLE,
  cohenKappa     DOUBLE,                          -- 이중코딩 신뢰도
  passedGate     BOOLEAN NOT NULL,
  gateDetailJson VARCHAR,
  ranAt          TIMESTAMPTZ NOT NULL
);

-- 기사에 실리는 모든 숫자는 여기서 파생된다. 여기 없는 숫자는 기사에 쓰지 않는다.
CREATE TABLE qa.resultManifest (
  metricId        VARCHAR PRIMARY KEY,
  metricName      VARCHAR NOT NULL,
  metricScope     VARCHAR NOT NULL,               -- 'monthly'|'yearly'|'ytd'|'segment'|'model'
  cohortType      cohortTypeEnum NOT NULL,
  periodLabel     VARCHAR NOT NULL,               -- '2024-03' | '2019~2026' | 'YTD2026'
  jobCode         VARCHAR,
  metricValue     DOUBLE,
  metricValueText VARCHAR,
  ciLow           DOUBLE,
  ciHigh          DOUBLE,
  nDenominator    INTEGER,
  dedupApplied    BOOLEAN NOT NULL,
  scriptPath      VARCHAR NOT NULL,
  scriptGitSha    VARCHAR NOT NULL,
  inputMartSha256 VARCHAR NOT NULL,
  figureFile      VARCHAR,
  tableFile       VARCHAR,
  dataVersion     VARCHAR NOT NULL,
  computedAt      TIMESTAMPTZ NOT NULL
);

CREATE TABLE qa.decisionLog (
  decisionId   VARCHAR PRIMARY KEY,
  decidedAt    TIMESTAMPTZ NOT NULL,
  phase        VARCHAR NOT NULL,
  topic        VARCHAR NOT NULL,
  decision     VARCHAR NOT NULL,
  rationale    VARCHAR NOT NULL,
  supersedes   VARCHAR,
  decidedBy    VARCHAR NOT NULL,
  ssotSection  VARCHAR                            -- 갱신한 SSOT 절
);

-- =====================================================================
-- 7. 파생 뷰
-- =====================================================================

-- RQ1 분모. 항상 이 뷰를 통해서만 센다.
-- RECON_20260806_01 근거로 validPosting 단일기준 대신 rq1EligibleFlag 사용
-- (외부 ATS 전용이라 본문이 없어도 채용형태·게시일·기업명만 있으면 RQ1엔 포함시킨다).
CREATE VIEW mart.vValidPostingMonthly AS
SELECT
  periodMonth,
  cohortType,
  dedupAppliedFlag AS dedupApplied,
  COUNT(DISTINCT canonicalPostingId) AS totalValidPostingCount
FROM (
  SELECT periodMonth, cohortType, canonicalPostingId, TRUE AS dedupAppliedFlag
  FROM mart.postingAnalysisMart
  WHERE rq1EligibleFlag AND canonicalRecordFlag
  UNION ALL
  SELECT periodMonth, cohortType, postingId AS canonicalPostingId, FALSE AS dedupAppliedFlag
  FROM mart.postingAnalysisMart
  WHERE rq1EligibleFlag
)
GROUP BY 1,2,3;

-- 혼합 미해결 트랙 + 외부 ATS 전용(본문 없음) 공고는 RQ2에서 제외 (SSOT §3.3-5, RECON_20260806_01)
CREATE VIEW mart.vRq2Eligible AS
SELECT *
FROM mart.postingAnalysisMart
WHERE rq2EligibleFlag
  AND canonicalRecordFlag
  AND mixedResolvedFlag
  AND boundaryResolvedFlag
  AND trackType <> 'mixedUnresolved';

-- NCS 매핑 분모 전용 뷰 (RECON_20260806_01 신설)
CREATE VIEW mart.vNcsEligible AS
SELECT *
FROM mart.postingAnalysisMart
WHERE ncsEligibleFlag
  AND canonicalRecordFlag
  AND trackType <> 'mixedUnresolved';

-- 분석 준비 게이트 점검
CREATE VIEW qa.vAnalysisReadyGate AS
SELECT
  (SELECT COUNT(*) FROM qa.monthlyCoverageAudit WHERE coverageStatus = 'insufficient') AS insufficientMonths,
  (SELECT MAX(macroF1) FROM qa.evalRun WHERE targetType='careerClass') AS careerMacroF1,
  (SELECT MAX(precisionE0) FROM qa.evalRun WHERE targetType='careerClass') AS precisionE0,
  (SELECT MAX(boundaryPrecision) FROM qa.evalRun WHERE targetType='boundary') AS boundaryPrecision,
  (SELECT MAX(mappingPrecision) FROM qa.evalRun WHERE targetType='ncsMapping') AS mappingPrecision,
  (SELECT MAX(coverage) FROM qa.evalRun WHERE targetType='ncsMapping') AS mappingCoverage,
  (SELECT COUNT(*) FROM mart.postingAnalysisMart) AS martRows,
  (SELECT COUNT(*) FROM mart.timeSeriesMart) AS timeSeriesRows,
  (SELECT COUNT(*) FROM qa.resultManifest) AS manifestRows;
