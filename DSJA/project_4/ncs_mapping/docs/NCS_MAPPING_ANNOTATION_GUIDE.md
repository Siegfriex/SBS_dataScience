# NCS Mapping Gold Annotation Guide (v1, template stage)

- 목표: `n = 300`, 이중코딩(두 명이 각각 독립적으로 라벨링) 비율 30%, Cohen's kappa ≥ 0.70
- 현재 상태: **템플릿만 존재, 실제 라벨 없음.** Agent 2의 duty-level input(트랙/섹션/evidenceText)이 없으면 채울 표본 자체를 뽑을 수 없다.

## 왜 이 가이드가 필요한가

RQ2-B 최종 매핑 품질 게이트(precision ≥ 0.85, coverage ≥ 0.80, lowConfidenceShare ≤ 0.20)는 정답(gold) 라벨 없이는 측정할 수 없다. 이 문서는 그 정답 라벨을 만드는 절차를 정의한다.

## 표본 추출 절차 (Agent 2 input 도착 후)

1. Agent 2가 넘긴 evidenceText 중 `ncsEligibleFlag=true`인 섹션에서 추출한다.
2. 연도·산업/직무군을 축으로 층화추출한다(가능하면 `stratified_detail_sample_n126`과 동일한 연도 축 사용 — 단, n=126은 mapping gold로 재사용하지 않는다. §0 규칙 참고).
3. n=300 중 30%(90건)는 두 명의 annotator가 독립적으로 라벨링하고 나머지 70%(210건)는 1인이 라벨링한다.
4. 이중코딩 90건에서 Cohen's kappa를 계산해 0.70 미만이면 가이드를 보완하고 재교육 후 재라벨링한다.

## Annotator 절차

각 evidenceText에 대해:

1. `candidateNcsUnitCodes`(retrieval이 제시한 top-5)를 확인한다.
2. 후보 중 실제로 해당 duty를 가장 잘 나타내는 코드를 고른다. 후보 중에 적합한 것이 없으면 `mappableFlag=false`로 표시하고 `goldNcsUnitCode`는 비워둔다 — 후보에 없는 코드를 임의로 만들어 채우지 않는다.
3. **도구명 단독 언급은 근거로 사용하지 않는다**(예: "Python 가능"만 있고 무엇을 하는지 설명이 없는 경우 `mappableFlag=false`). 도구+업무가 함께 명시된 경우만 매핑한다(예: "Python으로 ETL 파이프라인 구축").
4. `goldNcsLevel`은 evidenceText가 명시하는 업무의 난이도/책임범위를 근거로 판단하되, 원천 NCS 능력단위의 공식 수준(`ncsLevel`, 1~8)에서 고른다 — 임의 숫자를 만들지 않는다.
5. `reviewNote`에 판단 근거(왜 이 코드/레벨을 선택했는지, 애매했던 지점)를 남긴다.

## 이중코딩 불일치 조정(adjudication)

두 annotator의 라벨이 다르면 제3자(또는 두 annotator 간 논의)가 `adjudicatedLabel`을 정하고 `reviewNote`에 조정 사유를 남긴다. `adjudicatedLabel`이 채워진 행이 최종 gold 라벨이다.

## 템플릿 필드

| 필드 | 설명 |
|---|---|
| goldSampleId | 표본 고유 ID |
| trackId | Agent 2 트랙 ID |
| sectionId | Agent 2 섹션 ID |
| evidenceText | 원문 duty/task 텍스트 |
| candidateNcsUnitCodes | retrieval이 제시한 top-5 후보 (파이프 구분) |
| goldNcsUnitCode | annotator가 확정한 정답 코드 (없으면 공란) |
| goldNcsLevel | 정답 코드의 공식 NCS 수준(1~8) |
| mappableFlag | 후보 중 적합한 코드가 있었는지 여부 |
| annotator1 / annotator2 | 각 annotator 식별자 (단일 코딩 행은 annotator2 공란) |
| adjudicatedLabel | 이중코딩 불일치 조정 후 최종 라벨 |
| reviewNote | 판단 근거/애매한 지점 |

`data/gold/ncsMappings/gold_ncs_mapping_v1_TEMPLATE.csv`는 헤더만 있는 빈 템플릿이다.
