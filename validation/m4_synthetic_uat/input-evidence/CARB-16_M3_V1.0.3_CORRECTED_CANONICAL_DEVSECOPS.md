# CARB-16 M3 V1.0.3 corrected canonical DevSecOps verification

- Verification time (UTC): `2026-08-14T14:33:30Z`
- Repository: `https://github.com/Ghostsci/carbonlab-opc`
- Detached baseline: `c4f0b5bab63572dd0b9722be7aa12293fc3fb2b8`
- Baseline tree: `29276451fd21482cffdab828c655bfbb5c428221`
- Attachment: `M3_MINIMUM_CLOSED_LOOP_V1.0.3_CORRECTED_CANONICAL.tar.gz`
- Attachment SHA-256: `60abf4fd50a1b1922f31958c4a50ec56330da5b251b1a761973295cd5b178d63`

## Environment capability matrix

- OS: Linux x86_64, kernel `6.8.0-76060800daily20240311-generic`; CPU: 32 logical cores.
- Python `3.10.12`, pip `22.0.2`; Node `v22.23.1`, npm `10.9.8`; Git `2.34.1`.
- Docker CLI `24.0.7`; daemon unavailable (`NOT_RUN_ENV`). `psql` and `sqlite3` CLI unavailable.
- `python3-venv`/ensurepip unavailable. Tests used an isolated `/tmp/.../deps` target directory; `pip check` reported no broken requirements.

## Executed verification and results

- `sha256sum <archive>`: exit 0; archive digest matched the submitted value.
- Python `tarfile` member audit: 14/14 member names safe (no absolute path or `..`).
- `(cd extracted/carbonlab-opc && sha256sum -c validation/m3_candidate_passport_v1/SHA256SUMS)`: exit 0; 10/10 files OK.
- Clean clone detached at the fixed commit: HEAD and tree matched the manifest; initial status clean.
- `git apply --check .../M3_MINIMUM_CLOSED_LOOP_V1.0.3.patch`: exit 0.
- `git apply .../M3_MINIMUM_CLOSED_LOOP_V1.0.3.patch`: exit 0; only the four declared baseline additions appeared.
- `cmp` of the four patch-created files against the archive copies: all exit 0. Their SHA-256 values matched `SHA256SUMS`.
- `PYTHONPATH=<isolated-deps>:. python3 -m pytest backend/tests/test_candidate_passport_v1.py -q`, repeated three times: exit 0 each; `19 passed` each.
- Five explicit signed-credential negative tests in one pytest invocation: exit 0; `5 passed`.
- Fresh six-scenario generation and `run_batch` repeated three times: generated result objects equal the archived `results` 3/3. Independently canonicalized run hashes were `ca94fd62e6e4d3bee3442280d65ff49174117451f4ce1024dd7532450e4e1680` 3/3 and matched all declarations.
- Independently canonicalized input hash was `b9b1457a975a597e76516c62b770292a62ed92c2f3dcdd7358d0775b4268a0fe`; archived `scenario-results.json` SHA-256 was `ae10f1026f3b02e9b681175994e4cf9db97617949755cba8a629c430fcf83ba7`.
- Archived and freshly generated successful confirmation both use `authentication=signed_confirmation_credential`.

## Classification

- `PASS`: attachment signature/hash, archive path safety, internal checksums, fixed-baseline clean application, byte-for-byte patch payload, three test replays, five authentication negatives, canonical input/output consistency.
- `NOT_RUN_ENV`: Docker runtime verification, live database/migration verification, and a conventional venv. These are outside the corrected canonical-only change and were not represented as PASS.
- Dependency integrity: isolated runtime/test subset passed `pip check`; no new vulnerability waiver is claimed and repository-wide dependency risks were not re-audited because the attachment changes no dependency declaration or business code from the already verified V1.0.3 payload.
- Business code change required: no.
- Human/independent participation required: yes; a different employee must perform independent QA.
- Suggested stage conclusion: `PASS_WITH_LIMITATIONS` for this DevSecOps gate. M3 is not self-approved; M4-M6 remain blocked pending independent QA and Owner gate.

## Replay / rollback

Replay from a fresh clone at the fixed commit, verify archive SHA-256 and `SHA256SUMS`, apply the standard patch with `git apply`, then run the listed pytest command three times plus the five named negative tests. Reverse only in the disposable clone with `git apply -R M3_MINIMUM_CLOSED_LOOP_V1.0.3.patch`, or delete the disposable clone.
