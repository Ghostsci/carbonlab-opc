# M2_FORMAL_REFROZEN_PATCH_AND_PYTEST_V4

## Candidate conclusion

`PASS_WITH_LIMITATIONS` candidate for independent QA. V4 satisfies the requested dependency and provider re-freeze, three CPython 3.12 replays, and audit-chain recomputation. It does not itself approve M2-FORMAL or unblock M3.

## Fixed inputs and change boundary

- Repository: `https://github.com/Ghostsci/carbonlab-opc.git`
- Read-only baseline: `main@c4f0b5bab63572dd0b9722be7aa12293fc3fb2b8`
- V2 dependency source attachment: `01a00021-477e-77d2-82f3-70138e22601f`, SHA-256 `6187e6be22f66c68f4721a94cff5823e81b55a85b92ac7fb61cdda15462ed2e9`
- V3 evidence source attachment: `01a0002d-335e-7714-892c-21091b67fb5c`, SHA-256 `d6fd16fa8b519646deaf3c7927c194072061d81dc71d6a101d9788d7cf050aa1`
- Only code change: the accepted `providers.py` import-order patch, recorded in `provider-import-order-v4.patch` and `logs/provider-scope.diff`.
- Dependency re-freeze: `pytest==9.0.3`; its required `pygments` dependency is frozen at `2.20.0` because the initially resolved 2.19.2 has PYSEC-2026-2987.
- Provider remains `static/static-v1/in-process`; temperature 0; seed 20260814; concurrency 1; retries 0.
- No Truth正文 was read. Only the previously approved sanitized audit-chain files were consumed.

## Environment capability matrix

- Linux x86_64, kernel 6.8: `PASS`
- Task-local CPython 3.12.11: `PASS`
- Offline virtual environment and wheel installation: `PASS`
- Node 22.23.1 / npm 10.9.8: detected, not required for this closure
- Docker client 24.0.7: daemon unavailable, `NOT_RUN_ENV`; container execution was not required for the accepted replay path
- CPU enumeration via `lscpu`: platform sysfs unavailable, `NOT_RUN_ENV`; architecture was independently identified as x86_64
- PostgreSQL and SQLite CLIs: unavailable, `NOT_RUN_ENV`; no database migration was in V4 scope
- `/tmp`: 16 GiB available at probe time

## Commands and exits

1. `UV_CACHE_DIR=<task>/uv-cache UV_PYTHON_INSTALL_DIR=<task>/python uv python install 3.12` — exit 0; CPython 3.12.11 installed task-locally.
2. `python3.12 -m venv .venv` — exit 0.
3. `.venv/bin/python -m pip install --no-index --find-links wheelhouse-py312 -r requirements-py312.lock` — exit 0.
4. `sha256sum -c wheelhouse-py312.sha256` — exit 0, 17/17 wheels verified.
5. `pip-audit -r requirements-py312.lock --disable-pip --no-deps` — exit 0, `No known vulnerabilities found`; PYSEC-2026-1845 is absent and no new finding remains.
6. Frozen replay command, executed three times: `PYTHONPATH=. .venv/bin/python -m pytest backend/tests/test_llm_conformance.py backend/tests/test_llm_validation_contracts.py backend/tests/test_llm_validation_reporting.py -vv` — exits 0/0/0.
7. Audit-chain canonical recomputation using UTF-8 JSON, sorted keys, no whitespace, and zero genesis — exit 0.

## Replay results

- Replay 1: 24/24 passed, raw log SHA-256 `990f9eef854bb22de0a96c68b186901cca84a3fae5fe0944dac4c9675ba78938`.
- Replay 2: 24/24 passed, raw log SHA-256 `aa435a5101ce7f13d69ee770e458fd7daa5dd34e1301689f1da0013c0231da32`.
- Replay 3: 24/24 passed, raw log SHA-256 `aa435a5101ce7f13d69ee770e458fd7daa5dd34e1301689f1da0013c0231da32`.
- Each raw log contains all 24 node IDs and individual `PASSED` outcomes. Semantic result consistency is 72/72, 100%. Replay 1 differs bytewise only in elapsed-time text (0.14s versus 0.15s); no case result differs.
- Extracted per-case result logs are byte-identical, SHA-256 `ae525060dd9c0a40d4e13e6e9daded4526a98740729756d489c15964737f1552` for all three runs.

## Audit chain

- Sanitized chain SHA-256: `19daeafeedb2305d68d6dadbe355deda906152d288222e0203afc28d5cbbf32a`.
- Approved head record SHA-256: `4866874d23385a691fa876e0a162d5f575d4bece4eb0e46afcf2f7e27957bed5`.
- Recomputed 11/11 linked events from zero genesis to approved head `891a3006f3ae29be03dcdd6452858766ce4d9b896378a8606fd1c8331d239c36`, exit 0.

## Classification

- `PASS`: accepted provider patch scope; pytest 9.0.3 re-freeze; complete offline wheel set and hashes; dependency audit; three CPython 3.12 replays; per-case results; 100% semantic consistency; 11-event audit chain.
- `FAIL_CODE`: none.
- `FAIL_DEPENDENCY`: none after Pygments 2.20.0 re-freeze.
- `NOT_RUN_ENV`: Docker daemon, CPU sysfs enumeration, database CLIs; none blocks the V4 replay.
- `BLOCKED_EXTERNAL`: none.
- Overall candidate: `PASS_WITH_LIMITATIONS`, because the portable source archive uses a task-local, no-remote Git fixture for reporting tests and final acceptance remains with independent QA.

## Rollback and boundary

Delete the task-specific `/tmp/m2-v4-work` directory. No formal or remote baseline was modified, no remote Git write occurred, and no external LLM, real data, credentials, fee-bearing service, or publication was used.
