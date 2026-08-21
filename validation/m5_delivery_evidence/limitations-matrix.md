# Limitations matrix

| Item | Classification | Treatment |
|---|---|---|
| candidate.2 new baseline, 29 members, owner freeze | PASS | Exact version/hash/boundary locked |
| Legacy M0—M2 and policy evidence | PASS_WITH_LIMITATIONS | Retained as LEGACY_EVIDENCE_UNRECOVERABLE / NOT_SUPPLIED_TO_M5; not continued |
| Git administrative metadata | NOT_RUN_ENV | Fixed repository URL and requested SHA recorded |
| Docker Compose, psql, sqlite3 | NOT_RUN_ENV | Not required by this stdlib-only replay |
| Real data, external LLM, production/remote writes, submission | NOT_RUN_ENV | Prohibited |
| M4 archive and 69 member hashes | PASS | Verified before build |
| Eight executable rejection cases | PASS | Any assertion failure exits nonzero |
