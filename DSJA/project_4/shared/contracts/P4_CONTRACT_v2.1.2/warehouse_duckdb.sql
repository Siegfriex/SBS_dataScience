-- GENERATED FILE - DO NOT EDIT
-- contractVersion: 2.1.2
-- sourceContractSha256: f92380cdfc16967f1e363800cd9a575e44532f18a86b2f28f8c3e2404ed675e9
-- generatedAt: 2026-08-06T05:08:58+00:00
-- generatorVersion: 2.1.2
SET TimeZone = 'Asia/Seoul';

CREATE SCHEMA IF NOT EXISTS raw;
CREATE SCHEMA IF NOT EXISTS core;
CREATE SCHEMA IF NOT EXISTS ncs;
CREATE SCHEMA IF NOT EXISTS mart;
CREATE SCHEMA IF NOT EXISTS qa;

-- Versioned registry of verified Linkareer APQ and SSR query architecture
CREATE TABLE IF NOT EXISTS raw.queryRegistry (
  operationName VARCHAR NOT NULL,
  sha256Hash VARCHAR NOT NULL CHECK (length(sha256Hash) = 64),
  transportType VARCHAR NOT NULL CHECK (transportType IN ('graphqlApq', 'nextDataSsr', 'apolloCache', 'html')),
  httpMethod VARCHAR NOT NULL CHECK (httpMethod IN ('GET', 'POST')),
  variablesSchemaJson JSON,
  responseSchemaJson JSON,
  frontendBuildId VARCHAR,
  discoveredAt TIMESTAMPTZ NOT NULL,
  lastVerifiedAt TIMESTAMPTZ NOT NULL,
  activeFlag BOOLEAN NOT NULL,
  verificationStatus VARCHAR NOT NULL CHECK (verificationStatus IN ('verified', 'stale', 'failed', 'pending')),
  PRIMARY KEY (operationName, sha256Hash)
);

-- Source authorization and coverage registry
CREATE TABLE IF NOT EXISTS raw.sourceRegistry (
  sourceName VARCHAR NOT NULL CHECK (sourceName IN ('linkareer', 'ncs')),
  sourceType VARCHAR NOT NULL CHECK (sourceType IN ('web', 'api', 'fileDownload')),
  sourceRole VARCHAR NOT NULL CHECK (sourceRole IN ('posting', 'competency')),
  baseUrl VARCHAR NOT NULL,
  termsStatus VARCHAR NOT NULL DEFAULT 'unverified' CHECK (termsStatus IN ('reviewedConditional', 'permissionGranted', 'permitted', 'restricted', 'unverified')),
  robotsStatus VARCHAR NOT NULL DEFAULT 'unverified' CHECK (robotsStatus IN ('allowed', 'restricted', 'notApplicable', 'unverified')),
  historyStart DATE,
  historyEnd DATE,
  historyStatus VARCHAR NOT NULL DEFAULT 'unverified' CHECK (historyStatus IN ('confirmed', 'partial', 'unavailable', 'unverified')),
  paginationType VARCHAR CHECK (paginationType IN ('page', 'cursor', 'infiniteScroll', 'internalJson', 'unknown')),
  verifiedAt TIMESTAMPTZ,
  PRIMARY KEY (sourceName)
);

-- Collection run metadata
CREATE TABLE IF NOT EXISTS raw.crawlRun (
  crawlRunId VARCHAR NOT NULL,
  sourceName VARCHAR NOT NULL,
  runPhase VARCHAR NOT NULL,
  collectorVersion VARCHAR NOT NULL,
  configSha256 VARCHAR NOT NULL CHECK (length(configSha256) = 64),
  startedAt TIMESTAMPTZ NOT NULL,
  endedAt TIMESTAMPTZ,
  status VARCHAR NOT NULL CHECK (status IN ('running', 'completed', 'aborted', 'failed', 'partial')),
  requestCount INTEGER NOT NULL DEFAULT 0 CHECK (requestCount >= 0),
  successCount INTEGER NOT NULL DEFAULT 0 CHECK (successCount >= 0),
  failCount INTEGER NOT NULL DEFAULT 0 CHECK (failCount >= 0),
  gitCommitSha VARCHAR,
  PRIMARY KEY (crawlRunId)
);

-- Immutable index discovery record
CREATE TABLE IF NOT EXISTS raw.linkareerIndexRaw (
  indexItemId VARCHAR NOT NULL,
  crawlRunId VARCHAR NOT NULL,
  discoveryType VARCHAR NOT NULL,
  sourcePostingId VARCHAR,
  detailUrl VARCHAR NOT NULL,
  titleRaw VARCHAR,
  companyRaw VARCHAR,
  postedAtRaw VARCHAR,
  categoryRaw VARCHAR,
  activityTypeId VARCHAR NOT NULL,
  groupRaw VARCHAR,
  jobTypesRawJson JSON,
  recruitStartAt TIMESTAMPTZ,
  recruitCloseAt TIMESTAMPTZ,
  activityStartAt TIMESTAMPTZ,
  activityEndAt TIMESTAMPTZ,
  createdAt TIMESTAMPTZ,
  rawPath VARCHAR NOT NULL,
  rawSha256 VARCHAR NOT NULL CHECK (length(rawSha256) = 64),
  PRIMARY KEY (indexItemId)
);

-- Immutable posting detail snapshot; postingRawId is a superseded alias
CREATE TABLE IF NOT EXISTS raw.linkareerPostingRaw (
  rawPostingId VARCHAR NOT NULL,
  indexItemId VARCHAR,
  crawlRunId VARCHAR NOT NULL,
  sourcePostingId VARCHAR NOT NULL,
  sourceUrl VARCHAR NOT NULL,
  fetchedAt TIMESTAMPTZ NOT NULL,
  httpStatus SMALLINT NOT NULL CHECK (httpStatus BETWEEN 100 AND 599),
  contentType VARCHAR,
  rawPath VARCHAR NOT NULL,
  rawSha256 VARCHAR NOT NULL CHECK (length(rawSha256) = 64),
  textAvailableFlag BOOLEAN NOT NULL DEFAULT FALSE,
  assetCount SMALLINT NOT NULL DEFAULT 0 CHECK (assetCount >= 0),
  nextDataJsonPath VARCHAR,
  activityJsonPath VARCHAR,
  apolloCacheJsonPath VARCHAR,
  activityTextEntityKey VARCHAR,
  dutiesRawJson JSON,
  activityTextHtml VARCHAR,
  activityTextAvailableFlag BOOLEAN NOT NULL DEFAULT FALSE,
  externalApplyUrl VARCHAR,
  externalApplyFlag BOOLEAN NOT NULL DEFAULT FALSE,
  externalAtsDomain VARCHAR,
  externalDetailOnlyFlag BOOLEAN NOT NULL DEFAULT FALSE,
  PRIMARY KEY (rawPostingId)
);

-- Posting image PDF or attachment lineage
CREATE TABLE IF NOT EXISTS raw.postingAsset (
  assetId VARCHAR NOT NULL,
  rawPostingId VARCHAR NOT NULL,
  assetType VARCHAR NOT NULL CHECK (assetType IN ('image', 'pdf', 'attachment', 'other')),
  assetUrl VARCHAR,
  assetPath VARCHAR NOT NULL,
  assetSha256 VARCHAR NOT NULL CHECK (length(assetSha256) = 64),
  widthPx INTEGER CHECK (widthPx IS NULL OR widthPx > 0),
  heightPx INTEGER CHECK (heightPx IS NULL OR heightPx > 0),
  bytes BIGINT CHECK (bytes IS NULL OR bytes >= 0),
  PRIMARY KEY (assetId)
);

-- OCR result and block lineage
CREATE TABLE IF NOT EXISTS raw.ocrResult (
  ocrId VARCHAR NOT NULL,
  assetId VARCHAR NOT NULL,
  ocrEngine VARCHAR NOT NULL,
  ocrModel VARCHAR NOT NULL,
  ocrVersion VARCHAR NOT NULL,
  ocrText VARCHAR,
  ocrBlocksJson JSON,
  ocrConfidence DOUBLE CHECK (ocrConfidence IS NULL OR ocrConfidence BETWEEN 0 AND 1),
  ocrReviewFlag BOOLEAN NOT NULL DEFAULT FALSE,
  producedAt TIMESTAMPTZ NOT NULL,
  PRIMARY KEY (ocrId)
);

-- One normalized posting identity with dedup-independent eligibility
CREATE TABLE IF NOT EXISTS core.postingNormalized (
  postingId VARCHAR NOT NULL,
  rawPostingId VARCHAR NOT NULL,
  sourcePostingId VARCHAR NOT NULL,
  sourceUrl VARCHAR NOT NULL,
  companyKey VARCHAR,
  companyName VARCHAR,
  industryName VARCHAR,
  jobTitle VARCHAR,
  bodyText VARCHAR,
  postedAt TIMESTAMPTZ,
  deadlineAt TIMESTAMPTZ,
  postingKind VARCHAR NOT NULL CHECK (postingKind IN ('recruitIntern', 'recruitNewGrad', 'recruitExperienced', 'recruitUnknown', 'contest', 'extracurricular', 'education', 'club', 'volunteer', 'other')),
  recruitmentScope VARCHAR NOT NULL CHECK (recruitmentScope IN ('entryOnly', 'internOnly', 'experiencedOnly', 'entryInternMixed', 'entryExperiencedMixed', 'internExperiencedMixed', 'allMixed', 'mixedUnresolved', 'unknown')),
  postingEligibleFlag BOOLEAN NOT NULL DEFAULT FALSE,
  rq1EligibleFlag BOOLEAN NOT NULL DEFAULT FALSE,
  rq2EligibleFlag BOOLEAN NOT NULL DEFAULT FALSE,
  ncsEligibleFlag BOOLEAN NOT NULL DEFAULT FALSE,
  rq2ExclusionReason VARCHAR CHECK (rq2ExclusionReason IN ('activityTextMissing', 'externalAtsBodyUnavailable', 'boundaryUnresolved', 'trackUnresolved', 'textTooShort', 'nonRecruitPosting', 'other')),
  invalidReason VARCHAR,
  duplicateGroupId VARCHAR,
  canonicalPostingId VARCHAR NOT NULL,
  canonicalPostedAt TIMESTAMPTZ NOT NULL,
  canonicalRecordFlag BOOLEAN NOT NULL DEFAULT TRUE,
  repostCount SMALLINT NOT NULL DEFAULT 0 CHECK (repostCount >= 0),
  rawSha256 VARCHAR NOT NULL CHECK (length(rawSha256) = 64),
  parseVersion VARCHAR NOT NULL,
  dataVersion VARCHAR NOT NULL,
  normalizedAt TIMESTAMPTZ NOT NULL,
  PRIMARY KEY (postingId)
);

-- Recruitment track within a posting
CREATE TABLE IF NOT EXISTS core.postingTrack (
  trackId VARCHAR NOT NULL,
  postingId VARCHAR NOT NULL,
  trackIndex SMALLINT NOT NULL CHECK (trackIndex >= 0),
  trackType VARCHAR NOT NULL CHECK (trackType IN ('entry', 'intern', 'experienced', 'mixedUnresolved', 'unknown')),
  trackTitle VARCHAR,
  hasEntryFlag BOOLEAN NOT NULL,
  hasInternFlag BOOLEAN NOT NULL,
  hasExperiencedFlag BOOLEAN NOT NULL,
  recruitmentScope VARCHAR NOT NULL CHECK (recruitmentScope IN ('entryOnly', 'internOnly', 'experiencedOnly', 'entryInternMixed', 'entryExperiencedMixed', 'internExperiencedMixed', 'allMixed', 'mixedUnresolved', 'unknown')),
  mixedResolvedFlag BOOLEAN NOT NULL,
  splitConfidence DOUBLE CHECK (splitConfidence IS NULL OR splitConfidence BETWEEN 0 AND 1),
  trackVersion VARCHAR NOT NULL,
  jobTypeSource VARCHAR NOT NULL CHECK (jobTypeSource IN ('dutiesJobType', 'jobTypes', 'detailText', 'unresolved')),
  jobTypeConflictFlag BOOLEAN NOT NULL DEFAULT FALSE,
  PRIMARY KEY (trackId),
  UNIQUE (postingId, trackIndex)
);

-- Typed section within a track
CREATE TABLE IF NOT EXISTS core.postingSection (
  sectionId VARCHAR NOT NULL,
  trackId VARCHAR NOT NULL,
  postingId VARCHAR NOT NULL,
  sectionOrder SMALLINT NOT NULL CHECK (sectionOrder >= 0),
  sectionType VARCHAR NOT NULL CHECK (sectionType IN ('title', 'duty', 'required', 'preferred', 'qualification', 'process', 'condition', 'benefit', 'company', 'other')),
  sectionText VARCHAR NOT NULL,
  sourceMode VARCHAR NOT NULL CHECK (sourceMode IN ('html', 'ocr', 'merged')),
  boundaryResolvedFlag BOOLEAN NOT NULL,
  sectionConfidence DOUBLE CHECK (sectionConfidence IS NULL OR sectionConfidence BETWEEN 0 AND 1),
  parseVersion VARCHAR NOT NULL,
  PRIMARY KEY (sectionId),
  UNIQUE (trackId, sectionOrder)
);

-- Atomic requirement evidence
CREATE TABLE IF NOT EXISTS core.requirementFact (
  requirementId VARCHAR NOT NULL,
  sectionId VARCHAR NOT NULL,
  trackId VARCHAR NOT NULL,
  postingId VARCHAR NOT NULL,
  requirementType VARCHAR NOT NULL CHECK (requirementType IN ('careerMonths', 'priorExperience', 'portfolio', 'project', 'certificate', 'degree', 'major', 'skill', 'tool', 'language', 'duty', 'other')),
  obligation VARCHAR NOT NULL CHECK (obligation IN ('required', 'preferred', 'unknown')),
  valueNum DOUBLE,
  valueUnit VARCHAR,
  valueText VARCHAR,
  certificateNameRaw VARCHAR,
  certificateClass VARCHAR CHECK (certificateClass IN ('craftsman', 'industrialEngineer', 'engineer', 'masterCraftsman', 'professionalEngineer', 'otherNational')),
  degreeLevel VARCHAR CHECK (degreeLevel IN ('highSchool', 'associate', 'bachelor', 'master', 'doctor')),
  evidenceText VARCHAR NOT NULL,
  extractorVersion VARCHAR NOT NULL,
  confidence DOUBLE CHECK (confidence IS NULL OR confidence BETWEEN 0 AND 1),
  reviewFlag BOOLEAN NOT NULL DEFAULT FALSE,
  PRIMARY KEY (requirementId)
);

-- Career and intern access labels
CREATE TABLE IF NOT EXISTS core.careerLabel (
  trackId VARCHAR NOT NULL,
  postingId VARCHAR NOT NULL,
  careerClass VARCHAR NOT NULL CHECK (careerClass IN ('E0', 'E1', 'E2', 'E3', 'U')),
  internAccessClass VARCHAR CHECK (internAccessClass IN ('I0', 'I1', 'IU')),
  nominalEntryFlag BOOLEAN NOT NULL,
  openEntryFlag BOOLEAN NOT NULL,
  restrictedEntryFlag BOOLEAN NOT NULL,
  openInternFlag BOOLEAN NOT NULL,
  restrictedInternFlag BOOLEAN NOT NULL,
  experiencedInternFlag BOOLEAN NOT NULL,
  minCareerMonths SMALLINT CHECK (minCareerMonths IS NULL OR minCareerMonths >= 0),
  requiredExperienceFlag BOOLEAN NOT NULL,
  requiredPriorExperienceFlag BOOLEAN NOT NULL,
  boundaryResolvedFlag BOOLEAN NOT NULL,
  explicitCareerFlag BOOLEAN NOT NULL,
  labelConfidence DOUBLE CHECK (labelConfidence IS NULL OR labelConfidence BETWEEN 0 AND 1),
  labelVersion VARCHAR NOT NULL,
  PRIMARY KEY (trackId)
);

-- Auditable pairwise repost decision
CREATE TABLE IF NOT EXISTS core.postingDedupEdge (
  edgeId VARCHAR NOT NULL,
  leftPostingId VARCHAR NOT NULL,
  rightPostingId VARCHAR NOT NULL,
  dayDiff INTEGER NOT NULL CHECK (dayDiff BETWEEN 0 AND 90),
  titleSimilarity DOUBLE CHECK (titleSimilarity IS NULL OR titleSimilarity BETWEEN 0 AND 1),
  bodySimilarity DOUBLE CHECK (bodySimilarity IS NULL OR bodySimilarity BETWEEN 0 AND 1),
  decision VARCHAR NOT NULL CHECK (decision IN ('sameGroup', 'distinct', 'undecided')),
  decisionBasis VARCHAR,
  dedupVersion VARCHAR NOT NULL,
  PRIMARY KEY (edgeId),
  UNIQUE (leftPostingId, rightPostingId, dedupVersion)
);

-- NCS unit and level anchor
CREATE TABLE IF NOT EXISTS ncs.ncsUnit (
  ncsUnitCode VARCHAR NOT NULL,
  ncsUnitName VARCHAR NOT NULL,
  ncsMajorCode VARCHAR,
  ncsMiddleCode VARCHAR,
  ncsMinorCode VARCHAR,
  ncsSubCode VARCHAR NOT NULL,
  ncsLevel SMALLINT NOT NULL CHECK (ncsLevel BETWEEN 1 AND 8),
  ncsBand VARCHAR NOT NULL CHECK (ncsBand IN ('level1to2', 'level3to4', 'level5to6', 'level7to8')),
  definitionText VARCHAR,
  performanceCriteriaText VARCHAR,
  knowledgeText VARCHAR,
  skillText VARCHAR,
  attitudeText VARCHAR,
  developmentYear SMALLINT,
  sourceVersion VARCHAR NOT NULL,
  rawSha256 VARCHAR NOT NULL CHECK (length(rawSha256) = 64),
  PRIMARY KEY (ncsUnitCode)
);

-- NCS learning module task evidence
CREATE TABLE IF NOT EXISTS ncs.ncsLearningModule (
  moduleId VARCHAR NOT NULL,
  ncsUnitCode VARCHAR NOT NULL,
  moduleName VARCHAR NOT NULL,
  taskText VARCHAR,
  trainingLevel SMALLINT CHECK (trainingLevel IS NULL OR trainingLevel BETWEEN 1 AND 8),
  sourceUrl VARCHAR,
  localFilePath VARCHAR,
  redistributableFlag BOOLEAN NOT NULL DEFAULT FALSE,
  sourceVersion VARCHAR NOT NULL,
  rawSha256 VARCHAR NOT NULL CHECK (length(rawSha256) = 64),
  PRIMARY KEY (moduleId)
);

-- Evidence-bearing posting-task to NCS match
CREATE TABLE IF NOT EXISTS ncs.postingNcsMatch (
  matchId VARCHAR NOT NULL,
  postingId VARCHAR NOT NULL,
  trackId VARCHAR NOT NULL,
  sectionId VARCHAR,
  requirementId VARCHAR,
  ncsUnitCode VARCHAR NOT NULL,
  ncsLevel SMALLINT NOT NULL CHECK (ncsLevel BETWEEN 1 AND 8),
  ncsBand VARCHAR NOT NULL CHECK (ncsBand IN ('level1to2', 'level3to4', 'level5to6', 'level7to8')),
  mappingBasis VARCHAR NOT NULL CHECK (mappingBasis IN ('ncsUnitDirect', 'ncsPerformanceCriteria', 'ncsLearningModule', 'dictionaryRule', 'semanticMatch')),
  matchScore DOUBLE CHECK (matchScore IS NULL OR matchScore BETWEEN 0 AND 1),
  matchRank SMALLINT NOT NULL CHECK (matchRank >= 1),
  selectedFlag BOOLEAN NOT NULL,
  ncsConfidenceTier VARCHAR NOT NULL CHECK (ncsConfidenceTier IN ('high', 'medium', 'low')),
  evidenceText VARCHAR NOT NULL,
  mappingVersion VARCHAR NOT NULL,
  matchedAt TIMESTAMPTZ NOT NULL,
  PRIMARY KEY (matchId)
);

-- Canonical track-grain analytical mart
CREATE TABLE IF NOT EXISTS mart.postingAnalysisMart (
  trackId VARCHAR NOT NULL,
  postingId VARCHAR NOT NULL,
  canonicalPostingId VARCHAR NOT NULL,
  canonicalPostedAt TIMESTAMPTZ NOT NULL,
  periodMonth DATE NOT NULL,
  year SMALLINT NOT NULL,
  month SMALLINT NOT NULL CHECK (month BETWEEN 1 AND 12),
  quarterNumber SMALLINT NOT NULL CHECK (quarterNumber BETWEEN 1 AND 4),
  asOfDate DATE NOT NULL,
  sourceName VARCHAR NOT NULL CHECK (sourceName IN ('linkareer')),
  sourceUrl VARCHAR NOT NULL,
  companyKey VARCHAR,
  companyName VARCHAR,
  jobTitle VARCHAR,
  cohortType VARCHAR NOT NULL CHECK (cohortType IN ('coreAiIt', 'allJobs')),
  jobCodeLevel VARCHAR NOT NULL CHECK (jobCodeLevel IN ('all', 'major', 'middle', 'minor', 'sub')),
  jobCode VARCHAR NOT NULL,
  coreAiItFlag BOOLEAN NOT NULL,
  postingKind VARCHAR NOT NULL CHECK (postingKind IN ('recruitIntern', 'recruitNewGrad', 'recruitExperienced', 'recruitUnknown', 'contest', 'extracurricular', 'education', 'club', 'volunteer', 'other')),
  postingEligibleFlag BOOLEAN NOT NULL,
  rq1EligibleFlag BOOLEAN NOT NULL,
  rq2EligibleFlag BOOLEAN NOT NULL,
  ncsEligibleFlag BOOLEAN NOT NULL,
  rq2ExclusionReason VARCHAR CHECK (rq2ExclusionReason IN ('activityTextMissing', 'externalAtsBodyUnavailable', 'boundaryUnresolved', 'trackUnresolved', 'textTooShort', 'nonRecruitPosting', 'other')),
  canonicalRecordFlag BOOLEAN NOT NULL,
  trackType VARCHAR NOT NULL CHECK (trackType IN ('entry', 'intern', 'experienced', 'mixedUnresolved', 'unknown')),
  recruitmentScope VARCHAR NOT NULL CHECK (recruitmentScope IN ('entryOnly', 'internOnly', 'experiencedOnly', 'entryInternMixed', 'entryExperiencedMixed', 'internExperiencedMixed', 'allMixed', 'mixedUnresolved', 'unknown')),
  hasEntryFlag BOOLEAN NOT NULL,
  hasInternFlag BOOLEAN NOT NULL,
  hasExperiencedFlag BOOLEAN NOT NULL,
  mixedResolvedFlag BOOLEAN NOT NULL,
  activityTextAvailableFlag BOOLEAN NOT NULL,
  externalApplyFlag BOOLEAN NOT NULL,
  externalDetailOnlyFlag BOOLEAN NOT NULL,
  jobTypeConflictFlag BOOLEAN NOT NULL,
  careerClass VARCHAR NOT NULL CHECK (careerClass IN ('E0', 'E1', 'E2', 'E3', 'U')),
  internAccessClass VARCHAR CHECK (internAccessClass IN ('I0', 'I1', 'IU')),
  nominalEntryFlag BOOLEAN NOT NULL,
  restrictedInternFlag BOOLEAN NOT NULL,
  experiencedInternFlag BOOLEAN NOT NULL,
  boundaryResolvedFlag BOOLEAN NOT NULL,
  minCareerMonths SMALLINT CHECK (minCareerMonths IS NULL OR minCareerMonths >= 0),
  ncsLevelWeightedMedian DOUBLE,
  ncsBandPrimary VARCHAR CHECK (ncsBandPrimary IN ('level1to2', 'level3to4', 'level5to6', 'level7to8')),
  ncsMappingCoverage DOUBLE NOT NULL CHECK (ncsMappingCoverage BETWEEN 0 AND 1),
  ncsConfidenceTier VARCHAR CHECK (ncsConfidenceTier IN ('high', 'medium', 'low')),
  highDemandScore DOUBLE CHECK (highDemandScore IS NULL),
  scoreStatus VARCHAR NOT NULL DEFAULT 'reserved' CHECK (scoreStatus IN ('reserved')),
  duplicateGroupId VARCHAR,
  repostCount SMALLINT NOT NULL DEFAULT 0 CHECK (repostCount >= 0),
  rawSha256 VARCHAR NOT NULL CHECK (length(rawSha256) = 64),
  parseVersion VARCHAR NOT NULL,
  labelVersion VARCHAR NOT NULL,
  ncsMapVersion VARCHAR NOT NULL,
  dataVersion VARCHAR NOT NULL,
  builtAt TIMESTAMPTZ NOT NULL,
  PRIMARY KEY (trackId)
);

-- Monthly metric mart
CREATE TABLE IF NOT EXISTS mart.timeSeriesMart (
  periodMonth DATE NOT NULL,
  cohortType VARCHAR NOT NULL CHECK (cohortType IN ('coreAiIt', 'allJobs')),
  jobCodeLevel VARCHAR NOT NULL CHECK (jobCodeLevel IN ('all', 'major', 'middle', 'minor', 'sub')),
  jobCode VARCHAR NOT NULL,
  dedupApplied BOOLEAN NOT NULL,
  totalValidPostingCount INTEGER NOT NULL CHECK (totalValidPostingCount >= 0),
  entryPostingCount INTEGER NOT NULL CHECK (entryPostingCount >= 0),
  internPostingCount INTEGER NOT NULL CHECK (internPostingCount >= 0),
  entryPostingRate DOUBLE,
  internPostingRate DOUBLE,
  entryOnlyRate DOUBLE,
  internOnlyRate DOUBLE,
  mixedRate DOUBLE,
  experiencedOnlyRate DOUBLE,
  internRelativeIndex DOUBLE,
  openEntryShare DOUBLE,
  restrictedEntryShare DOUBLE,
  unknownCareerShare DOUBLE,
  restrictedInternShare DOUBLE,
  experiencedInternShare DOUBLE,
  unknownInternShare DOUBLE,
  advancedDutyShare DOUBLE,
  ncsMappingCoverage DOUBLE,
  lowConfidenceNcsShare DOUBLE,
  rq1EligibilityRate DOUBLE,
  rq2EligibilityRate DOUBLE,
  ncsEligibilityRate DOUBLE,
  externalApplyShare DOUBLE CHECK (externalApplyShare IS NULL OR externalApplyShare BETWEEN 0 AND 1),
  externalDetailOnlyShare DOUBLE CHECK (externalDetailOnlyShare IS NULL OR externalDetailOnlyShare BETWEEN 0 AND 1),
  activityTextAvailabilityRate DOUBLE,
  jobTypeConflictRate DOUBLE,
  coverageStatus VARCHAR NOT NULL CHECK (coverageStatus IN ('complete', 'partial', 'insufficient', 'excluded', 'unverified')),
  partialMonthFlag BOOLEAN NOT NULL,
  asOfDate DATE NOT NULL,
  dataVersion VARCHAR NOT NULL,
  builtAt TIMESTAMPTZ NOT NULL,
  PRIMARY KEY (periodMonth, cohortType, jobCodeLevel, jobCode, dedupApplied)
);

-- Manual RQ5 case registry
CREATE TABLE IF NOT EXISTS mart.caseStudyRegistry (
  caseId VARCHAR NOT NULL,
  postingId VARCHAR NOT NULL,
  trackId VARCHAR,
  companyName VARCHAR,
  selectionReason VARCHAR NOT NULL,
  evidenceQuote VARCHAR,
  reviewedBy VARCHAR NOT NULL,
  reviewedAt TIMESTAMPTZ NOT NULL,
  PRIMARY KEY (caseId)
);

-- Optional RQ3 similarity result
CREATE TABLE IF NOT EXISTS mart.similarityPair (
  pairId VARCHAR NOT NULL,
  internTrackId VARCHAR NOT NULL,
  comparisonTrackId VARCHAR NOT NULL,
  comparisonType VARCHAR NOT NULL CHECK (comparisonType IN ('entry', 'experienced')),
  ncsSubCode VARCHAR,
  yearGap SMALLINT CHECK (yearGap IS NULL OR yearGap BETWEEN 0 AND 1),
  qualificationSimilarity DOUBLE,
  dutySimilarity DOUBLE,
  embeddingModel VARCHAR NOT NULL,
  auxVersion VARCHAR NOT NULL,
  PRIMARY KEY (pairId)
);

-- Monthly collection and OCR coverage audit
CREATE TABLE IF NOT EXISTS qa.monthlyCoverageAudit (
  periodMonth DATE NOT NULL,
  sourceName VARCHAR NOT NULL,
  discoveredCount INTEGER NOT NULL CHECK (discoveredCount >= 0),
  fetchedCount INTEGER NOT NULL CHECK (fetchedCount >= 0),
  aliveCount INTEGER NOT NULL CHECK (aliveCount >= 0),
  deadCount INTEGER NOT NULL CHECK (deadCount >= 0),
  parsedCount INTEGER NOT NULL CHECK (parsedCount >= 0),
  validPostingCount INTEGER NOT NULL CHECK (validPostingCount >= 0),
  imageOnlyShare DOUBLE,
  ocrAttemptCount INTEGER NOT NULL DEFAULT 0 CHECK (ocrAttemptCount >= 0),
  ocrSuccessCount INTEGER NOT NULL DEFAULT 0 CHECK (ocrSuccessCount >= 0),
  ocrSuccessRate DOUBLE,
  survivalRate DOUBLE,
  coverageStatus VARCHAR NOT NULL CHECK (coverageStatus IN ('complete', 'partial', 'insufficient', 'excluded', 'unverified')),
  coverageReason VARCHAR NOT NULL CHECK (coverageReason IN ('completeObserved', 'partialMonth', 'platformPreLaunch', 'historicalLoss', 'paginationUnverified', 'sourceChange', 'policyBlocked', 'other', 'unverified')),
  platformCoverageRegime VARCHAR NOT NULL CHECK (platformCoverageRegime IN ('preStableRecruitService', 'stableRecruitService', 'sourceDesignChange', 'unknown')),
  auditNote VARCHAR,
  auditVersion VARCHAR NOT NULL,
  auditedAt TIMESTAMPTZ NOT NULL,
  PRIMARY KEY (periodMonth, sourceName, auditVersion)
);

-- Versioned source-policy evidence used by the collection gate
CREATE TABLE IF NOT EXISTS qa.sourcePolicyAudit (
  sourceName VARCHAR NOT NULL,
  policyVersion VARCHAR NOT NULL,
  robotsStatus VARCHAR NOT NULL CHECK (robotsStatus IN ('allowed', 'restricted', 'notApplicable', 'unverified')),
  termsStatus VARCHAR NOT NULL CHECK (termsStatus IN ('reviewedConditional', 'permissionGranted', 'permitted', 'restricted', 'unverified')),
  clientAccessMode VARCHAR NOT NULL CHECK (clientAccessMode IN ('transparentHttp', 'documentedBrowser', 'impersonatedOnly', 'unverified')),
  transparentClientVerified BOOLEAN NOT NULL DEFAULT FALSE,
  collectionBlocked BOOLEAN NOT NULL DEFAULT FALSE,
  verifiedAt TIMESTAMPTZ NOT NULL,
  reviewerStatus VARCHAR NOT NULL CHECK (reviewerStatus IN ('pending', 'reviewed', 'approved', 'rejected')),
  evidenceSha256 VARCHAR NOT NULL CHECK (length(evidenceSha256) = 64),
  policyNote VARCHAR,
  PRIMARY KEY (sourceName, policyVersion)
);

-- Human-labeled evaluation sample
CREATE TABLE IF NOT EXISTS qa.goldSample (
  goldId VARCHAR NOT NULL,
  goldSetName VARCHAR NOT NULL,
  targetType VARCHAR NOT NULL,
  postingId VARCHAR NOT NULL,
  trackId VARCHAR,
  goldValue VARCHAR NOT NULL,
  annotator VARCHAR NOT NULL,
  doubleCodedFlag BOOLEAN NOT NULL DEFAULT FALSE,
  evidenceText VARCHAR,
  goldVersion VARCHAR NOT NULL,
  labeledAt TIMESTAMPTZ NOT NULL,
  PRIMARY KEY (goldId)
);

-- Quality-gate evaluation run
CREATE TABLE IF NOT EXISTS qa.evalRun (
  evalRunId VARCHAR NOT NULL,
  targetType VARCHAR NOT NULL,
  goldSetName VARCHAR NOT NULL,
  predictorVersion VARCHAR NOT NULL,
  sampleCount INTEGER NOT NULL CHECK (sampleCount >= 0),
  macroF1 DOUBLE,
  precisionE0 DOUBLE,
  boundaryPrecision DOUBLE,
  mappingPrecision DOUBLE,
  mappingCoverage DOUBLE,
  lowConfidenceShare DOUBLE,
  passedGate BOOLEAN NOT NULL,
  ranAt TIMESTAMPTZ NOT NULL,
  PRIMARY KEY (evalRunId)
);

-- Reproducibility manifest for every reported result
CREATE TABLE IF NOT EXISTS qa.resultManifest (
  metricId VARCHAR NOT NULL,
  metricName VARCHAR NOT NULL,
  metricScope VARCHAR NOT NULL,
  cohortType VARCHAR NOT NULL CHECK (cohortType IN ('coreAiIt', 'allJobs')),
  periodLabel VARCHAR NOT NULL,
  jobCode VARCHAR,
  metricValue DOUBLE,
  denominatorCount INTEGER,
  dedupApplied BOOLEAN NOT NULL,
  scriptPath VARCHAR NOT NULL,
  scriptGitSha VARCHAR NOT NULL,
  inputMartSha256 VARCHAR NOT NULL CHECK (length(inputMartSha256) = 64),
  dataVersion VARCHAR NOT NULL,
  computedAt TIMESTAMPTZ NOT NULL,
  PRIMARY KEY (metricId)
);

-- Versioned project decision log
CREATE TABLE IF NOT EXISTS qa.decisionLog (
  decisionId VARCHAR NOT NULL,
  decidedAt TIMESTAMPTZ NOT NULL,
  phase VARCHAR NOT NULL,
  topic VARCHAR NOT NULL,
  decision VARCHAR NOT NULL,
  rationale VARCHAR NOT NULL,
  supersedes VARCHAR,
  decidedBy VARCHAR NOT NULL,
  ssotSection VARCHAR,
  PRIMARY KEY (decisionId)
);

CREATE OR REPLACE VIEW qa.vPrimaryKeyViolations AS
SELECT 'raw.queryRegistry' AS tableName, ((SELECT COUNT(*) FROM raw.queryRegistry WHERE operationName IS NULL OR sha256Hash IS NULL) + (SELECT COUNT(*) FROM (SELECT operationName, sha256Hash, COUNT(*) AS duplicateCount FROM raw.queryRegistry GROUP BY operationName, sha256Hash HAVING COUNT(*) > 1)))::BIGINT AS violationCount
UNION ALL
SELECT 'raw.sourceRegistry' AS tableName, ((SELECT COUNT(*) FROM raw.sourceRegistry WHERE sourceName IS NULL) + (SELECT COUNT(*) FROM (SELECT sourceName, COUNT(*) AS duplicateCount FROM raw.sourceRegistry GROUP BY sourceName HAVING COUNT(*) > 1)))::BIGINT AS violationCount
UNION ALL
SELECT 'raw.crawlRun' AS tableName, ((SELECT COUNT(*) FROM raw.crawlRun WHERE crawlRunId IS NULL) + (SELECT COUNT(*) FROM (SELECT crawlRunId, COUNT(*) AS duplicateCount FROM raw.crawlRun GROUP BY crawlRunId HAVING COUNT(*) > 1)))::BIGINT AS violationCount
UNION ALL
SELECT 'raw.linkareerIndexRaw' AS tableName, ((SELECT COUNT(*) FROM raw.linkareerIndexRaw WHERE indexItemId IS NULL) + (SELECT COUNT(*) FROM (SELECT indexItemId, COUNT(*) AS duplicateCount FROM raw.linkareerIndexRaw GROUP BY indexItemId HAVING COUNT(*) > 1)))::BIGINT AS violationCount
UNION ALL
SELECT 'raw.linkareerPostingRaw' AS tableName, ((SELECT COUNT(*) FROM raw.linkareerPostingRaw WHERE rawPostingId IS NULL) + (SELECT COUNT(*) FROM (SELECT rawPostingId, COUNT(*) AS duplicateCount FROM raw.linkareerPostingRaw GROUP BY rawPostingId HAVING COUNT(*) > 1)))::BIGINT AS violationCount
UNION ALL
SELECT 'raw.postingAsset' AS tableName, ((SELECT COUNT(*) FROM raw.postingAsset WHERE assetId IS NULL) + (SELECT COUNT(*) FROM (SELECT assetId, COUNT(*) AS duplicateCount FROM raw.postingAsset GROUP BY assetId HAVING COUNT(*) > 1)))::BIGINT AS violationCount
UNION ALL
SELECT 'raw.ocrResult' AS tableName, ((SELECT COUNT(*) FROM raw.ocrResult WHERE ocrId IS NULL) + (SELECT COUNT(*) FROM (SELECT ocrId, COUNT(*) AS duplicateCount FROM raw.ocrResult GROUP BY ocrId HAVING COUNT(*) > 1)))::BIGINT AS violationCount
UNION ALL
SELECT 'core.postingNormalized' AS tableName, ((SELECT COUNT(*) FROM core.postingNormalized WHERE postingId IS NULL) + (SELECT COUNT(*) FROM (SELECT postingId, COUNT(*) AS duplicateCount FROM core.postingNormalized GROUP BY postingId HAVING COUNT(*) > 1)))::BIGINT AS violationCount
UNION ALL
SELECT 'core.postingTrack' AS tableName, ((SELECT COUNT(*) FROM core.postingTrack WHERE trackId IS NULL) + (SELECT COUNT(*) FROM (SELECT trackId, COUNT(*) AS duplicateCount FROM core.postingTrack GROUP BY trackId HAVING COUNT(*) > 1)))::BIGINT AS violationCount
UNION ALL
SELECT 'core.postingSection' AS tableName, ((SELECT COUNT(*) FROM core.postingSection WHERE sectionId IS NULL) + (SELECT COUNT(*) FROM (SELECT sectionId, COUNT(*) AS duplicateCount FROM core.postingSection GROUP BY sectionId HAVING COUNT(*) > 1)))::BIGINT AS violationCount
UNION ALL
SELECT 'core.requirementFact' AS tableName, ((SELECT COUNT(*) FROM core.requirementFact WHERE requirementId IS NULL) + (SELECT COUNT(*) FROM (SELECT requirementId, COUNT(*) AS duplicateCount FROM core.requirementFact GROUP BY requirementId HAVING COUNT(*) > 1)))::BIGINT AS violationCount
UNION ALL
SELECT 'core.careerLabel' AS tableName, ((SELECT COUNT(*) FROM core.careerLabel WHERE trackId IS NULL) + (SELECT COUNT(*) FROM (SELECT trackId, COUNT(*) AS duplicateCount FROM core.careerLabel GROUP BY trackId HAVING COUNT(*) > 1)))::BIGINT AS violationCount
UNION ALL
SELECT 'core.postingDedupEdge' AS tableName, ((SELECT COUNT(*) FROM core.postingDedupEdge WHERE edgeId IS NULL) + (SELECT COUNT(*) FROM (SELECT edgeId, COUNT(*) AS duplicateCount FROM core.postingDedupEdge GROUP BY edgeId HAVING COUNT(*) > 1)))::BIGINT AS violationCount
UNION ALL
SELECT 'ncs.ncsUnit' AS tableName, ((SELECT COUNT(*) FROM ncs.ncsUnit WHERE ncsUnitCode IS NULL) + (SELECT COUNT(*) FROM (SELECT ncsUnitCode, COUNT(*) AS duplicateCount FROM ncs.ncsUnit GROUP BY ncsUnitCode HAVING COUNT(*) > 1)))::BIGINT AS violationCount
UNION ALL
SELECT 'ncs.ncsLearningModule' AS tableName, ((SELECT COUNT(*) FROM ncs.ncsLearningModule WHERE moduleId IS NULL) + (SELECT COUNT(*) FROM (SELECT moduleId, COUNT(*) AS duplicateCount FROM ncs.ncsLearningModule GROUP BY moduleId HAVING COUNT(*) > 1)))::BIGINT AS violationCount
UNION ALL
SELECT 'ncs.postingNcsMatch' AS tableName, ((SELECT COUNT(*) FROM ncs.postingNcsMatch WHERE matchId IS NULL) + (SELECT COUNT(*) FROM (SELECT matchId, COUNT(*) AS duplicateCount FROM ncs.postingNcsMatch GROUP BY matchId HAVING COUNT(*) > 1)))::BIGINT AS violationCount
UNION ALL
SELECT 'mart.postingAnalysisMart' AS tableName, ((SELECT COUNT(*) FROM mart.postingAnalysisMart WHERE trackId IS NULL) + (SELECT COUNT(*) FROM (SELECT trackId, COUNT(*) AS duplicateCount FROM mart.postingAnalysisMart GROUP BY trackId HAVING COUNT(*) > 1)))::BIGINT AS violationCount
UNION ALL
SELECT 'mart.timeSeriesMart' AS tableName, ((SELECT COUNT(*) FROM mart.timeSeriesMart WHERE periodMonth IS NULL OR cohortType IS NULL OR jobCodeLevel IS NULL OR jobCode IS NULL OR dedupApplied IS NULL) + (SELECT COUNT(*) FROM (SELECT periodMonth, cohortType, jobCodeLevel, jobCode, dedupApplied, COUNT(*) AS duplicateCount FROM mart.timeSeriesMart GROUP BY periodMonth, cohortType, jobCodeLevel, jobCode, dedupApplied HAVING COUNT(*) > 1)))::BIGINT AS violationCount
UNION ALL
SELECT 'mart.caseStudyRegistry' AS tableName, ((SELECT COUNT(*) FROM mart.caseStudyRegistry WHERE caseId IS NULL) + (SELECT COUNT(*) FROM (SELECT caseId, COUNT(*) AS duplicateCount FROM mart.caseStudyRegistry GROUP BY caseId HAVING COUNT(*) > 1)))::BIGINT AS violationCount
UNION ALL
SELECT 'mart.similarityPair' AS tableName, ((SELECT COUNT(*) FROM mart.similarityPair WHERE pairId IS NULL) + (SELECT COUNT(*) FROM (SELECT pairId, COUNT(*) AS duplicateCount FROM mart.similarityPair GROUP BY pairId HAVING COUNT(*) > 1)))::BIGINT AS violationCount
UNION ALL
SELECT 'qa.monthlyCoverageAudit' AS tableName, ((SELECT COUNT(*) FROM qa.monthlyCoverageAudit WHERE periodMonth IS NULL OR sourceName IS NULL OR auditVersion IS NULL) + (SELECT COUNT(*) FROM (SELECT periodMonth, sourceName, auditVersion, COUNT(*) AS duplicateCount FROM qa.monthlyCoverageAudit GROUP BY periodMonth, sourceName, auditVersion HAVING COUNT(*) > 1)))::BIGINT AS violationCount
UNION ALL
SELECT 'qa.sourcePolicyAudit' AS tableName, ((SELECT COUNT(*) FROM qa.sourcePolicyAudit WHERE sourceName IS NULL OR policyVersion IS NULL) + (SELECT COUNT(*) FROM (SELECT sourceName, policyVersion, COUNT(*) AS duplicateCount FROM qa.sourcePolicyAudit GROUP BY sourceName, policyVersion HAVING COUNT(*) > 1)))::BIGINT AS violationCount
UNION ALL
SELECT 'qa.goldSample' AS tableName, ((SELECT COUNT(*) FROM qa.goldSample WHERE goldId IS NULL) + (SELECT COUNT(*) FROM (SELECT goldId, COUNT(*) AS duplicateCount FROM qa.goldSample GROUP BY goldId HAVING COUNT(*) > 1)))::BIGINT AS violationCount
UNION ALL
SELECT 'qa.evalRun' AS tableName, ((SELECT COUNT(*) FROM qa.evalRun WHERE evalRunId IS NULL) + (SELECT COUNT(*) FROM (SELECT evalRunId, COUNT(*) AS duplicateCount FROM qa.evalRun GROUP BY evalRunId HAVING COUNT(*) > 1)))::BIGINT AS violationCount
UNION ALL
SELECT 'qa.resultManifest' AS tableName, ((SELECT COUNT(*) FROM qa.resultManifest WHERE metricId IS NULL) + (SELECT COUNT(*) FROM (SELECT metricId, COUNT(*) AS duplicateCount FROM qa.resultManifest GROUP BY metricId HAVING COUNT(*) > 1)))::BIGINT AS violationCount
UNION ALL
SELECT 'qa.decisionLog' AS tableName, ((SELECT COUNT(*) FROM qa.decisionLog WHERE decisionId IS NULL) + (SELECT COUNT(*) FROM (SELECT decisionId, COUNT(*) AS duplicateCount FROM qa.decisionLog GROUP BY decisionId HAVING COUNT(*) > 1)))::BIGINT AS violationCount;

CREATE OR REPLACE VIEW qa.vForeignKeyViolations AS
SELECT 'raw.crawlRun.sourceName->raw.sourceRegistry.sourceName' AS relationship, COUNT(*)::BIGINT AS violationCount FROM raw.crawlRun child WHERE child.sourceName IS NOT NULL AND NOT EXISTS (SELECT 1 FROM raw.sourceRegistry parent WHERE parent.sourceName = child.sourceName)
UNION ALL
SELECT 'raw.linkareerIndexRaw.crawlRunId->raw.crawlRun.crawlRunId' AS relationship, COUNT(*)::BIGINT AS violationCount FROM raw.linkareerIndexRaw child WHERE child.crawlRunId IS NOT NULL AND NOT EXISTS (SELECT 1 FROM raw.crawlRun parent WHERE parent.crawlRunId = child.crawlRunId)
UNION ALL
SELECT 'raw.linkareerPostingRaw.indexItemId->raw.linkareerIndexRaw.indexItemId' AS relationship, COUNT(*)::BIGINT AS violationCount FROM raw.linkareerPostingRaw child WHERE child.indexItemId IS NOT NULL AND NOT EXISTS (SELECT 1 FROM raw.linkareerIndexRaw parent WHERE parent.indexItemId = child.indexItemId)
UNION ALL
SELECT 'raw.postingAsset.rawPostingId->raw.linkareerPostingRaw.rawPostingId' AS relationship, COUNT(*)::BIGINT AS violationCount FROM raw.postingAsset child WHERE child.rawPostingId IS NOT NULL AND NOT EXISTS (SELECT 1 FROM raw.linkareerPostingRaw parent WHERE parent.rawPostingId = child.rawPostingId)
UNION ALL
SELECT 'raw.ocrResult.assetId->raw.postingAsset.assetId' AS relationship, COUNT(*)::BIGINT AS violationCount FROM raw.ocrResult child WHERE child.assetId IS NOT NULL AND NOT EXISTS (SELECT 1 FROM raw.postingAsset parent WHERE parent.assetId = child.assetId)
UNION ALL
SELECT 'core.postingNormalized.rawPostingId->raw.linkareerPostingRaw.rawPostingId' AS relationship, COUNT(*)::BIGINT AS violationCount FROM core.postingNormalized child WHERE child.rawPostingId IS NOT NULL AND NOT EXISTS (SELECT 1 FROM raw.linkareerPostingRaw parent WHERE parent.rawPostingId = child.rawPostingId)
UNION ALL
SELECT 'core.postingTrack.postingId->core.postingNormalized.postingId' AS relationship, COUNT(*)::BIGINT AS violationCount FROM core.postingTrack child WHERE child.postingId IS NOT NULL AND NOT EXISTS (SELECT 1 FROM core.postingNormalized parent WHERE parent.postingId = child.postingId)
UNION ALL
SELECT 'core.postingSection.trackId->core.postingTrack.trackId' AS relationship, COUNT(*)::BIGINT AS violationCount FROM core.postingSection child WHERE child.trackId IS NOT NULL AND NOT EXISTS (SELECT 1 FROM core.postingTrack parent WHERE parent.trackId = child.trackId)
UNION ALL
SELECT 'core.requirementFact.sectionId->core.postingSection.sectionId' AS relationship, COUNT(*)::BIGINT AS violationCount FROM core.requirementFact child WHERE child.sectionId IS NOT NULL AND NOT EXISTS (SELECT 1 FROM core.postingSection parent WHERE parent.sectionId = child.sectionId)
UNION ALL
SELECT 'core.careerLabel.trackId->core.postingTrack.trackId' AS relationship, COUNT(*)::BIGINT AS violationCount FROM core.careerLabel child WHERE child.trackId IS NOT NULL AND NOT EXISTS (SELECT 1 FROM core.postingTrack parent WHERE parent.trackId = child.trackId)
UNION ALL
SELECT 'core.postingDedupEdge.leftPostingId->core.postingNormalized.postingId' AS relationship, COUNT(*)::BIGINT AS violationCount FROM core.postingDedupEdge child WHERE child.leftPostingId IS NOT NULL AND NOT EXISTS (SELECT 1 FROM core.postingNormalized parent WHERE parent.postingId = child.leftPostingId)
UNION ALL
SELECT 'core.postingDedupEdge.rightPostingId->core.postingNormalized.postingId' AS relationship, COUNT(*)::BIGINT AS violationCount FROM core.postingDedupEdge child WHERE child.rightPostingId IS NOT NULL AND NOT EXISTS (SELECT 1 FROM core.postingNormalized parent WHERE parent.postingId = child.rightPostingId)
UNION ALL
SELECT 'ncs.ncsLearningModule.ncsUnitCode->ncs.ncsUnit.ncsUnitCode' AS relationship, COUNT(*)::BIGINT AS violationCount FROM ncs.ncsLearningModule child WHERE child.ncsUnitCode IS NOT NULL AND NOT EXISTS (SELECT 1 FROM ncs.ncsUnit parent WHERE parent.ncsUnitCode = child.ncsUnitCode)
UNION ALL
SELECT 'ncs.postingNcsMatch.trackId->core.postingTrack.trackId' AS relationship, COUNT(*)::BIGINT AS violationCount FROM ncs.postingNcsMatch child WHERE child.trackId IS NOT NULL AND NOT EXISTS (SELECT 1 FROM core.postingTrack parent WHERE parent.trackId = child.trackId)
UNION ALL
SELECT 'ncs.postingNcsMatch.ncsUnitCode->ncs.ncsUnit.ncsUnitCode' AS relationship, COUNT(*)::BIGINT AS violationCount FROM ncs.postingNcsMatch child WHERE child.ncsUnitCode IS NOT NULL AND NOT EXISTS (SELECT 1 FROM ncs.ncsUnit parent WHERE parent.ncsUnitCode = child.ncsUnitCode)
UNION ALL
SELECT 'qa.sourcePolicyAudit.sourceName->raw.sourceRegistry.sourceName' AS relationship, COUNT(*)::BIGINT AS violationCount FROM qa.sourcePolicyAudit child WHERE child.sourceName IS NOT NULL AND NOT EXISTS (SELECT 1 FROM raw.sourceRegistry parent WHERE parent.sourceName = child.sourceName);

CREATE OR REPLACE VIEW qa.vEnumViolations AS
SELECT 'raw.queryRegistry' AS tableName, 'transportType' AS columnName, COUNT(*)::BIGINT AS violationCount FROM raw.queryRegistry WHERE transportType IS NOT NULL AND transportType NOT IN ('graphqlApq', 'nextDataSsr', 'apolloCache', 'html')
UNION ALL
SELECT 'raw.queryRegistry' AS tableName, 'httpMethod' AS columnName, COUNT(*)::BIGINT AS violationCount FROM raw.queryRegistry WHERE httpMethod IS NOT NULL AND httpMethod NOT IN ('GET', 'POST')
UNION ALL
SELECT 'raw.queryRegistry' AS tableName, 'verificationStatus' AS columnName, COUNT(*)::BIGINT AS violationCount FROM raw.queryRegistry WHERE verificationStatus IS NOT NULL AND verificationStatus NOT IN ('verified', 'stale', 'failed', 'pending')
UNION ALL
SELECT 'raw.sourceRegistry' AS tableName, 'sourceName' AS columnName, COUNT(*)::BIGINT AS violationCount FROM raw.sourceRegistry WHERE sourceName IS NOT NULL AND sourceName NOT IN ('linkareer', 'ncs')
UNION ALL
SELECT 'raw.sourceRegistry' AS tableName, 'sourceType' AS columnName, COUNT(*)::BIGINT AS violationCount FROM raw.sourceRegistry WHERE sourceType IS NOT NULL AND sourceType NOT IN ('web', 'api', 'fileDownload')
UNION ALL
SELECT 'raw.sourceRegistry' AS tableName, 'sourceRole' AS columnName, COUNT(*)::BIGINT AS violationCount FROM raw.sourceRegistry WHERE sourceRole IS NOT NULL AND sourceRole NOT IN ('posting', 'competency')
UNION ALL
SELECT 'raw.sourceRegistry' AS tableName, 'termsStatus' AS columnName, COUNT(*)::BIGINT AS violationCount FROM raw.sourceRegistry WHERE termsStatus IS NOT NULL AND termsStatus NOT IN ('reviewedConditional', 'permissionGranted', 'permitted', 'restricted', 'unverified')
UNION ALL
SELECT 'raw.sourceRegistry' AS tableName, 'robotsStatus' AS columnName, COUNT(*)::BIGINT AS violationCount FROM raw.sourceRegistry WHERE robotsStatus IS NOT NULL AND robotsStatus NOT IN ('allowed', 'restricted', 'notApplicable', 'unverified')
UNION ALL
SELECT 'raw.sourceRegistry' AS tableName, 'historyStatus' AS columnName, COUNT(*)::BIGINT AS violationCount FROM raw.sourceRegistry WHERE historyStatus IS NOT NULL AND historyStatus NOT IN ('confirmed', 'partial', 'unavailable', 'unverified')
UNION ALL
SELECT 'raw.sourceRegistry' AS tableName, 'paginationType' AS columnName, COUNT(*)::BIGINT AS violationCount FROM raw.sourceRegistry WHERE paginationType IS NOT NULL AND paginationType NOT IN ('page', 'cursor', 'infiniteScroll', 'internalJson', 'unknown')
UNION ALL
SELECT 'raw.crawlRun' AS tableName, 'status' AS columnName, COUNT(*)::BIGINT AS violationCount FROM raw.crawlRun WHERE status IS NOT NULL AND status NOT IN ('running', 'completed', 'aborted', 'failed', 'partial')
UNION ALL
SELECT 'raw.postingAsset' AS tableName, 'assetType' AS columnName, COUNT(*)::BIGINT AS violationCount FROM raw.postingAsset WHERE assetType IS NOT NULL AND assetType NOT IN ('image', 'pdf', 'attachment', 'other')
UNION ALL
SELECT 'core.postingNormalized' AS tableName, 'postingKind' AS columnName, COUNT(*)::BIGINT AS violationCount FROM core.postingNormalized WHERE postingKind IS NOT NULL AND postingKind NOT IN ('recruitIntern', 'recruitNewGrad', 'recruitExperienced', 'recruitUnknown', 'contest', 'extracurricular', 'education', 'club', 'volunteer', 'other')
UNION ALL
SELECT 'core.postingNormalized' AS tableName, 'recruitmentScope' AS columnName, COUNT(*)::BIGINT AS violationCount FROM core.postingNormalized WHERE recruitmentScope IS NOT NULL AND recruitmentScope NOT IN ('entryOnly', 'internOnly', 'experiencedOnly', 'entryInternMixed', 'entryExperiencedMixed', 'internExperiencedMixed', 'allMixed', 'mixedUnresolved', 'unknown')
UNION ALL
SELECT 'core.postingNormalized' AS tableName, 'rq2ExclusionReason' AS columnName, COUNT(*)::BIGINT AS violationCount FROM core.postingNormalized WHERE rq2ExclusionReason IS NOT NULL AND rq2ExclusionReason NOT IN ('activityTextMissing', 'externalAtsBodyUnavailable', 'boundaryUnresolved', 'trackUnresolved', 'textTooShort', 'nonRecruitPosting', 'other')
UNION ALL
SELECT 'core.postingTrack' AS tableName, 'trackType' AS columnName, COUNT(*)::BIGINT AS violationCount FROM core.postingTrack WHERE trackType IS NOT NULL AND trackType NOT IN ('entry', 'intern', 'experienced', 'mixedUnresolved', 'unknown')
UNION ALL
SELECT 'core.postingTrack' AS tableName, 'recruitmentScope' AS columnName, COUNT(*)::BIGINT AS violationCount FROM core.postingTrack WHERE recruitmentScope IS NOT NULL AND recruitmentScope NOT IN ('entryOnly', 'internOnly', 'experiencedOnly', 'entryInternMixed', 'entryExperiencedMixed', 'internExperiencedMixed', 'allMixed', 'mixedUnresolved', 'unknown')
UNION ALL
SELECT 'core.postingTrack' AS tableName, 'jobTypeSource' AS columnName, COUNT(*)::BIGINT AS violationCount FROM core.postingTrack WHERE jobTypeSource IS NOT NULL AND jobTypeSource NOT IN ('dutiesJobType', 'jobTypes', 'detailText', 'unresolved')
UNION ALL
SELECT 'core.postingSection' AS tableName, 'sectionType' AS columnName, COUNT(*)::BIGINT AS violationCount FROM core.postingSection WHERE sectionType IS NOT NULL AND sectionType NOT IN ('title', 'duty', 'required', 'preferred', 'qualification', 'process', 'condition', 'benefit', 'company', 'other')
UNION ALL
SELECT 'core.postingSection' AS tableName, 'sourceMode' AS columnName, COUNT(*)::BIGINT AS violationCount FROM core.postingSection WHERE sourceMode IS NOT NULL AND sourceMode NOT IN ('html', 'ocr', 'merged')
UNION ALL
SELECT 'core.requirementFact' AS tableName, 'requirementType' AS columnName, COUNT(*)::BIGINT AS violationCount FROM core.requirementFact WHERE requirementType IS NOT NULL AND requirementType NOT IN ('careerMonths', 'priorExperience', 'portfolio', 'project', 'certificate', 'degree', 'major', 'skill', 'tool', 'language', 'duty', 'other')
UNION ALL
SELECT 'core.requirementFact' AS tableName, 'obligation' AS columnName, COUNT(*)::BIGINT AS violationCount FROM core.requirementFact WHERE obligation IS NOT NULL AND obligation NOT IN ('required', 'preferred', 'unknown')
UNION ALL
SELECT 'core.requirementFact' AS tableName, 'certificateClass' AS columnName, COUNT(*)::BIGINT AS violationCount FROM core.requirementFact WHERE certificateClass IS NOT NULL AND certificateClass NOT IN ('craftsman', 'industrialEngineer', 'engineer', 'masterCraftsman', 'professionalEngineer', 'otherNational')
UNION ALL
SELECT 'core.requirementFact' AS tableName, 'degreeLevel' AS columnName, COUNT(*)::BIGINT AS violationCount FROM core.requirementFact WHERE degreeLevel IS NOT NULL AND degreeLevel NOT IN ('highSchool', 'associate', 'bachelor', 'master', 'doctor')
UNION ALL
SELECT 'core.careerLabel' AS tableName, 'careerClass' AS columnName, COUNT(*)::BIGINT AS violationCount FROM core.careerLabel WHERE careerClass IS NOT NULL AND careerClass NOT IN ('E0', 'E1', 'E2', 'E3', 'U')
UNION ALL
SELECT 'core.careerLabel' AS tableName, 'internAccessClass' AS columnName, COUNT(*)::BIGINT AS violationCount FROM core.careerLabel WHERE internAccessClass IS NOT NULL AND internAccessClass NOT IN ('I0', 'I1', 'IU')
UNION ALL
SELECT 'core.postingDedupEdge' AS tableName, 'decision' AS columnName, COUNT(*)::BIGINT AS violationCount FROM core.postingDedupEdge WHERE decision IS NOT NULL AND decision NOT IN ('sameGroup', 'distinct', 'undecided')
UNION ALL
SELECT 'ncs.ncsUnit' AS tableName, 'ncsBand' AS columnName, COUNT(*)::BIGINT AS violationCount FROM ncs.ncsUnit WHERE ncsBand IS NOT NULL AND ncsBand NOT IN ('level1to2', 'level3to4', 'level5to6', 'level7to8')
UNION ALL
SELECT 'ncs.postingNcsMatch' AS tableName, 'ncsBand' AS columnName, COUNT(*)::BIGINT AS violationCount FROM ncs.postingNcsMatch WHERE ncsBand IS NOT NULL AND ncsBand NOT IN ('level1to2', 'level3to4', 'level5to6', 'level7to8')
UNION ALL
SELECT 'ncs.postingNcsMatch' AS tableName, 'mappingBasis' AS columnName, COUNT(*)::BIGINT AS violationCount FROM ncs.postingNcsMatch WHERE mappingBasis IS NOT NULL AND mappingBasis NOT IN ('ncsUnitDirect', 'ncsPerformanceCriteria', 'ncsLearningModule', 'dictionaryRule', 'semanticMatch')
UNION ALL
SELECT 'ncs.postingNcsMatch' AS tableName, 'ncsConfidenceTier' AS columnName, COUNT(*)::BIGINT AS violationCount FROM ncs.postingNcsMatch WHERE ncsConfidenceTier IS NOT NULL AND ncsConfidenceTier NOT IN ('high', 'medium', 'low')
UNION ALL
SELECT 'mart.postingAnalysisMart' AS tableName, 'sourceName' AS columnName, COUNT(*)::BIGINT AS violationCount FROM mart.postingAnalysisMart WHERE sourceName IS NOT NULL AND sourceName NOT IN ('linkareer')
UNION ALL
SELECT 'mart.postingAnalysisMart' AS tableName, 'cohortType' AS columnName, COUNT(*)::BIGINT AS violationCount FROM mart.postingAnalysisMart WHERE cohortType IS NOT NULL AND cohortType NOT IN ('coreAiIt', 'allJobs')
UNION ALL
SELECT 'mart.postingAnalysisMart' AS tableName, 'jobCodeLevel' AS columnName, COUNT(*)::BIGINT AS violationCount FROM mart.postingAnalysisMart WHERE jobCodeLevel IS NOT NULL AND jobCodeLevel NOT IN ('all', 'major', 'middle', 'minor', 'sub')
UNION ALL
SELECT 'mart.postingAnalysisMart' AS tableName, 'postingKind' AS columnName, COUNT(*)::BIGINT AS violationCount FROM mart.postingAnalysisMart WHERE postingKind IS NOT NULL AND postingKind NOT IN ('recruitIntern', 'recruitNewGrad', 'recruitExperienced', 'recruitUnknown', 'contest', 'extracurricular', 'education', 'club', 'volunteer', 'other')
UNION ALL
SELECT 'mart.postingAnalysisMart' AS tableName, 'rq2ExclusionReason' AS columnName, COUNT(*)::BIGINT AS violationCount FROM mart.postingAnalysisMart WHERE rq2ExclusionReason IS NOT NULL AND rq2ExclusionReason NOT IN ('activityTextMissing', 'externalAtsBodyUnavailable', 'boundaryUnresolved', 'trackUnresolved', 'textTooShort', 'nonRecruitPosting', 'other')
UNION ALL
SELECT 'mart.postingAnalysisMart' AS tableName, 'trackType' AS columnName, COUNT(*)::BIGINT AS violationCount FROM mart.postingAnalysisMart WHERE trackType IS NOT NULL AND trackType NOT IN ('entry', 'intern', 'experienced', 'mixedUnresolved', 'unknown')
UNION ALL
SELECT 'mart.postingAnalysisMart' AS tableName, 'recruitmentScope' AS columnName, COUNT(*)::BIGINT AS violationCount FROM mart.postingAnalysisMart WHERE recruitmentScope IS NOT NULL AND recruitmentScope NOT IN ('entryOnly', 'internOnly', 'experiencedOnly', 'entryInternMixed', 'entryExperiencedMixed', 'internExperiencedMixed', 'allMixed', 'mixedUnresolved', 'unknown')
UNION ALL
SELECT 'mart.postingAnalysisMart' AS tableName, 'careerClass' AS columnName, COUNT(*)::BIGINT AS violationCount FROM mart.postingAnalysisMart WHERE careerClass IS NOT NULL AND careerClass NOT IN ('E0', 'E1', 'E2', 'E3', 'U')
UNION ALL
SELECT 'mart.postingAnalysisMart' AS tableName, 'internAccessClass' AS columnName, COUNT(*)::BIGINT AS violationCount FROM mart.postingAnalysisMart WHERE internAccessClass IS NOT NULL AND internAccessClass NOT IN ('I0', 'I1', 'IU')
UNION ALL
SELECT 'mart.postingAnalysisMart' AS tableName, 'ncsBandPrimary' AS columnName, COUNT(*)::BIGINT AS violationCount FROM mart.postingAnalysisMart WHERE ncsBandPrimary IS NOT NULL AND ncsBandPrimary NOT IN ('level1to2', 'level3to4', 'level5to6', 'level7to8')
UNION ALL
SELECT 'mart.postingAnalysisMart' AS tableName, 'ncsConfidenceTier' AS columnName, COUNT(*)::BIGINT AS violationCount FROM mart.postingAnalysisMart WHERE ncsConfidenceTier IS NOT NULL AND ncsConfidenceTier NOT IN ('high', 'medium', 'low')
UNION ALL
SELECT 'mart.postingAnalysisMart' AS tableName, 'scoreStatus' AS columnName, COUNT(*)::BIGINT AS violationCount FROM mart.postingAnalysisMart WHERE scoreStatus IS NOT NULL AND scoreStatus NOT IN ('reserved')
UNION ALL
SELECT 'mart.timeSeriesMart' AS tableName, 'cohortType' AS columnName, COUNT(*)::BIGINT AS violationCount FROM mart.timeSeriesMart WHERE cohortType IS NOT NULL AND cohortType NOT IN ('coreAiIt', 'allJobs')
UNION ALL
SELECT 'mart.timeSeriesMart' AS tableName, 'jobCodeLevel' AS columnName, COUNT(*)::BIGINT AS violationCount FROM mart.timeSeriesMart WHERE jobCodeLevel IS NOT NULL AND jobCodeLevel NOT IN ('all', 'major', 'middle', 'minor', 'sub')
UNION ALL
SELECT 'mart.timeSeriesMart' AS tableName, 'coverageStatus' AS columnName, COUNT(*)::BIGINT AS violationCount FROM mart.timeSeriesMart WHERE coverageStatus IS NOT NULL AND coverageStatus NOT IN ('complete', 'partial', 'insufficient', 'excluded', 'unverified')
UNION ALL
SELECT 'mart.similarityPair' AS tableName, 'comparisonType' AS columnName, COUNT(*)::BIGINT AS violationCount FROM mart.similarityPair WHERE comparisonType IS NOT NULL AND comparisonType NOT IN ('entry', 'experienced')
UNION ALL
SELECT 'qa.monthlyCoverageAudit' AS tableName, 'coverageStatus' AS columnName, COUNT(*)::BIGINT AS violationCount FROM qa.monthlyCoverageAudit WHERE coverageStatus IS NOT NULL AND coverageStatus NOT IN ('complete', 'partial', 'insufficient', 'excluded', 'unverified')
UNION ALL
SELECT 'qa.monthlyCoverageAudit' AS tableName, 'coverageReason' AS columnName, COUNT(*)::BIGINT AS violationCount FROM qa.monthlyCoverageAudit WHERE coverageReason IS NOT NULL AND coverageReason NOT IN ('completeObserved', 'partialMonth', 'platformPreLaunch', 'historicalLoss', 'paginationUnverified', 'sourceChange', 'policyBlocked', 'other', 'unverified')
UNION ALL
SELECT 'qa.monthlyCoverageAudit' AS tableName, 'platformCoverageRegime' AS columnName, COUNT(*)::BIGINT AS violationCount FROM qa.monthlyCoverageAudit WHERE platformCoverageRegime IS NOT NULL AND platformCoverageRegime NOT IN ('preStableRecruitService', 'stableRecruitService', 'sourceDesignChange', 'unknown')
UNION ALL
SELECT 'qa.sourcePolicyAudit' AS tableName, 'robotsStatus' AS columnName, COUNT(*)::BIGINT AS violationCount FROM qa.sourcePolicyAudit WHERE robotsStatus IS NOT NULL AND robotsStatus NOT IN ('allowed', 'restricted', 'notApplicable', 'unverified')
UNION ALL
SELECT 'qa.sourcePolicyAudit' AS tableName, 'termsStatus' AS columnName, COUNT(*)::BIGINT AS violationCount FROM qa.sourcePolicyAudit WHERE termsStatus IS NOT NULL AND termsStatus NOT IN ('reviewedConditional', 'permissionGranted', 'permitted', 'restricted', 'unverified')
UNION ALL
SELECT 'qa.sourcePolicyAudit' AS tableName, 'clientAccessMode' AS columnName, COUNT(*)::BIGINT AS violationCount FROM qa.sourcePolicyAudit WHERE clientAccessMode IS NOT NULL AND clientAccessMode NOT IN ('transparentHttp', 'documentedBrowser', 'impersonatedOnly', 'unverified')
UNION ALL
SELECT 'qa.sourcePolicyAudit' AS tableName, 'reviewerStatus' AS columnName, COUNT(*)::BIGINT AS violationCount FROM qa.sourcePolicyAudit WHERE reviewerStatus IS NOT NULL AND reviewerStatus NOT IN ('pending', 'reviewed', 'approved', 'rejected')
UNION ALL
SELECT 'qa.resultManifest' AS tableName, 'cohortType' AS columnName, COUNT(*)::BIGINT AS violationCount FROM qa.resultManifest WHERE cohortType IS NOT NULL AND cohortType NOT IN ('coreAiIt', 'allJobs');

CREATE OR REPLACE VIEW qa.vNullabilityViolations AS
SELECT 'raw.queryRegistry' AS tableName, 'operationName' AS columnName, COUNT(*)::BIGINT AS violationCount FROM raw.queryRegistry WHERE operationName IS NULL
UNION ALL
SELECT 'raw.queryRegistry' AS tableName, 'sha256Hash' AS columnName, COUNT(*)::BIGINT AS violationCount FROM raw.queryRegistry WHERE sha256Hash IS NULL
UNION ALL
SELECT 'raw.queryRegistry' AS tableName, 'transportType' AS columnName, COUNT(*)::BIGINT AS violationCount FROM raw.queryRegistry WHERE transportType IS NULL
UNION ALL
SELECT 'raw.queryRegistry' AS tableName, 'httpMethod' AS columnName, COUNT(*)::BIGINT AS violationCount FROM raw.queryRegistry WHERE httpMethod IS NULL
UNION ALL
SELECT 'raw.queryRegistry' AS tableName, 'discoveredAt' AS columnName, COUNT(*)::BIGINT AS violationCount FROM raw.queryRegistry WHERE discoveredAt IS NULL
UNION ALL
SELECT 'raw.queryRegistry' AS tableName, 'lastVerifiedAt' AS columnName, COUNT(*)::BIGINT AS violationCount FROM raw.queryRegistry WHERE lastVerifiedAt IS NULL
UNION ALL
SELECT 'raw.queryRegistry' AS tableName, 'activeFlag' AS columnName, COUNT(*)::BIGINT AS violationCount FROM raw.queryRegistry WHERE activeFlag IS NULL
UNION ALL
SELECT 'raw.queryRegistry' AS tableName, 'verificationStatus' AS columnName, COUNT(*)::BIGINT AS violationCount FROM raw.queryRegistry WHERE verificationStatus IS NULL
UNION ALL
SELECT 'raw.sourceRegistry' AS tableName, 'sourceName' AS columnName, COUNT(*)::BIGINT AS violationCount FROM raw.sourceRegistry WHERE sourceName IS NULL
UNION ALL
SELECT 'raw.sourceRegistry' AS tableName, 'sourceType' AS columnName, COUNT(*)::BIGINT AS violationCount FROM raw.sourceRegistry WHERE sourceType IS NULL
UNION ALL
SELECT 'raw.sourceRegistry' AS tableName, 'sourceRole' AS columnName, COUNT(*)::BIGINT AS violationCount FROM raw.sourceRegistry WHERE sourceRole IS NULL
UNION ALL
SELECT 'raw.sourceRegistry' AS tableName, 'baseUrl' AS columnName, COUNT(*)::BIGINT AS violationCount FROM raw.sourceRegistry WHERE baseUrl IS NULL
UNION ALL
SELECT 'raw.sourceRegistry' AS tableName, 'termsStatus' AS columnName, COUNT(*)::BIGINT AS violationCount FROM raw.sourceRegistry WHERE termsStatus IS NULL
UNION ALL
SELECT 'raw.sourceRegistry' AS tableName, 'robotsStatus' AS columnName, COUNT(*)::BIGINT AS violationCount FROM raw.sourceRegistry WHERE robotsStatus IS NULL
UNION ALL
SELECT 'raw.sourceRegistry' AS tableName, 'historyStatus' AS columnName, COUNT(*)::BIGINT AS violationCount FROM raw.sourceRegistry WHERE historyStatus IS NULL
UNION ALL
SELECT 'raw.crawlRun' AS tableName, 'crawlRunId' AS columnName, COUNT(*)::BIGINT AS violationCount FROM raw.crawlRun WHERE crawlRunId IS NULL
UNION ALL
SELECT 'raw.crawlRun' AS tableName, 'sourceName' AS columnName, COUNT(*)::BIGINT AS violationCount FROM raw.crawlRun WHERE sourceName IS NULL
UNION ALL
SELECT 'raw.crawlRun' AS tableName, 'runPhase' AS columnName, COUNT(*)::BIGINT AS violationCount FROM raw.crawlRun WHERE runPhase IS NULL
UNION ALL
SELECT 'raw.crawlRun' AS tableName, 'collectorVersion' AS columnName, COUNT(*)::BIGINT AS violationCount FROM raw.crawlRun WHERE collectorVersion IS NULL
UNION ALL
SELECT 'raw.crawlRun' AS tableName, 'configSha256' AS columnName, COUNT(*)::BIGINT AS violationCount FROM raw.crawlRun WHERE configSha256 IS NULL
UNION ALL
SELECT 'raw.crawlRun' AS tableName, 'startedAt' AS columnName, COUNT(*)::BIGINT AS violationCount FROM raw.crawlRun WHERE startedAt IS NULL
UNION ALL
SELECT 'raw.crawlRun' AS tableName, 'status' AS columnName, COUNT(*)::BIGINT AS violationCount FROM raw.crawlRun WHERE status IS NULL
UNION ALL
SELECT 'raw.crawlRun' AS tableName, 'requestCount' AS columnName, COUNT(*)::BIGINT AS violationCount FROM raw.crawlRun WHERE requestCount IS NULL
UNION ALL
SELECT 'raw.crawlRun' AS tableName, 'successCount' AS columnName, COUNT(*)::BIGINT AS violationCount FROM raw.crawlRun WHERE successCount IS NULL
UNION ALL
SELECT 'raw.crawlRun' AS tableName, 'failCount' AS columnName, COUNT(*)::BIGINT AS violationCount FROM raw.crawlRun WHERE failCount IS NULL
UNION ALL
SELECT 'raw.linkareerIndexRaw' AS tableName, 'indexItemId' AS columnName, COUNT(*)::BIGINT AS violationCount FROM raw.linkareerIndexRaw WHERE indexItemId IS NULL
UNION ALL
SELECT 'raw.linkareerIndexRaw' AS tableName, 'crawlRunId' AS columnName, COUNT(*)::BIGINT AS violationCount FROM raw.linkareerIndexRaw WHERE crawlRunId IS NULL
UNION ALL
SELECT 'raw.linkareerIndexRaw' AS tableName, 'discoveryType' AS columnName, COUNT(*)::BIGINT AS violationCount FROM raw.linkareerIndexRaw WHERE discoveryType IS NULL
UNION ALL
SELECT 'raw.linkareerIndexRaw' AS tableName, 'detailUrl' AS columnName, COUNT(*)::BIGINT AS violationCount FROM raw.linkareerIndexRaw WHERE detailUrl IS NULL
UNION ALL
SELECT 'raw.linkareerIndexRaw' AS tableName, 'activityTypeId' AS columnName, COUNT(*)::BIGINT AS violationCount FROM raw.linkareerIndexRaw WHERE activityTypeId IS NULL
UNION ALL
SELECT 'raw.linkareerIndexRaw' AS tableName, 'rawPath' AS columnName, COUNT(*)::BIGINT AS violationCount FROM raw.linkareerIndexRaw WHERE rawPath IS NULL
UNION ALL
SELECT 'raw.linkareerIndexRaw' AS tableName, 'rawSha256' AS columnName, COUNT(*)::BIGINT AS violationCount FROM raw.linkareerIndexRaw WHERE rawSha256 IS NULL
UNION ALL
SELECT 'raw.linkareerPostingRaw' AS tableName, 'rawPostingId' AS columnName, COUNT(*)::BIGINT AS violationCount FROM raw.linkareerPostingRaw WHERE rawPostingId IS NULL
UNION ALL
SELECT 'raw.linkareerPostingRaw' AS tableName, 'crawlRunId' AS columnName, COUNT(*)::BIGINT AS violationCount FROM raw.linkareerPostingRaw WHERE crawlRunId IS NULL
UNION ALL
SELECT 'raw.linkareerPostingRaw' AS tableName, 'sourcePostingId' AS columnName, COUNT(*)::BIGINT AS violationCount FROM raw.linkareerPostingRaw WHERE sourcePostingId IS NULL
UNION ALL
SELECT 'raw.linkareerPostingRaw' AS tableName, 'sourceUrl' AS columnName, COUNT(*)::BIGINT AS violationCount FROM raw.linkareerPostingRaw WHERE sourceUrl IS NULL
UNION ALL
SELECT 'raw.linkareerPostingRaw' AS tableName, 'fetchedAt' AS columnName, COUNT(*)::BIGINT AS violationCount FROM raw.linkareerPostingRaw WHERE fetchedAt IS NULL
UNION ALL
SELECT 'raw.linkareerPostingRaw' AS tableName, 'httpStatus' AS columnName, COUNT(*)::BIGINT AS violationCount FROM raw.linkareerPostingRaw WHERE httpStatus IS NULL
UNION ALL
SELECT 'raw.linkareerPostingRaw' AS tableName, 'rawPath' AS columnName, COUNT(*)::BIGINT AS violationCount FROM raw.linkareerPostingRaw WHERE rawPath IS NULL
UNION ALL
SELECT 'raw.linkareerPostingRaw' AS tableName, 'rawSha256' AS columnName, COUNT(*)::BIGINT AS violationCount FROM raw.linkareerPostingRaw WHERE rawSha256 IS NULL
UNION ALL
SELECT 'raw.linkareerPostingRaw' AS tableName, 'textAvailableFlag' AS columnName, COUNT(*)::BIGINT AS violationCount FROM raw.linkareerPostingRaw WHERE textAvailableFlag IS NULL
UNION ALL
SELECT 'raw.linkareerPostingRaw' AS tableName, 'assetCount' AS columnName, COUNT(*)::BIGINT AS violationCount FROM raw.linkareerPostingRaw WHERE assetCount IS NULL
UNION ALL
SELECT 'raw.linkareerPostingRaw' AS tableName, 'activityTextAvailableFlag' AS columnName, COUNT(*)::BIGINT AS violationCount FROM raw.linkareerPostingRaw WHERE activityTextAvailableFlag IS NULL
UNION ALL
SELECT 'raw.linkareerPostingRaw' AS tableName, 'externalApplyFlag' AS columnName, COUNT(*)::BIGINT AS violationCount FROM raw.linkareerPostingRaw WHERE externalApplyFlag IS NULL
UNION ALL
SELECT 'raw.linkareerPostingRaw' AS tableName, 'externalDetailOnlyFlag' AS columnName, COUNT(*)::BIGINT AS violationCount FROM raw.linkareerPostingRaw WHERE externalDetailOnlyFlag IS NULL
UNION ALL
SELECT 'raw.postingAsset' AS tableName, 'assetId' AS columnName, COUNT(*)::BIGINT AS violationCount FROM raw.postingAsset WHERE assetId IS NULL
UNION ALL
SELECT 'raw.postingAsset' AS tableName, 'rawPostingId' AS columnName, COUNT(*)::BIGINT AS violationCount FROM raw.postingAsset WHERE rawPostingId IS NULL
UNION ALL
SELECT 'raw.postingAsset' AS tableName, 'assetType' AS columnName, COUNT(*)::BIGINT AS violationCount FROM raw.postingAsset WHERE assetType IS NULL
UNION ALL
SELECT 'raw.postingAsset' AS tableName, 'assetPath' AS columnName, COUNT(*)::BIGINT AS violationCount FROM raw.postingAsset WHERE assetPath IS NULL
UNION ALL
SELECT 'raw.postingAsset' AS tableName, 'assetSha256' AS columnName, COUNT(*)::BIGINT AS violationCount FROM raw.postingAsset WHERE assetSha256 IS NULL
UNION ALL
SELECT 'raw.ocrResult' AS tableName, 'ocrId' AS columnName, COUNT(*)::BIGINT AS violationCount FROM raw.ocrResult WHERE ocrId IS NULL
UNION ALL
SELECT 'raw.ocrResult' AS tableName, 'assetId' AS columnName, COUNT(*)::BIGINT AS violationCount FROM raw.ocrResult WHERE assetId IS NULL
UNION ALL
SELECT 'raw.ocrResult' AS tableName, 'ocrEngine' AS columnName, COUNT(*)::BIGINT AS violationCount FROM raw.ocrResult WHERE ocrEngine IS NULL
UNION ALL
SELECT 'raw.ocrResult' AS tableName, 'ocrModel' AS columnName, COUNT(*)::BIGINT AS violationCount FROM raw.ocrResult WHERE ocrModel IS NULL
UNION ALL
SELECT 'raw.ocrResult' AS tableName, 'ocrVersion' AS columnName, COUNT(*)::BIGINT AS violationCount FROM raw.ocrResult WHERE ocrVersion IS NULL
UNION ALL
SELECT 'raw.ocrResult' AS tableName, 'ocrReviewFlag' AS columnName, COUNT(*)::BIGINT AS violationCount FROM raw.ocrResult WHERE ocrReviewFlag IS NULL
UNION ALL
SELECT 'raw.ocrResult' AS tableName, 'producedAt' AS columnName, COUNT(*)::BIGINT AS violationCount FROM raw.ocrResult WHERE producedAt IS NULL
UNION ALL
SELECT 'core.postingNormalized' AS tableName, 'postingId' AS columnName, COUNT(*)::BIGINT AS violationCount FROM core.postingNormalized WHERE postingId IS NULL
UNION ALL
SELECT 'core.postingNormalized' AS tableName, 'rawPostingId' AS columnName, COUNT(*)::BIGINT AS violationCount FROM core.postingNormalized WHERE rawPostingId IS NULL
UNION ALL
SELECT 'core.postingNormalized' AS tableName, 'sourcePostingId' AS columnName, COUNT(*)::BIGINT AS violationCount FROM core.postingNormalized WHERE sourcePostingId IS NULL
UNION ALL
SELECT 'core.postingNormalized' AS tableName, 'sourceUrl' AS columnName, COUNT(*)::BIGINT AS violationCount FROM core.postingNormalized WHERE sourceUrl IS NULL
UNION ALL
SELECT 'core.postingNormalized' AS tableName, 'postingKind' AS columnName, COUNT(*)::BIGINT AS violationCount FROM core.postingNormalized WHERE postingKind IS NULL
UNION ALL
SELECT 'core.postingNormalized' AS tableName, 'recruitmentScope' AS columnName, COUNT(*)::BIGINT AS violationCount FROM core.postingNormalized WHERE recruitmentScope IS NULL
UNION ALL
SELECT 'core.postingNormalized' AS tableName, 'postingEligibleFlag' AS columnName, COUNT(*)::BIGINT AS violationCount FROM core.postingNormalized WHERE postingEligibleFlag IS NULL
UNION ALL
SELECT 'core.postingNormalized' AS tableName, 'rq1EligibleFlag' AS columnName, COUNT(*)::BIGINT AS violationCount FROM core.postingNormalized WHERE rq1EligibleFlag IS NULL
UNION ALL
SELECT 'core.postingNormalized' AS tableName, 'rq2EligibleFlag' AS columnName, COUNT(*)::BIGINT AS violationCount FROM core.postingNormalized WHERE rq2EligibleFlag IS NULL
UNION ALL
SELECT 'core.postingNormalized' AS tableName, 'ncsEligibleFlag' AS columnName, COUNT(*)::BIGINT AS violationCount FROM core.postingNormalized WHERE ncsEligibleFlag IS NULL
UNION ALL
SELECT 'core.postingNormalized' AS tableName, 'canonicalPostingId' AS columnName, COUNT(*)::BIGINT AS violationCount FROM core.postingNormalized WHERE canonicalPostingId IS NULL
UNION ALL
SELECT 'core.postingNormalized' AS tableName, 'canonicalPostedAt' AS columnName, COUNT(*)::BIGINT AS violationCount FROM core.postingNormalized WHERE canonicalPostedAt IS NULL
UNION ALL
SELECT 'core.postingNormalized' AS tableName, 'canonicalRecordFlag' AS columnName, COUNT(*)::BIGINT AS violationCount FROM core.postingNormalized WHERE canonicalRecordFlag IS NULL
UNION ALL
SELECT 'core.postingNormalized' AS tableName, 'repostCount' AS columnName, COUNT(*)::BIGINT AS violationCount FROM core.postingNormalized WHERE repostCount IS NULL
UNION ALL
SELECT 'core.postingNormalized' AS tableName, 'rawSha256' AS columnName, COUNT(*)::BIGINT AS violationCount FROM core.postingNormalized WHERE rawSha256 IS NULL
UNION ALL
SELECT 'core.postingNormalized' AS tableName, 'parseVersion' AS columnName, COUNT(*)::BIGINT AS violationCount FROM core.postingNormalized WHERE parseVersion IS NULL
UNION ALL
SELECT 'core.postingNormalized' AS tableName, 'dataVersion' AS columnName, COUNT(*)::BIGINT AS violationCount FROM core.postingNormalized WHERE dataVersion IS NULL
UNION ALL
SELECT 'core.postingNormalized' AS tableName, 'normalizedAt' AS columnName, COUNT(*)::BIGINT AS violationCount FROM core.postingNormalized WHERE normalizedAt IS NULL
UNION ALL
SELECT 'core.postingTrack' AS tableName, 'trackId' AS columnName, COUNT(*)::BIGINT AS violationCount FROM core.postingTrack WHERE trackId IS NULL
UNION ALL
SELECT 'core.postingTrack' AS tableName, 'postingId' AS columnName, COUNT(*)::BIGINT AS violationCount FROM core.postingTrack WHERE postingId IS NULL
UNION ALL
SELECT 'core.postingTrack' AS tableName, 'trackIndex' AS columnName, COUNT(*)::BIGINT AS violationCount FROM core.postingTrack WHERE trackIndex IS NULL
UNION ALL
SELECT 'core.postingTrack' AS tableName, 'trackType' AS columnName, COUNT(*)::BIGINT AS violationCount FROM core.postingTrack WHERE trackType IS NULL
UNION ALL
SELECT 'core.postingTrack' AS tableName, 'hasEntryFlag' AS columnName, COUNT(*)::BIGINT AS violationCount FROM core.postingTrack WHERE hasEntryFlag IS NULL
UNION ALL
SELECT 'core.postingTrack' AS tableName, 'hasInternFlag' AS columnName, COUNT(*)::BIGINT AS violationCount FROM core.postingTrack WHERE hasInternFlag IS NULL
UNION ALL
SELECT 'core.postingTrack' AS tableName, 'hasExperiencedFlag' AS columnName, COUNT(*)::BIGINT AS violationCount FROM core.postingTrack WHERE hasExperiencedFlag IS NULL
UNION ALL
SELECT 'core.postingTrack' AS tableName, 'recruitmentScope' AS columnName, COUNT(*)::BIGINT AS violationCount FROM core.postingTrack WHERE recruitmentScope IS NULL
UNION ALL
SELECT 'core.postingTrack' AS tableName, 'mixedResolvedFlag' AS columnName, COUNT(*)::BIGINT AS violationCount FROM core.postingTrack WHERE mixedResolvedFlag IS NULL
UNION ALL
SELECT 'core.postingTrack' AS tableName, 'trackVersion' AS columnName, COUNT(*)::BIGINT AS violationCount FROM core.postingTrack WHERE trackVersion IS NULL
UNION ALL
SELECT 'core.postingTrack' AS tableName, 'jobTypeSource' AS columnName, COUNT(*)::BIGINT AS violationCount FROM core.postingTrack WHERE jobTypeSource IS NULL
UNION ALL
SELECT 'core.postingTrack' AS tableName, 'jobTypeConflictFlag' AS columnName, COUNT(*)::BIGINT AS violationCount FROM core.postingTrack WHERE jobTypeConflictFlag IS NULL
UNION ALL
SELECT 'core.postingSection' AS tableName, 'sectionId' AS columnName, COUNT(*)::BIGINT AS violationCount FROM core.postingSection WHERE sectionId IS NULL
UNION ALL
SELECT 'core.postingSection' AS tableName, 'trackId' AS columnName, COUNT(*)::BIGINT AS violationCount FROM core.postingSection WHERE trackId IS NULL
UNION ALL
SELECT 'core.postingSection' AS tableName, 'postingId' AS columnName, COUNT(*)::BIGINT AS violationCount FROM core.postingSection WHERE postingId IS NULL
UNION ALL
SELECT 'core.postingSection' AS tableName, 'sectionOrder' AS columnName, COUNT(*)::BIGINT AS violationCount FROM core.postingSection WHERE sectionOrder IS NULL
UNION ALL
SELECT 'core.postingSection' AS tableName, 'sectionType' AS columnName, COUNT(*)::BIGINT AS violationCount FROM core.postingSection WHERE sectionType IS NULL
UNION ALL
SELECT 'core.postingSection' AS tableName, 'sectionText' AS columnName, COUNT(*)::BIGINT AS violationCount FROM core.postingSection WHERE sectionText IS NULL
UNION ALL
SELECT 'core.postingSection' AS tableName, 'sourceMode' AS columnName, COUNT(*)::BIGINT AS violationCount FROM core.postingSection WHERE sourceMode IS NULL
UNION ALL
SELECT 'core.postingSection' AS tableName, 'boundaryResolvedFlag' AS columnName, COUNT(*)::BIGINT AS violationCount FROM core.postingSection WHERE boundaryResolvedFlag IS NULL
UNION ALL
SELECT 'core.postingSection' AS tableName, 'parseVersion' AS columnName, COUNT(*)::BIGINT AS violationCount FROM core.postingSection WHERE parseVersion IS NULL
UNION ALL
SELECT 'core.requirementFact' AS tableName, 'requirementId' AS columnName, COUNT(*)::BIGINT AS violationCount FROM core.requirementFact WHERE requirementId IS NULL
UNION ALL
SELECT 'core.requirementFact' AS tableName, 'sectionId' AS columnName, COUNT(*)::BIGINT AS violationCount FROM core.requirementFact WHERE sectionId IS NULL
UNION ALL
SELECT 'core.requirementFact' AS tableName, 'trackId' AS columnName, COUNT(*)::BIGINT AS violationCount FROM core.requirementFact WHERE trackId IS NULL
UNION ALL
SELECT 'core.requirementFact' AS tableName, 'postingId' AS columnName, COUNT(*)::BIGINT AS violationCount FROM core.requirementFact WHERE postingId IS NULL
UNION ALL
SELECT 'core.requirementFact' AS tableName, 'requirementType' AS columnName, COUNT(*)::BIGINT AS violationCount FROM core.requirementFact WHERE requirementType IS NULL
UNION ALL
SELECT 'core.requirementFact' AS tableName, 'obligation' AS columnName, COUNT(*)::BIGINT AS violationCount FROM core.requirementFact WHERE obligation IS NULL
UNION ALL
SELECT 'core.requirementFact' AS tableName, 'evidenceText' AS columnName, COUNT(*)::BIGINT AS violationCount FROM core.requirementFact WHERE evidenceText IS NULL
UNION ALL
SELECT 'core.requirementFact' AS tableName, 'extractorVersion' AS columnName, COUNT(*)::BIGINT AS violationCount FROM core.requirementFact WHERE extractorVersion IS NULL
UNION ALL
SELECT 'core.requirementFact' AS tableName, 'reviewFlag' AS columnName, COUNT(*)::BIGINT AS violationCount FROM core.requirementFact WHERE reviewFlag IS NULL
UNION ALL
SELECT 'core.careerLabel' AS tableName, 'trackId' AS columnName, COUNT(*)::BIGINT AS violationCount FROM core.careerLabel WHERE trackId IS NULL
UNION ALL
SELECT 'core.careerLabel' AS tableName, 'postingId' AS columnName, COUNT(*)::BIGINT AS violationCount FROM core.careerLabel WHERE postingId IS NULL
UNION ALL
SELECT 'core.careerLabel' AS tableName, 'careerClass' AS columnName, COUNT(*)::BIGINT AS violationCount FROM core.careerLabel WHERE careerClass IS NULL
UNION ALL
SELECT 'core.careerLabel' AS tableName, 'nominalEntryFlag' AS columnName, COUNT(*)::BIGINT AS violationCount FROM core.careerLabel WHERE nominalEntryFlag IS NULL
UNION ALL
SELECT 'core.careerLabel' AS tableName, 'openEntryFlag' AS columnName, COUNT(*)::BIGINT AS violationCount FROM core.careerLabel WHERE openEntryFlag IS NULL
UNION ALL
SELECT 'core.careerLabel' AS tableName, 'restrictedEntryFlag' AS columnName, COUNT(*)::BIGINT AS violationCount FROM core.careerLabel WHERE restrictedEntryFlag IS NULL
UNION ALL
SELECT 'core.careerLabel' AS tableName, 'openInternFlag' AS columnName, COUNT(*)::BIGINT AS violationCount FROM core.careerLabel WHERE openInternFlag IS NULL
UNION ALL
SELECT 'core.careerLabel' AS tableName, 'restrictedInternFlag' AS columnName, COUNT(*)::BIGINT AS violationCount FROM core.careerLabel WHERE restrictedInternFlag IS NULL
UNION ALL
SELECT 'core.careerLabel' AS tableName, 'experiencedInternFlag' AS columnName, COUNT(*)::BIGINT AS violationCount FROM core.careerLabel WHERE experiencedInternFlag IS NULL
UNION ALL
SELECT 'core.careerLabel' AS tableName, 'requiredExperienceFlag' AS columnName, COUNT(*)::BIGINT AS violationCount FROM core.careerLabel WHERE requiredExperienceFlag IS NULL
UNION ALL
SELECT 'core.careerLabel' AS tableName, 'requiredPriorExperienceFlag' AS columnName, COUNT(*)::BIGINT AS violationCount FROM core.careerLabel WHERE requiredPriorExperienceFlag IS NULL
UNION ALL
SELECT 'core.careerLabel' AS tableName, 'boundaryResolvedFlag' AS columnName, COUNT(*)::BIGINT AS violationCount FROM core.careerLabel WHERE boundaryResolvedFlag IS NULL
UNION ALL
SELECT 'core.careerLabel' AS tableName, 'explicitCareerFlag' AS columnName, COUNT(*)::BIGINT AS violationCount FROM core.careerLabel WHERE explicitCareerFlag IS NULL
UNION ALL
SELECT 'core.careerLabel' AS tableName, 'labelVersion' AS columnName, COUNT(*)::BIGINT AS violationCount FROM core.careerLabel WHERE labelVersion IS NULL
UNION ALL
SELECT 'core.postingDedupEdge' AS tableName, 'edgeId' AS columnName, COUNT(*)::BIGINT AS violationCount FROM core.postingDedupEdge WHERE edgeId IS NULL
UNION ALL
SELECT 'core.postingDedupEdge' AS tableName, 'leftPostingId' AS columnName, COUNT(*)::BIGINT AS violationCount FROM core.postingDedupEdge WHERE leftPostingId IS NULL
UNION ALL
SELECT 'core.postingDedupEdge' AS tableName, 'rightPostingId' AS columnName, COUNT(*)::BIGINT AS violationCount FROM core.postingDedupEdge WHERE rightPostingId IS NULL
UNION ALL
SELECT 'core.postingDedupEdge' AS tableName, 'dayDiff' AS columnName, COUNT(*)::BIGINT AS violationCount FROM core.postingDedupEdge WHERE dayDiff IS NULL
UNION ALL
SELECT 'core.postingDedupEdge' AS tableName, 'decision' AS columnName, COUNT(*)::BIGINT AS violationCount FROM core.postingDedupEdge WHERE decision IS NULL
UNION ALL
SELECT 'core.postingDedupEdge' AS tableName, 'dedupVersion' AS columnName, COUNT(*)::BIGINT AS violationCount FROM core.postingDedupEdge WHERE dedupVersion IS NULL
UNION ALL
SELECT 'ncs.ncsUnit' AS tableName, 'ncsUnitCode' AS columnName, COUNT(*)::BIGINT AS violationCount FROM ncs.ncsUnit WHERE ncsUnitCode IS NULL
UNION ALL
SELECT 'ncs.ncsUnit' AS tableName, 'ncsUnitName' AS columnName, COUNT(*)::BIGINT AS violationCount FROM ncs.ncsUnit WHERE ncsUnitName IS NULL
UNION ALL
SELECT 'ncs.ncsUnit' AS tableName, 'ncsSubCode' AS columnName, COUNT(*)::BIGINT AS violationCount FROM ncs.ncsUnit WHERE ncsSubCode IS NULL
UNION ALL
SELECT 'ncs.ncsUnit' AS tableName, 'ncsLevel' AS columnName, COUNT(*)::BIGINT AS violationCount FROM ncs.ncsUnit WHERE ncsLevel IS NULL
UNION ALL
SELECT 'ncs.ncsUnit' AS tableName, 'ncsBand' AS columnName, COUNT(*)::BIGINT AS violationCount FROM ncs.ncsUnit WHERE ncsBand IS NULL
UNION ALL
SELECT 'ncs.ncsUnit' AS tableName, 'sourceVersion' AS columnName, COUNT(*)::BIGINT AS violationCount FROM ncs.ncsUnit WHERE sourceVersion IS NULL
UNION ALL
SELECT 'ncs.ncsUnit' AS tableName, 'rawSha256' AS columnName, COUNT(*)::BIGINT AS violationCount FROM ncs.ncsUnit WHERE rawSha256 IS NULL
UNION ALL
SELECT 'ncs.ncsLearningModule' AS tableName, 'moduleId' AS columnName, COUNT(*)::BIGINT AS violationCount FROM ncs.ncsLearningModule WHERE moduleId IS NULL
UNION ALL
SELECT 'ncs.ncsLearningModule' AS tableName, 'ncsUnitCode' AS columnName, COUNT(*)::BIGINT AS violationCount FROM ncs.ncsLearningModule WHERE ncsUnitCode IS NULL
UNION ALL
SELECT 'ncs.ncsLearningModule' AS tableName, 'moduleName' AS columnName, COUNT(*)::BIGINT AS violationCount FROM ncs.ncsLearningModule WHERE moduleName IS NULL
UNION ALL
SELECT 'ncs.ncsLearningModule' AS tableName, 'redistributableFlag' AS columnName, COUNT(*)::BIGINT AS violationCount FROM ncs.ncsLearningModule WHERE redistributableFlag IS NULL
UNION ALL
SELECT 'ncs.ncsLearningModule' AS tableName, 'sourceVersion' AS columnName, COUNT(*)::BIGINT AS violationCount FROM ncs.ncsLearningModule WHERE sourceVersion IS NULL
UNION ALL
SELECT 'ncs.ncsLearningModule' AS tableName, 'rawSha256' AS columnName, COUNT(*)::BIGINT AS violationCount FROM ncs.ncsLearningModule WHERE rawSha256 IS NULL
UNION ALL
SELECT 'ncs.postingNcsMatch' AS tableName, 'matchId' AS columnName, COUNT(*)::BIGINT AS violationCount FROM ncs.postingNcsMatch WHERE matchId IS NULL
UNION ALL
SELECT 'ncs.postingNcsMatch' AS tableName, 'postingId' AS columnName, COUNT(*)::BIGINT AS violationCount FROM ncs.postingNcsMatch WHERE postingId IS NULL
UNION ALL
SELECT 'ncs.postingNcsMatch' AS tableName, 'trackId' AS columnName, COUNT(*)::BIGINT AS violationCount FROM ncs.postingNcsMatch WHERE trackId IS NULL
UNION ALL
SELECT 'ncs.postingNcsMatch' AS tableName, 'ncsUnitCode' AS columnName, COUNT(*)::BIGINT AS violationCount FROM ncs.postingNcsMatch WHERE ncsUnitCode IS NULL
UNION ALL
SELECT 'ncs.postingNcsMatch' AS tableName, 'ncsLevel' AS columnName, COUNT(*)::BIGINT AS violationCount FROM ncs.postingNcsMatch WHERE ncsLevel IS NULL
UNION ALL
SELECT 'ncs.postingNcsMatch' AS tableName, 'ncsBand' AS columnName, COUNT(*)::BIGINT AS violationCount FROM ncs.postingNcsMatch WHERE ncsBand IS NULL
UNION ALL
SELECT 'ncs.postingNcsMatch' AS tableName, 'mappingBasis' AS columnName, COUNT(*)::BIGINT AS violationCount FROM ncs.postingNcsMatch WHERE mappingBasis IS NULL
UNION ALL
SELECT 'ncs.postingNcsMatch' AS tableName, 'matchRank' AS columnName, COUNT(*)::BIGINT AS violationCount FROM ncs.postingNcsMatch WHERE matchRank IS NULL
UNION ALL
SELECT 'ncs.postingNcsMatch' AS tableName, 'selectedFlag' AS columnName, COUNT(*)::BIGINT AS violationCount FROM ncs.postingNcsMatch WHERE selectedFlag IS NULL
UNION ALL
SELECT 'ncs.postingNcsMatch' AS tableName, 'ncsConfidenceTier' AS columnName, COUNT(*)::BIGINT AS violationCount FROM ncs.postingNcsMatch WHERE ncsConfidenceTier IS NULL
UNION ALL
SELECT 'ncs.postingNcsMatch' AS tableName, 'evidenceText' AS columnName, COUNT(*)::BIGINT AS violationCount FROM ncs.postingNcsMatch WHERE evidenceText IS NULL
UNION ALL
SELECT 'ncs.postingNcsMatch' AS tableName, 'mappingVersion' AS columnName, COUNT(*)::BIGINT AS violationCount FROM ncs.postingNcsMatch WHERE mappingVersion IS NULL
UNION ALL
SELECT 'ncs.postingNcsMatch' AS tableName, 'matchedAt' AS columnName, COUNT(*)::BIGINT AS violationCount FROM ncs.postingNcsMatch WHERE matchedAt IS NULL
UNION ALL
SELECT 'mart.postingAnalysisMart' AS tableName, 'trackId' AS columnName, COUNT(*)::BIGINT AS violationCount FROM mart.postingAnalysisMart WHERE trackId IS NULL
UNION ALL
SELECT 'mart.postingAnalysisMart' AS tableName, 'postingId' AS columnName, COUNT(*)::BIGINT AS violationCount FROM mart.postingAnalysisMart WHERE postingId IS NULL
UNION ALL
SELECT 'mart.postingAnalysisMart' AS tableName, 'canonicalPostingId' AS columnName, COUNT(*)::BIGINT AS violationCount FROM mart.postingAnalysisMart WHERE canonicalPostingId IS NULL
UNION ALL
SELECT 'mart.postingAnalysisMart' AS tableName, 'canonicalPostedAt' AS columnName, COUNT(*)::BIGINT AS violationCount FROM mart.postingAnalysisMart WHERE canonicalPostedAt IS NULL
UNION ALL
SELECT 'mart.postingAnalysisMart' AS tableName, 'periodMonth' AS columnName, COUNT(*)::BIGINT AS violationCount FROM mart.postingAnalysisMart WHERE periodMonth IS NULL
UNION ALL
SELECT 'mart.postingAnalysisMart' AS tableName, 'year' AS columnName, COUNT(*)::BIGINT AS violationCount FROM mart.postingAnalysisMart WHERE year IS NULL
UNION ALL
SELECT 'mart.postingAnalysisMart' AS tableName, 'month' AS columnName, COUNT(*)::BIGINT AS violationCount FROM mart.postingAnalysisMart WHERE month IS NULL
UNION ALL
SELECT 'mart.postingAnalysisMart' AS tableName, 'quarterNumber' AS columnName, COUNT(*)::BIGINT AS violationCount FROM mart.postingAnalysisMart WHERE quarterNumber IS NULL
UNION ALL
SELECT 'mart.postingAnalysisMart' AS tableName, 'asOfDate' AS columnName, COUNT(*)::BIGINT AS violationCount FROM mart.postingAnalysisMart WHERE asOfDate IS NULL
UNION ALL
SELECT 'mart.postingAnalysisMart' AS tableName, 'sourceName' AS columnName, COUNT(*)::BIGINT AS violationCount FROM mart.postingAnalysisMart WHERE sourceName IS NULL
UNION ALL
SELECT 'mart.postingAnalysisMart' AS tableName, 'sourceUrl' AS columnName, COUNT(*)::BIGINT AS violationCount FROM mart.postingAnalysisMart WHERE sourceUrl IS NULL
UNION ALL
SELECT 'mart.postingAnalysisMart' AS tableName, 'cohortType' AS columnName, COUNT(*)::BIGINT AS violationCount FROM mart.postingAnalysisMart WHERE cohortType IS NULL
UNION ALL
SELECT 'mart.postingAnalysisMart' AS tableName, 'jobCodeLevel' AS columnName, COUNT(*)::BIGINT AS violationCount FROM mart.postingAnalysisMart WHERE jobCodeLevel IS NULL
UNION ALL
SELECT 'mart.postingAnalysisMart' AS tableName, 'jobCode' AS columnName, COUNT(*)::BIGINT AS violationCount FROM mart.postingAnalysisMart WHERE jobCode IS NULL
UNION ALL
SELECT 'mart.postingAnalysisMart' AS tableName, 'coreAiItFlag' AS columnName, COUNT(*)::BIGINT AS violationCount FROM mart.postingAnalysisMart WHERE coreAiItFlag IS NULL
UNION ALL
SELECT 'mart.postingAnalysisMart' AS tableName, 'postingKind' AS columnName, COUNT(*)::BIGINT AS violationCount FROM mart.postingAnalysisMart WHERE postingKind IS NULL
UNION ALL
SELECT 'mart.postingAnalysisMart' AS tableName, 'postingEligibleFlag' AS columnName, COUNT(*)::BIGINT AS violationCount FROM mart.postingAnalysisMart WHERE postingEligibleFlag IS NULL
UNION ALL
SELECT 'mart.postingAnalysisMart' AS tableName, 'rq1EligibleFlag' AS columnName, COUNT(*)::BIGINT AS violationCount FROM mart.postingAnalysisMart WHERE rq1EligibleFlag IS NULL
UNION ALL
SELECT 'mart.postingAnalysisMart' AS tableName, 'rq2EligibleFlag' AS columnName, COUNT(*)::BIGINT AS violationCount FROM mart.postingAnalysisMart WHERE rq2EligibleFlag IS NULL
UNION ALL
SELECT 'mart.postingAnalysisMart' AS tableName, 'ncsEligibleFlag' AS columnName, COUNT(*)::BIGINT AS violationCount FROM mart.postingAnalysisMart WHERE ncsEligibleFlag IS NULL
UNION ALL
SELECT 'mart.postingAnalysisMart' AS tableName, 'canonicalRecordFlag' AS columnName, COUNT(*)::BIGINT AS violationCount FROM mart.postingAnalysisMart WHERE canonicalRecordFlag IS NULL
UNION ALL
SELECT 'mart.postingAnalysisMart' AS tableName, 'trackType' AS columnName, COUNT(*)::BIGINT AS violationCount FROM mart.postingAnalysisMart WHERE trackType IS NULL
UNION ALL
SELECT 'mart.postingAnalysisMart' AS tableName, 'recruitmentScope' AS columnName, COUNT(*)::BIGINT AS violationCount FROM mart.postingAnalysisMart WHERE recruitmentScope IS NULL
UNION ALL
SELECT 'mart.postingAnalysisMart' AS tableName, 'hasEntryFlag' AS columnName, COUNT(*)::BIGINT AS violationCount FROM mart.postingAnalysisMart WHERE hasEntryFlag IS NULL
UNION ALL
SELECT 'mart.postingAnalysisMart' AS tableName, 'hasInternFlag' AS columnName, COUNT(*)::BIGINT AS violationCount FROM mart.postingAnalysisMart WHERE hasInternFlag IS NULL
UNION ALL
SELECT 'mart.postingAnalysisMart' AS tableName, 'hasExperiencedFlag' AS columnName, COUNT(*)::BIGINT AS violationCount FROM mart.postingAnalysisMart WHERE hasExperiencedFlag IS NULL
UNION ALL
SELECT 'mart.postingAnalysisMart' AS tableName, 'mixedResolvedFlag' AS columnName, COUNT(*)::BIGINT AS violationCount FROM mart.postingAnalysisMart WHERE mixedResolvedFlag IS NULL
UNION ALL
SELECT 'mart.postingAnalysisMart' AS tableName, 'activityTextAvailableFlag' AS columnName, COUNT(*)::BIGINT AS violationCount FROM mart.postingAnalysisMart WHERE activityTextAvailableFlag IS NULL
UNION ALL
SELECT 'mart.postingAnalysisMart' AS tableName, 'externalApplyFlag' AS columnName, COUNT(*)::BIGINT AS violationCount FROM mart.postingAnalysisMart WHERE externalApplyFlag IS NULL
UNION ALL
SELECT 'mart.postingAnalysisMart' AS tableName, 'externalDetailOnlyFlag' AS columnName, COUNT(*)::BIGINT AS violationCount FROM mart.postingAnalysisMart WHERE externalDetailOnlyFlag IS NULL
UNION ALL
SELECT 'mart.postingAnalysisMart' AS tableName, 'jobTypeConflictFlag' AS columnName, COUNT(*)::BIGINT AS violationCount FROM mart.postingAnalysisMart WHERE jobTypeConflictFlag IS NULL
UNION ALL
SELECT 'mart.postingAnalysisMart' AS tableName, 'careerClass' AS columnName, COUNT(*)::BIGINT AS violationCount FROM mart.postingAnalysisMart WHERE careerClass IS NULL
UNION ALL
SELECT 'mart.postingAnalysisMart' AS tableName, 'nominalEntryFlag' AS columnName, COUNT(*)::BIGINT AS violationCount FROM mart.postingAnalysisMart WHERE nominalEntryFlag IS NULL
UNION ALL
SELECT 'mart.postingAnalysisMart' AS tableName, 'restrictedInternFlag' AS columnName, COUNT(*)::BIGINT AS violationCount FROM mart.postingAnalysisMart WHERE restrictedInternFlag IS NULL
UNION ALL
SELECT 'mart.postingAnalysisMart' AS tableName, 'experiencedInternFlag' AS columnName, COUNT(*)::BIGINT AS violationCount FROM mart.postingAnalysisMart WHERE experiencedInternFlag IS NULL
UNION ALL
SELECT 'mart.postingAnalysisMart' AS tableName, 'boundaryResolvedFlag' AS columnName, COUNT(*)::BIGINT AS violationCount FROM mart.postingAnalysisMart WHERE boundaryResolvedFlag IS NULL
UNION ALL
SELECT 'mart.postingAnalysisMart' AS tableName, 'ncsMappingCoverage' AS columnName, COUNT(*)::BIGINT AS violationCount FROM mart.postingAnalysisMart WHERE ncsMappingCoverage IS NULL
UNION ALL
SELECT 'mart.postingAnalysisMart' AS tableName, 'scoreStatus' AS columnName, COUNT(*)::BIGINT AS violationCount FROM mart.postingAnalysisMart WHERE scoreStatus IS NULL
UNION ALL
SELECT 'mart.postingAnalysisMart' AS tableName, 'repostCount' AS columnName, COUNT(*)::BIGINT AS violationCount FROM mart.postingAnalysisMart WHERE repostCount IS NULL
UNION ALL
SELECT 'mart.postingAnalysisMart' AS tableName, 'rawSha256' AS columnName, COUNT(*)::BIGINT AS violationCount FROM mart.postingAnalysisMart WHERE rawSha256 IS NULL
UNION ALL
SELECT 'mart.postingAnalysisMart' AS tableName, 'parseVersion' AS columnName, COUNT(*)::BIGINT AS violationCount FROM mart.postingAnalysisMart WHERE parseVersion IS NULL
UNION ALL
SELECT 'mart.postingAnalysisMart' AS tableName, 'labelVersion' AS columnName, COUNT(*)::BIGINT AS violationCount FROM mart.postingAnalysisMart WHERE labelVersion IS NULL
UNION ALL
SELECT 'mart.postingAnalysisMart' AS tableName, 'ncsMapVersion' AS columnName, COUNT(*)::BIGINT AS violationCount FROM mart.postingAnalysisMart WHERE ncsMapVersion IS NULL
UNION ALL
SELECT 'mart.postingAnalysisMart' AS tableName, 'dataVersion' AS columnName, COUNT(*)::BIGINT AS violationCount FROM mart.postingAnalysisMart WHERE dataVersion IS NULL
UNION ALL
SELECT 'mart.postingAnalysisMart' AS tableName, 'builtAt' AS columnName, COUNT(*)::BIGINT AS violationCount FROM mart.postingAnalysisMart WHERE builtAt IS NULL
UNION ALL
SELECT 'mart.timeSeriesMart' AS tableName, 'periodMonth' AS columnName, COUNT(*)::BIGINT AS violationCount FROM mart.timeSeriesMart WHERE periodMonth IS NULL
UNION ALL
SELECT 'mart.timeSeriesMart' AS tableName, 'cohortType' AS columnName, COUNT(*)::BIGINT AS violationCount FROM mart.timeSeriesMart WHERE cohortType IS NULL
UNION ALL
SELECT 'mart.timeSeriesMart' AS tableName, 'jobCodeLevel' AS columnName, COUNT(*)::BIGINT AS violationCount FROM mart.timeSeriesMart WHERE jobCodeLevel IS NULL
UNION ALL
SELECT 'mart.timeSeriesMart' AS tableName, 'jobCode' AS columnName, COUNT(*)::BIGINT AS violationCount FROM mart.timeSeriesMart WHERE jobCode IS NULL
UNION ALL
SELECT 'mart.timeSeriesMart' AS tableName, 'dedupApplied' AS columnName, COUNT(*)::BIGINT AS violationCount FROM mart.timeSeriesMart WHERE dedupApplied IS NULL
UNION ALL
SELECT 'mart.timeSeriesMart' AS tableName, 'totalValidPostingCount' AS columnName, COUNT(*)::BIGINT AS violationCount FROM mart.timeSeriesMart WHERE totalValidPostingCount IS NULL
UNION ALL
SELECT 'mart.timeSeriesMart' AS tableName, 'entryPostingCount' AS columnName, COUNT(*)::BIGINT AS violationCount FROM mart.timeSeriesMart WHERE entryPostingCount IS NULL
UNION ALL
SELECT 'mart.timeSeriesMart' AS tableName, 'internPostingCount' AS columnName, COUNT(*)::BIGINT AS violationCount FROM mart.timeSeriesMart WHERE internPostingCount IS NULL
UNION ALL
SELECT 'mart.timeSeriesMart' AS tableName, 'coverageStatus' AS columnName, COUNT(*)::BIGINT AS violationCount FROM mart.timeSeriesMart WHERE coverageStatus IS NULL
UNION ALL
SELECT 'mart.timeSeriesMart' AS tableName, 'partialMonthFlag' AS columnName, COUNT(*)::BIGINT AS violationCount FROM mart.timeSeriesMart WHERE partialMonthFlag IS NULL
UNION ALL
SELECT 'mart.timeSeriesMart' AS tableName, 'asOfDate' AS columnName, COUNT(*)::BIGINT AS violationCount FROM mart.timeSeriesMart WHERE asOfDate IS NULL
UNION ALL
SELECT 'mart.timeSeriesMart' AS tableName, 'dataVersion' AS columnName, COUNT(*)::BIGINT AS violationCount FROM mart.timeSeriesMart WHERE dataVersion IS NULL
UNION ALL
SELECT 'mart.timeSeriesMart' AS tableName, 'builtAt' AS columnName, COUNT(*)::BIGINT AS violationCount FROM mart.timeSeriesMart WHERE builtAt IS NULL
UNION ALL
SELECT 'mart.caseStudyRegistry' AS tableName, 'caseId' AS columnName, COUNT(*)::BIGINT AS violationCount FROM mart.caseStudyRegistry WHERE caseId IS NULL
UNION ALL
SELECT 'mart.caseStudyRegistry' AS tableName, 'postingId' AS columnName, COUNT(*)::BIGINT AS violationCount FROM mart.caseStudyRegistry WHERE postingId IS NULL
UNION ALL
SELECT 'mart.caseStudyRegistry' AS tableName, 'selectionReason' AS columnName, COUNT(*)::BIGINT AS violationCount FROM mart.caseStudyRegistry WHERE selectionReason IS NULL
UNION ALL
SELECT 'mart.caseStudyRegistry' AS tableName, 'reviewedBy' AS columnName, COUNT(*)::BIGINT AS violationCount FROM mart.caseStudyRegistry WHERE reviewedBy IS NULL
UNION ALL
SELECT 'mart.caseStudyRegistry' AS tableName, 'reviewedAt' AS columnName, COUNT(*)::BIGINT AS violationCount FROM mart.caseStudyRegistry WHERE reviewedAt IS NULL
UNION ALL
SELECT 'mart.similarityPair' AS tableName, 'pairId' AS columnName, COUNT(*)::BIGINT AS violationCount FROM mart.similarityPair WHERE pairId IS NULL
UNION ALL
SELECT 'mart.similarityPair' AS tableName, 'internTrackId' AS columnName, COUNT(*)::BIGINT AS violationCount FROM mart.similarityPair WHERE internTrackId IS NULL
UNION ALL
SELECT 'mart.similarityPair' AS tableName, 'comparisonTrackId' AS columnName, COUNT(*)::BIGINT AS violationCount FROM mart.similarityPair WHERE comparisonTrackId IS NULL
UNION ALL
SELECT 'mart.similarityPair' AS tableName, 'comparisonType' AS columnName, COUNT(*)::BIGINT AS violationCount FROM mart.similarityPair WHERE comparisonType IS NULL
UNION ALL
SELECT 'mart.similarityPair' AS tableName, 'embeddingModel' AS columnName, COUNT(*)::BIGINT AS violationCount FROM mart.similarityPair WHERE embeddingModel IS NULL
UNION ALL
SELECT 'mart.similarityPair' AS tableName, 'auxVersion' AS columnName, COUNT(*)::BIGINT AS violationCount FROM mart.similarityPair WHERE auxVersion IS NULL
UNION ALL
SELECT 'qa.monthlyCoverageAudit' AS tableName, 'periodMonth' AS columnName, COUNT(*)::BIGINT AS violationCount FROM qa.monthlyCoverageAudit WHERE periodMonth IS NULL
UNION ALL
SELECT 'qa.monthlyCoverageAudit' AS tableName, 'sourceName' AS columnName, COUNT(*)::BIGINT AS violationCount FROM qa.monthlyCoverageAudit WHERE sourceName IS NULL
UNION ALL
SELECT 'qa.monthlyCoverageAudit' AS tableName, 'discoveredCount' AS columnName, COUNT(*)::BIGINT AS violationCount FROM qa.monthlyCoverageAudit WHERE discoveredCount IS NULL
UNION ALL
SELECT 'qa.monthlyCoverageAudit' AS tableName, 'fetchedCount' AS columnName, COUNT(*)::BIGINT AS violationCount FROM qa.monthlyCoverageAudit WHERE fetchedCount IS NULL
UNION ALL
SELECT 'qa.monthlyCoverageAudit' AS tableName, 'aliveCount' AS columnName, COUNT(*)::BIGINT AS violationCount FROM qa.monthlyCoverageAudit WHERE aliveCount IS NULL
UNION ALL
SELECT 'qa.monthlyCoverageAudit' AS tableName, 'deadCount' AS columnName, COUNT(*)::BIGINT AS violationCount FROM qa.monthlyCoverageAudit WHERE deadCount IS NULL
UNION ALL
SELECT 'qa.monthlyCoverageAudit' AS tableName, 'parsedCount' AS columnName, COUNT(*)::BIGINT AS violationCount FROM qa.monthlyCoverageAudit WHERE parsedCount IS NULL
UNION ALL
SELECT 'qa.monthlyCoverageAudit' AS tableName, 'validPostingCount' AS columnName, COUNT(*)::BIGINT AS violationCount FROM qa.monthlyCoverageAudit WHERE validPostingCount IS NULL
UNION ALL
SELECT 'qa.monthlyCoverageAudit' AS tableName, 'ocrAttemptCount' AS columnName, COUNT(*)::BIGINT AS violationCount FROM qa.monthlyCoverageAudit WHERE ocrAttemptCount IS NULL
UNION ALL
SELECT 'qa.monthlyCoverageAudit' AS tableName, 'ocrSuccessCount' AS columnName, COUNT(*)::BIGINT AS violationCount FROM qa.monthlyCoverageAudit WHERE ocrSuccessCount IS NULL
UNION ALL
SELECT 'qa.monthlyCoverageAudit' AS tableName, 'coverageStatus' AS columnName, COUNT(*)::BIGINT AS violationCount FROM qa.monthlyCoverageAudit WHERE coverageStatus IS NULL
UNION ALL
SELECT 'qa.monthlyCoverageAudit' AS tableName, 'coverageReason' AS columnName, COUNT(*)::BIGINT AS violationCount FROM qa.monthlyCoverageAudit WHERE coverageReason IS NULL
UNION ALL
SELECT 'qa.monthlyCoverageAudit' AS tableName, 'platformCoverageRegime' AS columnName, COUNT(*)::BIGINT AS violationCount FROM qa.monthlyCoverageAudit WHERE platformCoverageRegime IS NULL
UNION ALL
SELECT 'qa.monthlyCoverageAudit' AS tableName, 'auditVersion' AS columnName, COUNT(*)::BIGINT AS violationCount FROM qa.monthlyCoverageAudit WHERE auditVersion IS NULL
UNION ALL
SELECT 'qa.monthlyCoverageAudit' AS tableName, 'auditedAt' AS columnName, COUNT(*)::BIGINT AS violationCount FROM qa.monthlyCoverageAudit WHERE auditedAt IS NULL
UNION ALL
SELECT 'qa.sourcePolicyAudit' AS tableName, 'sourceName' AS columnName, COUNT(*)::BIGINT AS violationCount FROM qa.sourcePolicyAudit WHERE sourceName IS NULL
UNION ALL
SELECT 'qa.sourcePolicyAudit' AS tableName, 'policyVersion' AS columnName, COUNT(*)::BIGINT AS violationCount FROM qa.sourcePolicyAudit WHERE policyVersion IS NULL
UNION ALL
SELECT 'qa.sourcePolicyAudit' AS tableName, 'robotsStatus' AS columnName, COUNT(*)::BIGINT AS violationCount FROM qa.sourcePolicyAudit WHERE robotsStatus IS NULL
UNION ALL
SELECT 'qa.sourcePolicyAudit' AS tableName, 'termsStatus' AS columnName, COUNT(*)::BIGINT AS violationCount FROM qa.sourcePolicyAudit WHERE termsStatus IS NULL
UNION ALL
SELECT 'qa.sourcePolicyAudit' AS tableName, 'clientAccessMode' AS columnName, COUNT(*)::BIGINT AS violationCount FROM qa.sourcePolicyAudit WHERE clientAccessMode IS NULL
UNION ALL
SELECT 'qa.sourcePolicyAudit' AS tableName, 'transparentClientVerified' AS columnName, COUNT(*)::BIGINT AS violationCount FROM qa.sourcePolicyAudit WHERE transparentClientVerified IS NULL
UNION ALL
SELECT 'qa.sourcePolicyAudit' AS tableName, 'collectionBlocked' AS columnName, COUNT(*)::BIGINT AS violationCount FROM qa.sourcePolicyAudit WHERE collectionBlocked IS NULL
UNION ALL
SELECT 'qa.sourcePolicyAudit' AS tableName, 'verifiedAt' AS columnName, COUNT(*)::BIGINT AS violationCount FROM qa.sourcePolicyAudit WHERE verifiedAt IS NULL
UNION ALL
SELECT 'qa.sourcePolicyAudit' AS tableName, 'reviewerStatus' AS columnName, COUNT(*)::BIGINT AS violationCount FROM qa.sourcePolicyAudit WHERE reviewerStatus IS NULL
UNION ALL
SELECT 'qa.sourcePolicyAudit' AS tableName, 'evidenceSha256' AS columnName, COUNT(*)::BIGINT AS violationCount FROM qa.sourcePolicyAudit WHERE evidenceSha256 IS NULL
UNION ALL
SELECT 'qa.goldSample' AS tableName, 'goldId' AS columnName, COUNT(*)::BIGINT AS violationCount FROM qa.goldSample WHERE goldId IS NULL
UNION ALL
SELECT 'qa.goldSample' AS tableName, 'goldSetName' AS columnName, COUNT(*)::BIGINT AS violationCount FROM qa.goldSample WHERE goldSetName IS NULL
UNION ALL
SELECT 'qa.goldSample' AS tableName, 'targetType' AS columnName, COUNT(*)::BIGINT AS violationCount FROM qa.goldSample WHERE targetType IS NULL
UNION ALL
SELECT 'qa.goldSample' AS tableName, 'postingId' AS columnName, COUNT(*)::BIGINT AS violationCount FROM qa.goldSample WHERE postingId IS NULL
UNION ALL
SELECT 'qa.goldSample' AS tableName, 'goldValue' AS columnName, COUNT(*)::BIGINT AS violationCount FROM qa.goldSample WHERE goldValue IS NULL
UNION ALL
SELECT 'qa.goldSample' AS tableName, 'annotator' AS columnName, COUNT(*)::BIGINT AS violationCount FROM qa.goldSample WHERE annotator IS NULL
UNION ALL
SELECT 'qa.goldSample' AS tableName, 'doubleCodedFlag' AS columnName, COUNT(*)::BIGINT AS violationCount FROM qa.goldSample WHERE doubleCodedFlag IS NULL
UNION ALL
SELECT 'qa.goldSample' AS tableName, 'goldVersion' AS columnName, COUNT(*)::BIGINT AS violationCount FROM qa.goldSample WHERE goldVersion IS NULL
UNION ALL
SELECT 'qa.goldSample' AS tableName, 'labeledAt' AS columnName, COUNT(*)::BIGINT AS violationCount FROM qa.goldSample WHERE labeledAt IS NULL
UNION ALL
SELECT 'qa.evalRun' AS tableName, 'evalRunId' AS columnName, COUNT(*)::BIGINT AS violationCount FROM qa.evalRun WHERE evalRunId IS NULL
UNION ALL
SELECT 'qa.evalRun' AS tableName, 'targetType' AS columnName, COUNT(*)::BIGINT AS violationCount FROM qa.evalRun WHERE targetType IS NULL
UNION ALL
SELECT 'qa.evalRun' AS tableName, 'goldSetName' AS columnName, COUNT(*)::BIGINT AS violationCount FROM qa.evalRun WHERE goldSetName IS NULL
UNION ALL
SELECT 'qa.evalRun' AS tableName, 'predictorVersion' AS columnName, COUNT(*)::BIGINT AS violationCount FROM qa.evalRun WHERE predictorVersion IS NULL
UNION ALL
SELECT 'qa.evalRun' AS tableName, 'sampleCount' AS columnName, COUNT(*)::BIGINT AS violationCount FROM qa.evalRun WHERE sampleCount IS NULL
UNION ALL
SELECT 'qa.evalRun' AS tableName, 'passedGate' AS columnName, COUNT(*)::BIGINT AS violationCount FROM qa.evalRun WHERE passedGate IS NULL
UNION ALL
SELECT 'qa.evalRun' AS tableName, 'ranAt' AS columnName, COUNT(*)::BIGINT AS violationCount FROM qa.evalRun WHERE ranAt IS NULL
UNION ALL
SELECT 'qa.resultManifest' AS tableName, 'metricId' AS columnName, COUNT(*)::BIGINT AS violationCount FROM qa.resultManifest WHERE metricId IS NULL
UNION ALL
SELECT 'qa.resultManifest' AS tableName, 'metricName' AS columnName, COUNT(*)::BIGINT AS violationCount FROM qa.resultManifest WHERE metricName IS NULL
UNION ALL
SELECT 'qa.resultManifest' AS tableName, 'metricScope' AS columnName, COUNT(*)::BIGINT AS violationCount FROM qa.resultManifest WHERE metricScope IS NULL
UNION ALL
SELECT 'qa.resultManifest' AS tableName, 'cohortType' AS columnName, COUNT(*)::BIGINT AS violationCount FROM qa.resultManifest WHERE cohortType IS NULL
UNION ALL
SELECT 'qa.resultManifest' AS tableName, 'periodLabel' AS columnName, COUNT(*)::BIGINT AS violationCount FROM qa.resultManifest WHERE periodLabel IS NULL
UNION ALL
SELECT 'qa.resultManifest' AS tableName, 'dedupApplied' AS columnName, COUNT(*)::BIGINT AS violationCount FROM qa.resultManifest WHERE dedupApplied IS NULL
UNION ALL
SELECT 'qa.resultManifest' AS tableName, 'scriptPath' AS columnName, COUNT(*)::BIGINT AS violationCount FROM qa.resultManifest WHERE scriptPath IS NULL
UNION ALL
SELECT 'qa.resultManifest' AS tableName, 'scriptGitSha' AS columnName, COUNT(*)::BIGINT AS violationCount FROM qa.resultManifest WHERE scriptGitSha IS NULL
UNION ALL
SELECT 'qa.resultManifest' AS tableName, 'inputMartSha256' AS columnName, COUNT(*)::BIGINT AS violationCount FROM qa.resultManifest WHERE inputMartSha256 IS NULL
UNION ALL
SELECT 'qa.resultManifest' AS tableName, 'dataVersion' AS columnName, COUNT(*)::BIGINT AS violationCount FROM qa.resultManifest WHERE dataVersion IS NULL
UNION ALL
SELECT 'qa.resultManifest' AS tableName, 'computedAt' AS columnName, COUNT(*)::BIGINT AS violationCount FROM qa.resultManifest WHERE computedAt IS NULL
UNION ALL
SELECT 'qa.decisionLog' AS tableName, 'decisionId' AS columnName, COUNT(*)::BIGINT AS violationCount FROM qa.decisionLog WHERE decisionId IS NULL
UNION ALL
SELECT 'qa.decisionLog' AS tableName, 'decidedAt' AS columnName, COUNT(*)::BIGINT AS violationCount FROM qa.decisionLog WHERE decidedAt IS NULL
UNION ALL
SELECT 'qa.decisionLog' AS tableName, 'phase' AS columnName, COUNT(*)::BIGINT AS violationCount FROM qa.decisionLog WHERE phase IS NULL
UNION ALL
SELECT 'qa.decisionLog' AS tableName, 'topic' AS columnName, COUNT(*)::BIGINT AS violationCount FROM qa.decisionLog WHERE topic IS NULL
UNION ALL
SELECT 'qa.decisionLog' AS tableName, 'decision' AS columnName, COUNT(*)::BIGINT AS violationCount FROM qa.decisionLog WHERE decision IS NULL
UNION ALL
SELECT 'qa.decisionLog' AS tableName, 'rationale' AS columnName, COUNT(*)::BIGINT AS violationCount FROM qa.decisionLog WHERE rationale IS NULL
UNION ALL
SELECT 'qa.decisionLog' AS tableName, 'decidedBy' AS columnName, COUNT(*)::BIGINT AS violationCount FROM qa.decisionLog WHERE decidedBy IS NULL;

CREATE OR REPLACE VIEW qa.vSourcePolicyGate AS
SELECT sourceName, policyVersion, robotsStatus, termsStatus, clientAccessMode,
  transparentClientVerified, collectionBlocked, verifiedAt, reviewerStatus,
  CASE
    WHEN collectionBlocked THEN 'FAIL'
    WHEN robotsStatus = 'restricted' OR termsStatus = 'restricted' THEN 'FAIL'
    WHEN clientAccessMode = 'impersonatedOnly' THEN 'REVIEW_REQUIRED'
    WHEN robotsStatus <> 'notRestricted'
      OR termsStatus NOT IN ('reviewedConditional', 'permissionGranted', 'permitted')
      OR transparentClientVerified = FALSE
      OR reviewerStatus <> 'approved' THEN 'REVIEW_REQUIRED'
    ELSE 'PASS'
  END AS sourcePolicyGateStatus
FROM qa.sourcePolicyAudit;

CREATE OR REPLACE VIEW qa.vAnalysisReadyGate AS
WITH contractQa AS (
  SELECT
    (SELECT COALESCE(SUM(violationCount), 0) FROM qa.vPrimaryKeyViolations) AS primaryKeyViolations,
    (SELECT COALESCE(SUM(violationCount), 0) FROM qa.vForeignKeyViolations) AS foreignKeyViolations,
    (SELECT COALESCE(SUM(violationCount), 0) FROM qa.vEnumViolations) AS enumViolations,
    (SELECT COALESCE(SUM(violationCount), 0) FROM qa.vNullabilityViolations) AS nullabilityViolations
), evidence AS (
  SELECT
    (SELECT COUNT(*) FROM qa.monthlyCoverageAudit) AS coverageRows,
    (SELECT COUNT(*) FROM qa.evalRun) AS evalRows,
    (SELECT COUNT(*) FROM mart.postingAnalysisMart) AS postingMartRows,
    (SELECT COUNT(*) FROM mart.timeSeriesMart) AS timeSeriesRows,
    (SELECT COUNT(*) FROM qa.resultManifest) AS resultManifestRows,
    (SELECT COUNT(*) FROM qa.vSourcePolicyGate) AS sourcePolicyRows,
    (SELECT COUNT(*) FROM qa.vSourcePolicyGate WHERE sourcePolicyGateStatus = 'PASS') AS sourcePolicyPassRows,
    (SELECT COUNT(*) FROM qa.vSourcePolicyGate WHERE sourcePolicyGateStatus IN ('FAIL', 'REVIEW_REQUIRED')) AS sourcePolicyBlockingRows
)
SELECT contractQa.*, evidence.*,
  CASE
    WHEN primaryKeyViolations + foreignKeyViolations + enumViolations + nullabilityViolations > 0 THEN 'BLOCKED_CONTRACT'
    WHEN sourcePolicyBlockingRows > 0 THEN 'BLOCKED_SOURCE_POLICY'
    WHEN sourcePolicyRows = 0 OR sourcePolicyPassRows = 0
      OR coverageRows = 0 OR evalRows = 0 OR postingMartRows = 0 OR timeSeriesRows = 0 OR resultManifestRows = 0 THEN 'NOT_EVALUATED'
    ELSE 'EVIDENCE_PRESENT_REVIEW_REQUIRED'
  END AS analysisReadyStatus
FROM contractQa CROSS JOIN evidence;
