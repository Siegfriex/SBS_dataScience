-- Input contract: rq2b_mapping_input is the output of
-- p4.marts.rq2b.prepare_rq2b_mapping_input.

CREATE OR REPLACE TEMP VIEW rq2b_eligible_chunk_status AS
SELECT * EXCLUDE (_status_priority, _rn)
FROM (
    SELECT
        *,
        CASE mappingStatus
            WHEN 'ACCEPTED_SINGLE' THEN 0
            WHEN 'ACCEPTED_MULTI' THEN 1
            WHEN 'ABSTAIN' THEN 2
            WHEN 'UNMAPPED' THEN 3
            WHEN 'OUT_OF_SCOPE' THEN 4
        END AS _status_priority,
        row_number() OVER (
            PARTITION BY periodMonth, jobCohort, sourceRole, chunkId
            ORDER BY _status_priority
        ) AS _rn
    FROM rq2b_mapping_input
    WHERE ncsEligibleFlag
)
WHERE _rn = 1;

CREATE OR REPLACE TEMP VIEW rq2b_accepted_primary AS
SELECT * EXCLUDE (_rn)
FROM (
    SELECT
        *,
        row_number() OVER (
            PARTITION BY periodMonth, jobCohort, sourceRole, trackId, ncsUnitCode
            ORDER BY chunkId
        ) AS _rn
    FROM rq2b_mapping_input
    WHERE ncsEligibleFlag AND mappingStatus IN ('ACCEPTED_SINGLE', 'ACCEPTED_MULTI')
)
WHERE _rn = 1;

CREATE OR REPLACE TEMP VIEW rq2b_unit_mention_intensity_mart AS
SELECT
    periodMonth,
    jobCohort,
    sourceRole,
    trackId,
    ncsUnitCode,
    count(DISTINCT chunkId)::BIGINT AS unitMentionIntensity,
    'p4-rq2b-mart-v4.0.0' AS rq2bMartVersion
FROM rq2b_mapping_input
WHERE ncsEligibleFlag AND mappingStatus IN ('ACCEPTED_SINGLE', 'ACCEPTED_MULTI')
GROUP BY ALL;

CREATE OR REPLACE TEMP VIEW rq2b_weighted_levels AS
SELECT
    *,
    sum(mappingWeight) OVER (
        PARTITION BY periodMonth, jobCohort, sourceRole
    ) AS _total_weight,
    sum(mappingWeight) OVER (
        PARTITION BY periodMonth, jobCohort, sourceRole
        ORDER BY ncsLevel, trackId, ncsUnitCode
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS _cumulative_weight
FROM rq2b_accepted_primary;

CREATE OR REPLACE TEMP VIEW rq2b_weighted_median AS
SELECT
    periodMonth,
    jobCohort,
    sourceRole,
    min(ncsLevel) FILTER (WHERE _cumulative_weight >= _total_weight / 2.0) AS ncsLevelWeightedMedian
FROM rq2b_weighted_levels
GROUP BY ALL;

CREATE OR REPLACE TEMP VIEW rq2b_chunk_counts AS
SELECT
    periodMonth,
    jobCohort,
    sourceRole,
    count(*)::BIGINT AS ncsEligibleChunkCount,
    sum((mappingStatus = 'ACCEPTED_SINGLE')::INTEGER)::BIGINT AS acceptedSingleCount,
    sum((mappingStatus = 'ACCEPTED_MULTI')::INTEGER)::BIGINT AS acceptedMultiCount,
    sum((mappingStatus = 'ABSTAIN')::INTEGER)::BIGINT AS abstainCount,
    sum((mappingStatus = 'UNMAPPED')::INTEGER)::BIGINT AS unmappedCount,
    sum((mappingStatus = 'OUT_OF_SCOPE')::INTEGER)::BIGINT AS outOfScopeCount,
    sum((mappingStatus IN ('ACCEPTED_SINGLE', 'ACCEPTED_MULTI'))::INTEGER)::BIGINT AS acceptedMappedChunkCount
FROM rq2b_eligible_chunk_status
GROUP BY ALL;

CREATE OR REPLACE TEMP VIEW rq2b_accepted_weights AS
SELECT
    periodMonth,
    jobCohort,
    sourceRole,
    sum(mappingWeight)::DOUBLE AS acceptedMappedWeight,
    sum(CASE WHEN ncsBand IN ('level5to6', 'level7to8') THEN mappingWeight ELSE 0 END)::DOUBLE AS advancedWeight
FROM rq2b_accepted_primary
GROUP BY ALL;

CREATE OR REPLACE TEMP VIEW rq2b_mapping_coverage_mart AS
SELECT
    c.periodMonth,
    c.jobCohort,
    c.sourceRole,
    c.ncsEligibleChunkCount,
    c.acceptedSingleCount,
    c.acceptedMultiCount,
    c.abstainCount,
    c.unmappedCount,
    c.outOfScopeCount,
    c.acceptedMappedChunkCount,
    coalesce(w.acceptedMappedWeight, 0.0)::DOUBLE AS acceptedMappedWeight,
    c.acceptedMappedChunkCount::DOUBLE / nullif(c.ncsEligibleChunkCount, 0) AS mappingCoverage,
    w.advancedWeight / nullif(w.acceptedMappedWeight, 0) AS advancedDutyShareAccepted,
    coalesce(w.advancedWeight, 0.0) / nullif(c.ncsEligibleChunkCount, 0) AS advancedDutyShareEligibleLowerBound,
    m.ncsLevelWeightedMedian::DOUBLE AS ncsLevelWeightedMedian,
    'p4-rq2b-mart-v4.0.0' AS rq2bMartVersion
FROM rq2b_chunk_counts c
LEFT JOIN rq2b_accepted_weights w
  ON c.periodMonth = w.periodMonth AND c.jobCohort = w.jobCohort AND c.sourceRole = w.sourceRole
LEFT JOIN rq2b_weighted_median m
  ON c.periodMonth = m.periodMonth AND c.jobCohort = m.jobCohort AND c.sourceRole = m.sourceRole;

CREATE OR REPLACE TEMP VIEW rq2b_band_weights AS
SELECT
    periodMonth,
    jobCohort,
    sourceRole,
    ncsBand,
    sum(mappingWeight)::DOUBLE AS acceptedWeight
FROM rq2b_accepted_primary
GROUP BY ALL;

CREATE OR REPLACE TEMP VIEW rq2b_band_distribution_mart AS
WITH bands(ncsBand, ncsBandDisplayAlias) AS (
    VALUES
        ('level1to2', 'B1'),
        ('level3to4', 'B2'),
        ('level5to6', 'B3'),
        ('level7to8', 'B4')
), accepted_bands AS (
    SELECT
        c.periodMonth,
        c.jobCohort,
        c.sourceRole,
        'ACCEPTED_BAND' AS distributionCategory,
        b.ncsBand,
        b.ncsBandDisplayAlias,
        coalesce(w.acceptedWeight, 0.0)::DOUBLE AS acceptedWeight,
        NULL::BIGINT AS eligibleStatusCount,
        coalesce(a.acceptedMappedWeight, 0.0)::DOUBLE AS acceptedMappedDenominator,
        c.ncsEligibleChunkCount::BIGINT AS allEligibleDenominator,
        coalesce(w.acceptedWeight, 0.0) / nullif(a.acceptedMappedWeight, 0) AS bandShareAccepted,
        coalesce(w.acceptedWeight, 0.0) / nullif(c.ncsEligibleChunkCount, 0) AS bandShareEligibleLowerBound,
        'p4-rq2b-mart-v4.0.0' AS rq2bMartVersion
    FROM rq2b_chunk_counts c
    CROSS JOIN bands b
    LEFT JOIN rq2b_band_weights w
      ON c.periodMonth = w.periodMonth AND c.jobCohort = w.jobCohort
     AND c.sourceRole = w.sourceRole AND b.ncsBand = w.ncsBand
    LEFT JOIN rq2b_accepted_weights a
      ON c.periodMonth = a.periodMonth AND c.jobCohort = a.jobCohort AND c.sourceRole = a.sourceRole
), excluded_statuses AS (
    SELECT periodMonth, jobCohort, sourceRole, 'ABSTAIN' AS ncsBand, abstainCount AS eligibleStatusCount FROM rq2b_chunk_counts
    UNION ALL
    SELECT periodMonth, jobCohort, sourceRole, 'UNMAPPED', unmappedCount FROM rq2b_chunk_counts
    UNION ALL
    SELECT periodMonth, jobCohort, sourceRole, 'OUT_OF_SCOPE', outOfScopeCount FROM rq2b_chunk_counts
), excluded_rows AS (
    SELECT
        e.periodMonth,
        e.jobCohort,
        e.sourceRole,
        'EXCLUDED_STATUS' AS distributionCategory,
        e.ncsBand,
        e.ncsBand AS ncsBandDisplayAlias,
        0.0::DOUBLE AS acceptedWeight,
        e.eligibleStatusCount::BIGINT AS eligibleStatusCount,
        coalesce(a.acceptedMappedWeight, 0.0)::DOUBLE AS acceptedMappedDenominator,
        c.ncsEligibleChunkCount::BIGINT AS allEligibleDenominator,
        NULL::DOUBLE AS bandShareAccepted,
        NULL::DOUBLE AS bandShareEligibleLowerBound,
        'p4-rq2b-mart-v4.0.0' AS rq2bMartVersion
    FROM excluded_statuses e
    JOIN rq2b_chunk_counts c
      ON e.periodMonth = c.periodMonth AND e.jobCohort = c.jobCohort AND e.sourceRole = c.sourceRole
    LEFT JOIN rq2b_accepted_weights a
      ON e.periodMonth = a.periodMonth AND e.jobCohort = a.jobCohort AND e.sourceRole = a.sourceRole
)
SELECT * FROM accepted_bands
UNION ALL
SELECT * FROM excluded_rows;
