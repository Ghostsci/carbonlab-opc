# M3 Candidate Passport V1.0.3 authenticated-confirmation manifest

- mode: `SYNTHETIC_ONLY_LOCAL_CANDIDATE`
- baseline: `main@c4f0b5bab63572dd0b9722be7aa12293fc3fb2b8` (tree `29276451fd21482cffdab828c655bfbb5c428221`)
- provider: frozen `static/static-v1`, invoked through `StaticProvider`; output is derived only from `CandidateInput(scenario_id, documents)`
- pipeline/runtime/artifact version: `m3-candidate-passport-v1.0.3`
- candidate verdict: `CHANGES_REQUIRED` pending clean-clone DevSecOps replay and independent QA

## QA hard-gate fixes

1. `CandidateInput(extra="forbid")` cannot contain `truth` or `expected`; the extraction path never reads them.
2. The provider output is reconstructed from document bytes. Tampering both truth and expected output to `1` while leaving the document at `2144.05 t` leaves the candidate at `2144.05`.
3. Extracted values and units must occur in their cited evidence quote; quote presence alone is insufficient.
4. `actor_type` and `actor_id` remain absent from request-owned `ConfirmationAction`. Confirmation now requires an opaque JWT signed with the server authentication secret; the use boundary verifies signature, `passport_confirmation` type, `carbon-passport-confirmation` audience, expiry, subject and authorized role. The V1.0.2 public identity factory was removed.
5. Negative tests cover missing token, forged signature, wrong audience, expired identity and unauthorized role.
6. Expected business guard rejections are `PASS/outcome=expected_rejection`, not `FAIL_CODE`.
7. Runtime constant, contract, tests, manifest, logs and archive use V1.0.3.

## File SHA-256 (before final archive)

- `backend/services/candidate_passport_v1.py`: `e4041e6b55ffa2740eb2ba64b197f542605400e1a60e5f3aca7686385c3cd385`
- `backend/tests/test_candidate_passport_v1.py`: `4373d1e403072f101c5856f9c7cab220ee37c02b78bc82e809e899d3c7a7158a`
- `ai/memory-bank/05-product/confirmation-workflow.md`: `c8f9f39792584b214e7c350e8bf7403513aa0b73e6e389777d8fd48c1fa539c7`
- `scenario-results.json`: `ae10f1026f3b02e9b681175994e4cf9db97617949755cba8a629c430fcf83ba7`
- `failure-samples.json`: `98f889bc12bd07eda197656559af062efe75769d20dc511f6679e84ac586c0d0`
- replay logs (each): `8b7446f7147a497fc151d2ebe50105daa6b969eb69136250f107b516bf7920eb`

## Input/output hashes

- six-scenario document-only input SHA-256: `b9b1457a975a597e76516c62b770292a62ed92c2f3dcdd7358d0775b4268a0fe`
- canonical result SHA-256, runs 1/2/3: `ca94fd62e6e4d3bee3442280d65ff49174117451f4ce1024dd7532450e4e1680`
- semantic consistency: `100%`

## Three complete test runs

Each run used this exact command and exited `0`:

```text
PYTHONPATH=/tmp/carb_m3_v103_deps:. python3 -m pytest backend/tests/test_candidate_passport_v1.py -q
```

Raw logs are `logs/replay-1.log`, `logs/replay-2.log`, and `logs/replay-3.log`; each records `19 passed`. Tests cover truth/expected rejection and tampering, evidence value/unit binding, all five signed-credential negative cases, incomplete/conflicting/ambiguous inputs, period anomalies, prompt injection, rejection audit, deterministic calculation, batch isolation and replay identity.

## Failure samples and limitations

`failure-samples.json` retains unresolved and document-instruction failures from the six-scenario batch. All outputs remain `formal_write_allowed=false` and `publish_allowed=false`.

- `PASS_WITH_LIMITATIONS`: this synthetic candidate calls a deterministic document parser through the frozen provider interface; it does not qualify an external model.
- `PASS_WITH_LIMITATIONS`: signed confirmation credential verification is implemented, but no production API/database signing endpoint is added in M3. Production wiring must issue the short-lived credential only after real authentication and authorization.
- `NOT_RUN_ENV`: Docker/Compose/live database migrations are outside this pure local candidate module and unavailable in the task environment.
- Existing repository-wide dependency findings remain external to this four-file code fix and are not waived.
- No real data, credential, external LLM, production permission, remote write, publication, fee or competition submission was used.

## Exact rollback

The unified patch uses standard `b/` destination prefixes and applies with default `git apply M3_MINIMUM_CLOSED_LOOP_V1.0.3.patch`. In the task-isolated application copy, reverse it with `git apply -R M3_MINIMUM_CLOSED_LOOP_V1.0.3.patch` or delete only these baseline additions:

```text
backend/services/candidate_passport_v1.py
backend/tests/test_candidate_passport_v1.py
ai/memory-bank/05-product/confirmation-workflow.md
validation/m3_candidate_passport_v1/
```

Do not change the fixed baseline, frozen M1/M2 evidence, V1.0.0/V1.0.1 attachments or any remote object.
