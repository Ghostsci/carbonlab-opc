# Limitations matrix

| Item | Classification | Treatment |
|---|---|---|
| M5 v1.0.3 archive and 34 member hashes | PASS | Recomputed from actual archive bytes before authorization |
| M0—M2 and policy legacy objects | PASS_WITH_LIMITATIONS | Legacy-unrecoverable history retained; candidate.2 is a new baseline |
| v1.0.0 ten gate claims | FAIL_CODE | Superseded; independent malicious-payload bypass preserved in evidence |
| v1.0.1 adversarial cases | PASS | 32/32 rejected at guard or packaged execution boundary, exit 42, no marker side effect |
| Actual payload scan | PASS | Strict UTF-8/JSON, duplicate and unknown key rejection, recursive decoded content scan, immutable payload hash allowlist |
| Evidence-use binding | PASS_WITH_LIMITATIONS | Complete subject/object/version/hash/action/target/validity checked; offline package binding is not formal-action authorization |
| Packaged execution boundary | PASS | One read-only local action; no shell, arbitrary subprocess, network, remote, production, release, or submission dispatcher |
| Ambient OS commands outside boundary | NOT_RUN_ENV | Package does not claim system-wide sandbox enforcement |
| Real users and real-enterprise data | NOT_RUN_ENV | Not approved and prohibited in M6 |
| Formal submission/publication/production/remote writes | NOT_RUN_ENV | HUMAN_REQUIRED and absent from dispatcher |
