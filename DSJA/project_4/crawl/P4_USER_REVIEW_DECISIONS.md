# USER REVIEW DECISIONS

| ID | 사용자 검수 내용 | v2 반영 |
|---|---|---|
| UR01 | NCS와 링커리어로 원천 제한 | 공식 분석 원천을 두 개로 고정 |
| UR02 | 공무원 급수는 보조, NCS가 주안 | 공무원·공공 앵커 전체 제거 |
| UR03 | RQ1·RQ2 중심 | 주 분석으로 승격 |
| UR04 | 유사도는 보조 | `AUX_SIMILARITY`로 분리 |
| UR05 | RQ4는 독립 분석 | `allJobs` 코호트로 분리 |
| UR06 | RQ5는 수동 사례 | `caseStudyRegistry`만 유지 |
| UR07 | 50대 분석 제거 | 데이터·스키마·기사 흐름에서 삭제 |
| UR08 | E0~E3/U 유지 | 일반 채용 `careerClass`로 구현 |
| UR09 | 경험조건부 인턴 | `internAccessClass`, `restrictedInternFlag`, `experiencedInternFlag`로 분리 |
| UR10 | 필수조건 중심 | 주 결과는 필수요건만 사용, 우대는 보조 |
| UR11 | NCS 1~8을 4범주 | `level1to2`~`level7to8` |
| UR12 | 국가공인 자격증 등급 | `certificateClass` 추가 |
| UR13 | highDemand 산식 미정 | nullable 예약컬럼, 분석 사용 금지 |
| UR14 | 3개월 중복 제거 | 90일 재게시 그룹·최초 게시월 사용 |
| UR15 | 이미지 공고 OCR | asset·OCR lineage 테이블 추가 |
| UR16 | 공고 수만 측정 | RQ1은 distinct postingId, 인원수 미사용 |
| UR17 | mixed 처리 검토 | posting과 track 분리, 강제배분 금지 |
