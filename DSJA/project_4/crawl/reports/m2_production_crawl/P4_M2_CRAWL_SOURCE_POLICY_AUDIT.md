# P4 M2 crawl source-policy audit

- Run ID: `M2_PREFLIGHT_20260806_01`
- Policy: `p4-linkareer-production-rate-v1` / `p4-linkareer-kill-switch-v1`
- Production network transport calls: `0`
- External ATS transport calls: `0`
- Query registry: `PASS`, SHA-256 `7715d7170ec4d033c6ec257aee4eebd34381b12cfc2be891a3b8d61f8655782e`
- Negative tests: `14/14 PASS`
- Approval artifact: `MISSING`
- Transparent-client production evidence: `REVIEW_REQUIRED`

The source-policy contract is fail-closed. Robots allowance and conditional terms review do not substitute for transparent-client evidence and a signed user approval. No Linkareer or external ATS request was issued by this preflight.
