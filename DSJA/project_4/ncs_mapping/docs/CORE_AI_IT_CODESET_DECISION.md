# Core AI·IT NCS Codeset — Draft Decision Record

- codeSetVersion: `core-ai-it-v0.1`
- status: `REVIEW_REQUIRED` (NOT frozen — do not treat as final until Agent 3/사용자 승인)
- granularity: `ncsSubCode` (8-digit major+middle+minor+sub prefix, i.e. NCS 세분류)

## 왜 이 범위인가

`data/processed/ncsUnit.parquet`(13,442행)의 `majorCode`를 실제로 group-by해서 각 대분류의 대표 능력단위명을 확인한 결과, **majorCode=20**이 유일하게 정보통신(ICT) 성격을 갖는 대분류임을 경험적으로 확인했다(예: `정보기술 전략 기획`, `교환시스템 구축계획`, `중계방송기획`). 이 원천 CSV에는 대분류명 자체가 없으므로(§Phase A `missingHierarchyRate` 발견 참고), 이름을 임의로 붙이지 않고 대표 능력단위명으로만 판단했다.

majorCode=20은 middleCode 3개로 나뉜다:

| middleCode | 대표 능력단위명 | 세분류(subCode) 수 | 능력단위 수 | 포함 여부 |
|---|---|---|---|---|
| 01 | 정보기술 전략 기획, SW아키텍처 수행 관리, 인공지능 플랫폼 구축 계획 | 69 | 691 | **INCLUDED** |
| 02 | 교환시스템 구축계획, 무선통신망구축, 위성통신서비스 기획 | 38 | 405 | 제외 (검토 대상) |
| 03 | 중계방송기획, TV방송 기술기획, DMB 서비스 기획 | 13 | 158 | 제외 (검토 대상) |

`middle=01`(정보기술)은 minorCode 11개로 다시 나뉘며, 그 구성이 명확히 소프트웨어/IT 직무 스펙트럼과 대응한다:

```
minor01 정보기술전략/컨설팅/IT비즈니스분석 (8개 subCode)
minor02 SW아키텍처/요구사항/DB/네트워크/보안/UI-UX/시스템SW/빅데이터/핀테크/클라우드/IoT (17개 subCode)
minor03 IT운영/기술지원/빅데이터운영/IoT운영/데이터거래 (6개 subCode)
minor04 IT프로젝트관리/품질/테스트/감리 (4개 subCode)
minor05 기술영업/IT마케팅 (2개 subCode)
minor06 정보보호/보안(암호,생체인식,OT보안,클라우드보안,SW공급망보안 등) (14개 subCode)
minor07 인공지능(플랫폼/서비스/모델/학습데이터/생성형AI) (7개 subCode)
minor08 블록체인 (3개 subCode)
minor09 스마트물류 (3개 subCode)
minor10 디지털트윈 (3개 subCode)
minor11 개인정보보호 (3개 subCode)
```

`middle=02`(통신)와 `middle=03`(방송)은 통신망/방송 설비 구축·서비스 기획이 중심이라 "AI·IT 소프트웨어 직무"라는 이번 프로젝트의 직무 매핑 범위와는 결이 다르다고 잠정 판단해 v0.1에서는 제외했다. 다만 완전히 삭제하지 않고 `included=false`로 `configs/core_ai_it_codes.yaml`에 남겨두었으므로, 검토자가 통신망 엔지니어/방송 기술직 채용공고를 RQ2-B 범위에 포함하고 싶다면 그대로 뒤집을 수 있다.

## Cross-major AI 키워드 후보 (subCode 단위 포함 아님, 검토용 개별 unit만 나열)

`majorCode=20` 밖에서 능력단위명에 `인공지능/머신러닝/딥러닝/빅데이터/데이터사이언스/데이터분석/챗봇/자연어처리/컴퓨터비전` 키워드가 명시적으로 포함된 유닛 9건을 발견했다(`data/interim/cross_major_ai_candidates.csv`):

| ncsUnitCode | ncsUnitName | majorCode | matchedKeyword |
|---|---|---|---|
| 0201030211_21v4 | 고객데이터 분석 | 02(경영·회계·사무) | 데이터 분석 |
| 0803020530_18v4 | 게임 인공지능프로그래밍 | 08(문화·예술·디자인·방송) | 인공지능 |
| 0902010213_16v2 | 견인정수 데이터 분석 | 09(운전) | 데이터 분석 |
| 0902010215_16v2 | 열차운영 계획시스템 데이터 분석 | 09(운전) | 데이터 분석 |
| 1402030415_21v1 | 공간빅데이터 분석 | 14(건설) | 빅데이터 |
| 1402030417_21v1 | 공간빅데이터 서비스 프로그래밍 | 14(건설) | 빅데이터 |
| 1504010310_20v3 | 기계품질 데이터분석 | 15(기계) | 데이터분석 |
| 1901040210_14v1 | 전력 빅데이터 분석 소프트웨어 설계 | 19(전기·전자) | 빅데이터 |
| 2305060204_24v2 | BEMS 운영 데이터 분석 | 23(환경·에너지·안전) | 데이터 분석 |

이들은 각자 다른 subCode 그룹에 속해 있고 같은 그룹 내 다른 능력단위는 대부분 해당 산업 도메인 고유 업무이므로, subCode 그룹 전체를 끌어오지 않고 **unit 단위 후보로만** 남겨둔다. 최종 채택 여부는 사용자/Agent 3 검토 후 결정한다.

## 알려진 한계

1. **ncsSubName은 공식 명칭이 아니다** — 원천 CSV에 세분류명 컬럼이 없어 각 subCode 그룹의 첫 번째 능력단위명(코드 정렬 기준)을 대표 라벨로 사용했다. `configs/core_ai_it_codes.yaml`의 모든 행에 `subNameIsDerived: true`로 명시했다.
2. **middle=02/03 제외는 임시 판단** — 통신/방송 인프라 구축 직무가 이번 RQ2-B AI·IT job market 분석 범위에 포함되는지는 도메인 판단이 필요하다.
3. **결과를 보고 포함 코드를 조정하지 않았다** — 지침(§6)에 따라 이 v0.1은 최초 산출값 그대로이며, Agent 3·사용자 승인 후 `core-ai-it-v1.0`/`status=FROZEN`으로 승격한다.
