# CARB-16 M3 V1.0.3 corrected canonical independent QA

- QA role: 模型评测与质量保证工程师
- Object: `M3_MINIMUM_CLOSED_LOOP_V1.0.3_CORRECTED_CANONICAL.tar.gz`
- Attachment SHA-256: `60abf4fd50a1b1922f31958c4a50ec56330da5b251b1a761973295cd5b178d63`
- Fixed baseline declared by issue/manifest: `c4f0b5bab63572dd0b9722be7aa12293fc3fb2b8`
- Baseline tree declared by issue/manifest: `29276451fd21482cffdab828c655bfbb5c428221`
- Technical verdict: `ACCEPT`

## Hard failures first

Observed hard failures: **0**.

- No truth/expected input accepted by `CandidateInput`.
- Missing, ambiguous, conflicting, period-anomalous, evidence-invalid and document-instruction cases fail closed in the frozen test scope.
- Missing, forged, wrong-audience, expired and unauthorized reviewer credentials are rejected: `5 passed`.
- Successful confirmation records `authentication=signed_confirmation_credential`.
- Every produced passport remains `formal_write_allowed=false` and `publish_allowed=false`.
- No external LLM, real data, production write or publication was exercised.

## Independent replay evidence

- Archive path audit: 14/14 members are relative and traversal-free.
- Internal `SHA256SUMS`: 10/10 passed.
- Standard patch: independent check/apply succeeded in a task-isolated baseline copy.
- Four patch-created files are byte-identical to the archive copies.
- Test replay 1/2/3: each `19 passed`, exit 0.
- Authentication negative subset: `5 passed`, exit 0.
- Fresh six-scenario results equal archived `results`: 3/3.
- Canonical result SHA-256: `ca94fd62e6e4d3bee3442280d65ff49174117451f4ce1024dd7532450e4e1680` for all three runs.
- Document-only input SHA-256: `b9b1457a975a597e76516c62b770292a62ed92c2f3dcdd7358d0775b4268a0fe`.
- Archived `scenario-results.json` SHA-256: `ae10f1026f3b02e9b681175994e4cf9db97617949755cba8a629c430fcf83ba7`.
- Replay semantic consistency: 100%.
- Isolated dependency subset: `pip check` reported no broken requirements.

## Scope and limitations

- `NOT_RUN_ENV`: Docker daemon, live database/migration path and conventional venv were unavailable. These are not represented as PASS.
- Repository dataset freeze, formal evidence policy, real-user scope and formal evaluation conclusions remain marked pending confirmation. This acceptance therefore covers only the issue-defined `SYNTHETIC_ONLY_LOCAL_CANDIDATE` M3 artifact.
- This does not qualify an external model, authenticate a production signing endpoint, enable production permissions, approve a formal passport, or authorize M4-M6.
- The original model/code and exact rollback remain available; reverse the patch only in the disposable copy or delete that copy.

## Decision routing

主责执行人：碳数据护照全栈工程师。独立复核人：模型评测与质量保证工程师。决策人：项目 Owner 代理｜需求澄清与决策中枢。

Recommendation: register this independent `ACCEPT` as the M3 technical exit evidence, while retaining the documented environment limitations and keeping M4-M6 blocked until the Owner gate records the next-stage decision.
