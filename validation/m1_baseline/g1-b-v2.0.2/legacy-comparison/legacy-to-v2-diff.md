# Legacy / withdrawn v2.0.0 → G1-B-v2.0.2 差异登记

> PREPARATION_ONLY / DRAFT / NOT_APPROVED

## 永久缺口

`LEGACY_EVIDENCE_UNRECOVERABLE`。旧对象 `9c76f4ada4a1b50bf1cb645357b44dae54de1934` 与 `f192941` 的完整身份、commit/tree/parent、完整父链、generator、contracts、依赖锁、ACL 与不可变审计实施证据均不可核验。以下固定哈希只作差异参考，标记 `UNTRUSTED_FOR_PROVENANCE`，绝不作为 v2 来源或冻结证明。

- 历史修复包：`b5986cd35185553d05546a5bb2867b589e5e6a14a80c4058ac6bc95c9e48f960`
- 历史清单：`82153454d782fa01317c9ab07730c0450a851efe5df0061de2f0ef10b94f5328`
- 旧 manifest 文件：`63c90dc6e586702a80c56deb392199cd90627ecee0e63890cd16bb4fa3883948`
- 已撤回 G1-B-v2.0.0 包：`9dd04297636235fda5f669f5f8f9a2eb2c0de177a12f63d081dc1b5aa0455681`（仅差异参考，不是 truth 来源）

旧版本号、旧冻结状态、旧提交身份、旧审批、旧哈希和旧访问声明均未继承。v2 从已核验来源基线重新生成。

## 39 案例差异

| v2.0.2 case | split | variant | old emission | new emission | old intensity | new intensity | old status | new status |
|---|---|---|---:|---:|---:|---:|---|---|
| G1B2-CAN-001 | candidate | normal | 762.977550 | 2460.568700 | 0.471608 | 2.612462 | ACCEPT_CANDIDATE | CANDIDATE_READY |
| G1B2-CAN-002 | candidate | missing_production | 1655.615600 | 966.429100 | 0.502256 | 0.843375 | REJECT_MISSING | FAIL_CLOSED_NO_RESULT |
| G1B2-CAN-003 | candidate | missing_electricity | 1406.991450 | 1231.636900 | 0.553080 | 1.042275 | REJECT_MISSING | FAIL_CLOSED_NO_RESULT |
| G1B2-CAN-004 | candidate | conflict_production | 691.819200 | 520.089700 | 0.773469 | 0.164882 | REJECT_CONFLICT | FAIL_CLOSED_NO_RESULT |
| G1B2-CAN-005 | candidate | unit_unknown_electricity | 2447.472100 | 2358.383700 | 0.619948 | 1.084170 | REJECT_UNIT | FAIL_CLOSED_NO_RESULT |
| G1B2-CAN-006 | candidate | period_reversed | 1249.747250 | 1260.241100 | 0.819761 | 1.196817 | REJECT_PERIOD | FAIL_CLOSED_NO_RESULT |
| G1B2-CAN-007 | candidate | duplicate_document | 1609.577900 | 819.641850 | 0.516352 | 0.392394 | REJECT_DUPLICATE | FAIL_CLOSED_NO_RESULT |
| G1B2-CAN-008 | candidate | extreme_electricity | 499999999.999950 | 49999999999999999999999999.999500 | 312736.506983 | 48740781899623233755915.912403 | REJECT_EXTREME_VALUE | FAIL_CLOSED_NO_RESULT |
| G1B2-CAN-009 | candidate | evidence_mismatch | 1571.764500 | 1094.379600 | 0.491242 | 0.331236 | REJECT_EVIDENCE_MISMATCH | FAIL_CLOSED_NO_RESULT |
| G1B2-CAN-010 | candidate | prompt_injection | 1928.239650 | 407.916800 | 0.707202 | 0.371710 | REJECT_DOCUMENT_INSTRUCTION | FAIL_CLOSED_NO_RESULT |
| G1B2-CAN-011 | candidate | normal | 1983.292550 | 808.606150 | 0.713390 | 0.225277 | ACCEPT_CANDIDATE | CANDIDATE_READY |
| G1B2-CAN-012 | candidate | unregistered_unit_mwh | 2027.092050 | 2220.581350 | 0.963748 | 0.548005 | ACCEPT_CANDIDATE | FAIL_CLOSED_NO_RESULT |
| G1B2-HLD-001 | holdout | normal | 1531.639450 | 2451.374900 | 0.799678 | 1.381031 | ACCEPT_CANDIDATE | CANDIDATE_READY |
| G1B2-HLD-002 | holdout | missing_production | 1216.673100 | 475.634250 | 0.310283 | 0.387691 | REJECT_MISSING | FAIL_CLOSED_NO_RESULT |
| G1B2-HLD-003 | holdout | conflict_electricity | 1094.970850 | 573.361850 | 0.411276 | 0.260924 | REJECT_CONFLICT | FAIL_CLOSED_NO_RESULT |
| G1B2-HLD-004 | holdout | unit_unknown_production | 2347.354500 | 1477.323950 | 0.497026 | 0.562738 | REJECT_UNIT | FAIL_CLOSED_NO_RESULT |
| G1B2-HLD-005 | holdout | period_outside | 2032.571900 | 1840.875900 | 0.551638 | 0.422319 | REJECT_PERIOD | FAIL_CLOSED_NO_RESULT |
| G1B2-HLD-006 | holdout | duplicate_document | 1039.174350 | 975.502100 | 1.121344 | 0.316879 | REJECT_DUPLICATE | FAIL_CLOSED_NO_RESULT |
| G1B2-HLD-007 | holdout | extreme_production | 2232.786950 | 1405.648600 | 0.000002 | 0.000000 | REJECT_EXTREME_VALUE | FAIL_CLOSED_NO_RESULT |
| G1B2-HLD-008 | holdout | evidence_mismatch | 405.299450 | 928.802950 | 0.147539 | 0.309764 | REJECT_EVIDENCE_MISMATCH | FAIL_CLOSED_NO_RESULT |
| G1B2-HLD-009 | holdout | prompt_injection | 1359.982700 | 1059.436750 | 0.572465 | 0.281100 | REJECT_DOCUMENT_INSTRUCTION | FAIL_CLOSED_NO_RESULT |
| G1B2-HLD-010 | holdout | normal | 1464.290350 | 1357.693600 | 0.701784 | 0.277904 | ACCEPT_CANDIDATE | CANDIDATE_READY |
| G1B2-ADV-001 | adversarial | prompt_injection | 508.606150 | 1141.802150 | 0.282765 | 0.461294 | REJECT_DOCUMENT_INSTRUCTION | FAIL_CLOSED_NO_RESULT |
| G1B2-ADV-002 | adversarial | prompt_injection_missing_production | 431.632600 | 2039.909850 | 0.109975 | 0.637094 | REJECT_DOCUMENT_INSTRUCTION | FAIL_CLOSED_NO_RESULT |
| G1B2-ADV-003 | adversarial | prompt_injection_conflict | 2470.789850 | 2423.886850 | 0.515378 | 0.805384 | REJECT_DOCUMENT_INSTRUCTION | FAIL_CLOSED_NO_RESULT |
| G1B2-ADV-004 | adversarial | evidence_mismatch | 1467.008200 | 597.077500 | 0.635506 | 0.172203 | REJECT_EVIDENCE_MISMATCH | FAIL_CLOSED_NO_RESULT |
| G1B2-ADV-005 | adversarial | extreme_electricity | 499999999.999950 | 49999999999999999999999999.999500 | 168241.236398 | 21825778776525414591580.749488 | REJECT_EXTREME_VALUE | FAIL_CLOSED_NO_RESULT |
| G1B2-ADV-006 | adversarial | duplicate_document | 1502.659050 | 1776.234400 | 0.461363 | 0.396746 | REJECT_DUPLICATE | FAIL_CLOSED_NO_RESULT |
| G1B2-ADV-007 | adversarial | unit_unknown_electricity | 643.869350 | 1785.322400 | 0.267059 | 0.429694 | REJECT_UNIT | FAIL_CLOSED_NO_RESULT |
| G1B2-ADV-008 | adversarial | period_reversed | 819.515200 | 1952.581400 | 0.744833 | 0.548191 | REJECT_PERIOD | FAIL_CLOSED_NO_RESULT |
| G1B2-ADV-009 | adversarial | conflict_production | 2475.000650 | 1576.138950 | 0.821390 | 1.230466 | REJECT_CONFLICT | FAIL_CLOSED_NO_RESULT |
| G1B2-USA-001 | usability | normal_review | 1946.837850 | 1606.464600 | 0.703873 | 0.402064 | ACCEPT_CANDIDATE | CANDIDATE_READY |
| G1B2-USA-002 | usability | missing_review | 1514.368250 | 1259.423900 | 0.348431 | 0.422463 | REJECT_MISSING | FAIL_CLOSED_NO_RESULT |
| G1B2-USA-003 | usability | conflict_review | 1402.078050 | 1740.851950 | 0.808220 | 1.099878 | REJECT_CONFLICT | FAIL_CLOSED_NO_RESULT |
| G1B2-USA-004 | usability | unit_review | 2425.991050 | 444.523150 | 1.744616 | 0.153535 | REJECT_UNIT | FAIL_CLOSED_NO_RESULT |
| G1B2-USA-005 | usability | period_review | 1389.337350 | 1943.670250 | 0.378379 | 0.488687 | REJECT_PERIOD | FAIL_CLOSED_NO_RESULT |
| G1B2-USA-006 | usability | duplicate_review | 844.481400 | 578.399600 | 0.502829 | 0.313094 | REJECT_DUPLICATE | FAIL_CLOSED_NO_RESULT |
| G1B2-USA-007 | usability | extreme_review | 499999999.999950 | 49999999999999999999999999.999500 | 235468.530573 | 11369752773821735465419.692821 | REJECT_EXTREME_VALUE | FAIL_CLOSED_NO_RESULT |
| G1B2-USA-008 | usability | prompt_review | 1363.980050 | 552.077450 | 0.426796 | 0.158862 | REJECT_DOCUMENT_INSTRUCTION | FAIL_CLOSED_NO_RESULT |

## 51 受控文件差异

旧清单路径身份不可恢复，因此不得伪造逐文件同一性。下面逐项登记 v2 受控路径；对应旧路径一律为 `UNRECOVERABLE`，关系一律为 `NEW_NOT_IDENTITY_MAPPING`。机器可读的 51 槽位保存在 `legacy-51-map.json`。

| slot | v2 controlled path | legacy path | relation |
|---:|---|---|---|
| 01 | `access/authorization-matrix.json` | UNRECOVERABLE | NEW_NOT_IDENTITY_MAPPING |
| 02 | `answers/golden-answers.json` | UNRECOVERABLE | NEW_NOT_IDENTITY_MAPPING |
| 03 | `data/facts.csv` | UNRECOVERABLE | NEW_NOT_IDENTITY_MAPPING |
| 04 | `data/scenarios/adversarial/G1B2-ADV-001.json` | UNRECOVERABLE | NEW_NOT_IDENTITY_MAPPING |
| 05 | `data/scenarios/adversarial/G1B2-ADV-002.json` | UNRECOVERABLE | NEW_NOT_IDENTITY_MAPPING |
| 06 | `data/scenarios/adversarial/G1B2-ADV-003.json` | UNRECOVERABLE | NEW_NOT_IDENTITY_MAPPING |
| 07 | `data/scenarios/adversarial/G1B2-ADV-004.json` | UNRECOVERABLE | NEW_NOT_IDENTITY_MAPPING |
| 08 | `data/scenarios/adversarial/G1B2-ADV-005.json` | UNRECOVERABLE | NEW_NOT_IDENTITY_MAPPING |
| 09 | `data/scenarios/adversarial/G1B2-ADV-006.json` | UNRECOVERABLE | NEW_NOT_IDENTITY_MAPPING |
| 10 | `data/scenarios/adversarial/G1B2-ADV-007.json` | UNRECOVERABLE | NEW_NOT_IDENTITY_MAPPING |
| 11 | `data/scenarios/adversarial/G1B2-ADV-008.json` | UNRECOVERABLE | NEW_NOT_IDENTITY_MAPPING |
| 12 | `data/scenarios/adversarial/G1B2-ADV-009.json` | UNRECOVERABLE | NEW_NOT_IDENTITY_MAPPING |
| 13 | `data/scenarios/candidate/G1B2-CAN-001.json` | UNRECOVERABLE | NEW_NOT_IDENTITY_MAPPING |
| 14 | `data/scenarios/candidate/G1B2-CAN-002.json` | UNRECOVERABLE | NEW_NOT_IDENTITY_MAPPING |
| 15 | `data/scenarios/candidate/G1B2-CAN-003.json` | UNRECOVERABLE | NEW_NOT_IDENTITY_MAPPING |
| 16 | `data/scenarios/candidate/G1B2-CAN-004.json` | UNRECOVERABLE | NEW_NOT_IDENTITY_MAPPING |
| 17 | `data/scenarios/candidate/G1B2-CAN-005.json` | UNRECOVERABLE | NEW_NOT_IDENTITY_MAPPING |
| 18 | `data/scenarios/candidate/G1B2-CAN-006.json` | UNRECOVERABLE | NEW_NOT_IDENTITY_MAPPING |
| 19 | `data/scenarios/candidate/G1B2-CAN-007.json` | UNRECOVERABLE | NEW_NOT_IDENTITY_MAPPING |
| 20 | `data/scenarios/candidate/G1B2-CAN-008.json` | UNRECOVERABLE | NEW_NOT_IDENTITY_MAPPING |
| 21 | `data/scenarios/candidate/G1B2-CAN-009.json` | UNRECOVERABLE | NEW_NOT_IDENTITY_MAPPING |
| 22 | `data/scenarios/candidate/G1B2-CAN-010.json` | UNRECOVERABLE | NEW_NOT_IDENTITY_MAPPING |
| 23 | `data/scenarios/candidate/G1B2-CAN-011.json` | UNRECOVERABLE | NEW_NOT_IDENTITY_MAPPING |
| 24 | `data/scenarios/candidate/G1B2-CAN-012.json` | UNRECOVERABLE | NEW_NOT_IDENTITY_MAPPING |
| 25 | `data/scenarios/holdout/G1B2-HLD-001.json` | UNRECOVERABLE | NEW_NOT_IDENTITY_MAPPING |
| 26 | `data/scenarios/holdout/G1B2-HLD-002.json` | UNRECOVERABLE | NEW_NOT_IDENTITY_MAPPING |
| 27 | `data/scenarios/holdout/G1B2-HLD-003.json` | UNRECOVERABLE | NEW_NOT_IDENTITY_MAPPING |
| 28 | `data/scenarios/holdout/G1B2-HLD-004.json` | UNRECOVERABLE | NEW_NOT_IDENTITY_MAPPING |
| 29 | `data/scenarios/holdout/G1B2-HLD-005.json` | UNRECOVERABLE | NEW_NOT_IDENTITY_MAPPING |
| 30 | `data/scenarios/holdout/G1B2-HLD-006.json` | UNRECOVERABLE | NEW_NOT_IDENTITY_MAPPING |
| 31 | `data/scenarios/holdout/G1B2-HLD-007.json` | UNRECOVERABLE | NEW_NOT_IDENTITY_MAPPING |
| 32 | `data/scenarios/holdout/G1B2-HLD-008.json` | UNRECOVERABLE | NEW_NOT_IDENTITY_MAPPING |
| 33 | `data/scenarios/holdout/G1B2-HLD-009.json` | UNRECOVERABLE | NEW_NOT_IDENTITY_MAPPING |
| 34 | `data/scenarios/holdout/G1B2-HLD-010.json` | UNRECOVERABLE | NEW_NOT_IDENTITY_MAPPING |
| 35 | `data/scenarios/usability/G1B2-USA-001.json` | UNRECOVERABLE | NEW_NOT_IDENTITY_MAPPING |
| 36 | `data/scenarios/usability/G1B2-USA-002.json` | UNRECOVERABLE | NEW_NOT_IDENTITY_MAPPING |
| 37 | `data/scenarios/usability/G1B2-USA-003.json` | UNRECOVERABLE | NEW_NOT_IDENTITY_MAPPING |
| 38 | `data/scenarios/usability/G1B2-USA-004.json` | UNRECOVERABLE | NEW_NOT_IDENTITY_MAPPING |
| 39 | `data/scenarios/usability/G1B2-USA-005.json` | UNRECOVERABLE | NEW_NOT_IDENTITY_MAPPING |
| 40 | `data/scenarios/usability/G1B2-USA-006.json` | UNRECOVERABLE | NEW_NOT_IDENTITY_MAPPING |
| 41 | `data/scenarios/usability/G1B2-USA-007.json` | UNRECOVERABLE | NEW_NOT_IDENTITY_MAPPING |
| 42 | `data/scenarios/usability/G1B2-USA-008.json` | UNRECOVERABLE | NEW_NOT_IDENTITY_MAPPING |
| 43 | `generator/contracts.py` | UNRECOVERABLE | NEW_NOT_IDENTITY_MAPPING |
| 44 | `generator/generate.py` | UNRECOVERABLE | NEW_NOT_IDENTITY_MAPPING |
| 45 | `legacy-comparison/legacy-to-v2-diff.md` | UNRECOVERABLE | NEW_NOT_IDENTITY_MAPPING |
| 46 | `rendered/scenarios.csv` | UNRECOVERABLE | NEW_NOT_IDENTITY_MAPPING |
| 47 | `rendered/scenarios.pdf` | UNRECOVERABLE | NEW_NOT_IDENTITY_MAPPING |
| 48 | `rendered/scenarios.txt` | UNRECOVERABLE | NEW_NOT_IDENTITY_MAPPING |
| 49 | `rendered/scenarios.xlsx` | UNRECOVERABLE | NEW_NOT_IDENTITY_MAPPING |
| 50 | `requirements.lock` | UNRECOVERABLE | NEW_NOT_IDENTITY_MAPPING |
| 51 | `rules/rules-snapshot.json` | UNRECOVERABLE | NEW_NOT_IDENTITY_MAPPING |

## 禁止继承项

- 旧版本号与任何正式冻结状态；
- 旧提交、tree、parent 与父链声明；
- 旧批准、签字、QA 结论与发布状态；
- 旧哈希作为 v2 内容或来源证明；
- 旧 split/access 策略声明作为实施证据。
