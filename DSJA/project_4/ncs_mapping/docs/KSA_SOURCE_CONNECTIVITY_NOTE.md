# KSA Source (dataset 15157542) — Connectivity Verification Note

- `KSA_SOURCE_STATUS = UNVERIFIED` **remains unchanged**. No real records were retrieved. This note documents a connectivity test only, per the operator supplying a personal data.go.kr API key on 2026-08-06.
- The API key itself is stored only in `DSJA/project_4/ncs_mapping/.env` (gitignored, `chmod 600`), never committed.

## What was tested

Endpoint given: `https://apis.data.go.kr/B490007/ncsSchoolInfo` (dataset 15157542, "한국산업인력공단_NCS고교직업교육과정 정보 서비스_GW").

The bare endpoint returns `NO_OPENAPI_SERVICE_ERROR` — it requires an operation path segment. The full Swagger/OpenAPI spec was recovered from the dataset's public detail page (`www.data.go.kr/data/15157542/openapi.do`), revealing exactly **one** exposed operation:

```
GET https://apis.data.go.kr/B490007/ncsSchoolInfo/openapi14
```

### Request parameters (per the recovered swagger doc)

| param | required | description |
|---|---|---|
| serviceKey | yes | data.go.kr issued key |
| returnType | yes | response format (tested with `xml`) |
| mcdNm | yes | 교과목명 (curriculum subject name) — **exact match, no wildcard/list operation exists** |
| targYy | yes | 대상년도 |
| cdName | no | 고교능력단위코드명 |

### Response fields (this is the valuable part for Phase B)

`lcd/lcdNm`(교과군코드/명), `mcd/mcdNm`(교과목코드/명), `ncsLclasCd/ncsLclasCdnm`(대분류코드/명), `ncsMclasCd/ncsMclasCdnm`(중분류코드/명), `ncsSclasCd/ncsSclasCdnm`(소분류코드/명), `ncsSubdCd/ncsSubdCdnm`(세분류코드/명), `cd/cdName`(고교능력단위코드/명), `ncsClCd`, `dutySvcNo`, `targYy`.

**This response shape, if it could be bulk-retrieved, would directly fill the `majorName`/`middleName`/`minorName`/`subName` gap identified in the Phase A acceptance audit** (`data/ncs/ncsUnit_20260806.csv` has codes but no hierarchy names). It cannot be bulk-retrieved with the current key/operation, see below.

## Connectivity test results

```
serviceKey valid, auth OK        -- confirmed (distinct error codes for missing-param vs bad-value vs no-match, not an auth-rejection code)
code 009 "필수 파라미터를 확인하여 주십시요"  -- when mcdNm/targYy omitted
code 001 "mcdNm 값을 확인하여 주십시요"      -- when mcdNm is blank/whitespace
code 002 "empty data"                        -- when mcdNm/targYy are well-formed but no record matches
```

Tried `mcdNm` values: several plausible 전문교과 subject names (e.g. "성공적인 직업생활", the sole 전문공통과목) across `targYy` 2020–2025, plus several real leaf `ncsUnitName` values sampled from the already-verified `ncsUnitCode` source, plus wildcard-style values (`%`, `*`). All returned code 002 (empty data) — none is confirmed as a genuinely valid `mcdNm`.

## Why this blocks bulk ingestion (not just "not tried yet")

The service exposes **no list/search/pagination operation** — only exact-match lookup by `mcdNm` + `targYy`. There is no companion operation on this same host (`B490007`) to enumerate valid subject names; the swagger spec lists exactly one `operationId` (`openapi14`). Populating this source at scale would require an external authoritative list of 전문교과 subject names (e.g. from KRIVET/moe.go.kr curriculum guides), which is outside this release's scope and outside data.go.kr's own API surface for this dataset.

## Disposition

- `KSA_SOURCE_STATUS = UNVERIFIED` stays as-is; no KSA fields populated anywhere in `data/processed/ncsUnit.parquet`.
- The request/response schema above is preserved here so a future pass (once a valid subject-name list is sourced) doesn't have to re-discover the API shape.
- If the operator wants to pursue this further, the next concrete step is sourcing an authoritative 전문교과 교과목명 list (e.g. from KRIVET's `2022 개정 직업계고 교육과정 편성·운영 안내서`), not further blind-guessing against this endpoint.
