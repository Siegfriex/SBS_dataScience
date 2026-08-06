# NCS 공공데이터 원천 실측 감사

- 기준일: 2026-08-06 / 조사: 백그라운드 리서치 에이전트(WebSearch/WebFetch), Agent 1(P4-A1-SOURCE) 검토
- 원칙: 데이터셋 ID/API 엔드포인트는 실제 확인된 것만 기재. 추측 금지.

## 원천별 요약

| # | sourceDataset | sourceUrl | datasetId | sourceVersion | license | recordCount | accessMethod | redistributable |
|---|---|---|---|---|---|---|---|---|
| 1 | 한국산업인력공단_국가직무능력표준 정보_20251231 | data.go.kr/data/15083321/fileData.do | 15083321 | 수정일 2026-02-20, 연간 갱신 | 공공저작물 자유이용허락 제1유형(출처표시) | 13,343건 | CSV 다운로드 + 오픈API 병행 | true |
| 2 | 한국산업인력공단_NCS 기준정보 조회 | data.go.kr/data/15128213/openapi.do | 15128213 | 수정일 2025-06-09 | 이용허락범위 제한 없음, 무료 | - | REST API(인증키 필요) | true(라이선스상), 스키마 실호출 재검증 필요 |
| 3 | 한국산업인력공단_NCS고교직업교육과정 정보 서비스_GW | data.go.kr/data/15157542/openapi.do | 15157542 | 수정일 2026-03-05 | "제한 없음" 명시되나 유료 표기와 불일치 — **재확인 필요** | - | REST API(인증키 필요) | 확인 불가 |
| 4 | 한국산업인력공단_NCS 관련 정보 서비스 | data.go.kr/data/15063879/openapi.do | 15063879 | 수정일 2025-06-25 | 이용허락범위 제한 없음, 무료 | - | REST API(인증키 필요), 실제 서비스: c.q-net.or.kr/openapi/Ncs1info/ncsinfo.do | true |
| 5 | NCS 통합포털 학습모듈 파일 검색 | ncs.go.kr/unity/th03/ncsModuleFileSearch.do | (데이터셋 ID 없음, 검색기능) | 상시 갱신 | 공공누리 제2유형(비상업, 출처표시) + 개별 삽화/사진 별도 동의 필요 | 미확인 | 웹검색 + PDF 개별 다운로드 | **false** — 로컬 참조·매핑근거 추출 전용, Git 커밋 금지 |

## 필드 상세

- **#1(능력단위 파일데이터)**: 분류번호, 명칭, 수준(1~8), 훈련시간 — 4개 필드만. `ncs.ncsUnit`의 `ncsUnitCode/ncsUnitName/ncsLevel/trainingHours`에 직접 매핑 가능.
- **#2(기준정보 API)**: 대/중/소/세분류 조회 + 능력단위분류코드 조회 + 능력단위요소 조회 + 키워드 검색, 7개 오퍼레이션 확인. **응답 스키마는 Swagger가 이미지로만 제공되어 텍스트로 미확인 — 인증키 발급 후 실호출 검증 전까지 파이프라인 설계 착수 보류 권고.**
- **#3(고교직업교육과정 API)**: 5개 원천 중 유일하게 불완전. KSA(지식·기술·태도)·능력단위요소·수행준거가 실제로 이 API 응답에 포함되는지 **텍스트 근거로 확증 못 함**(활용신청 16건으로 사용사례 희소). 이전 세션에서 이 API에 이 필드들이 있다고 전제했던 것은 **미검증 가정이었음이 이번 조사로 드러남**.
- **#4(관련 정보 서비스)**: 응답 필드 명확 확인 — `ncsClCd/compeUnitName/compeUnitLevel/ncsLclasCdnm/ncsMclasCdnm/ncsSclasCdnm/ncsSubdCdnm/compeUnitDef`. 5개 중 스키마가 가장 명확하며 #1의 수준값과 즉시 교차검증 가능.
- **#5(학습모듈)**: 비정형 PDF, API 없음. 저작권 제약은 프로젝트의 기존 방침(로컬 전용, redistributable=FALSE)과 실측이 정확히 일치.

## 핵심 리스크 — KSA/수행준거 원천 불확실

담당업무·자격요건을 NCS 능력단위요소 수준까지 매핑하려면 KSA·수행준거가 필요한데, 이를 제공하는 유일한 후보(#3)의 실제 필드 구성이 검증되지 않았다. **만약 #3에 KSA가 없다면, 매핑 근거는 결국 #5(학습모듈 PDF)의 비정형 텍스트 추출에 의존하게 되고, 이는 추가 OCR/텍스트파싱 엔지니어링과 재배포 제약(로컬 전용) 하의 매핑 근거 사용이라는 두 가지 제약이 동시에 걸린다.**

## 다음 단계 (필수)

data.go.kr에서 인증키를 발급받아 #3 API를 1회 실제 호출해 응답에 KSA/능력단위요소/수행준거 필드가 실재하는지 확정하는 것이 NCS 매핑 파이프라인(PROMPT 11/12 상당) 착수 전 반드시 선행돼야 한다. 이 인증키 발급은 사람 계정으로 진행해야 하는 절차라 Agent 1이 자동으로 수행할 수 없다.

## 2026-08-06 추가 진전 — 사람이 API 키 제공, 실호출 시도

사용자가 data.go.kr 일반 인증키를 제공(엔드포인트 `https://apis.data.go.kr/B490007/ncsSchoolInfo`). 실제 호출로 확인한 것:

- 서비스 URL 뒤에 오퍼레이션 번호가 붙는 패턴(`{service}/openapi{N}`)을 다른 한국산업인력공단 NCS API들(예: `ncsEduCource/openapi20`, `ncsStudyModule/openapi21`)에서 역추적으로 발견
- `openapi1`~`openapi30`을 전수 시도한 결과 **`openapi14`만 유효**(`NO_OPENAPI_SERVICE_ERROR`가 아니라 `필수 파라미터를 확인하여 주십시요`(코드 009) 반환) — **엔드포인트 자체는 실재하고 키도 유효함이 확정**
- 그러나 `pageNo`/`numOfRows`/`type` 외 필수로 요구되는 추가 파라미터명을 15개 이상 시도(ncsClCd, searchNm, schulCrseCd, schulKndCd, trng2Cd, schulNm, searchWrd, ncsLclasCd, year, trngCourseNm 등)했으나 **전부 동일한 "필수 파라미터 확인" 오류만 반환** — 정확한 파라미터명은 여전히 미확정
- Swagger UI를 Node/patchright로 직접 로드해 네트워크 요청을 스니핑했으나, 이 데이터셋(게이트웨이형, `_GW`)은 실제로 이미지 8장짜리 가이드만 제공하고 인터랙티브 스펙 자체가 없음을 재확인

**결론**: KSA_SOURCE_STATUS는 여전히 `UNVERIFIED`이나, 상태가 "완전 미확인"에서 **"엔드포인트·키 유효성 확인됨, 요청 스키마만 미확정"으로 좁혀짐**. 다음 중 하나가 필요: (a) 한국산업인력공단 담당자에게 직접 문의, (b) data.go.kr 고객센터에 파라미터 스펙 요청, (c) 이 API를 실제로 사용한 타 개발자 코드/블로그 추가 검색.

