# M2_VALUES_CANDIDATE_V2｜8 项运行值候选冻结记录

## 结论

依据 `DEC-20260814-02`，8/8 项均已提出具体候选值，不等待人类逐项填写。当前统一状态为 `CANDIDATE / PENDING_INDEPENDENT_QA`；第 6 项另受 Truth 实施包和独立安全审计阻断。整体保持 `PREPARATION_ONLY / NOT_READY_NOT_RUN`，不得启动 M2-FORMAL。

本版本替代候选件 v1 的送审口径，但不覆盖或撤销评论 `46cebf17-4354-4fa4-80a1-eaba720e9694` 的旧附件。适用范围仅为仓库合成数据、静态 provider 和 `/tmp`；禁止外部 LLM、网络、凭据、truth 正文读取/复制/披露、正式数据变更和正式结果发布。

## 8 项状态

| # | 候选冻结值 | 状态 | 证据/版本 | 负责人、复核与可测试验收 | 回滚 | 阻断 |
|---:|---|---|---|---|---|---|
| 1 | `static/static-v1/in-process://backend.validation.providers.StaticProvider`；temperature=0、top_p=1、seed=20260814、并发1、重试0、无重采样/tools/stream、timeout=5s、网络 DENY、凭据 NONE | CANDIDATE | `backend/validation/providers.py`；`M2-STATIC-V1`；哈希见 snapshot manifest | 协调员提出，QA 复核；静态检查无 URL/密钥并验证重复调用字节一致 | 删除临时目录，配置恢复 UNSET | 是，待 QA |
| 2 | contract、task catalog、schema、`contracts.py`、`prompting.py` 组成 `M2-PROMPT-BUNDLE-V2`；场景/集合 prompt hash 必须复算一致 | CANDIDATE | 五文件均纳入同一附件集；哈希见 manifest | 协调员提出，QA 复核；逐文件哈希一致且同一合成场景编译两次相同 | 删除临时 prompt manifest，bundle 恢复 UNSET | 是，待 QA |
| 3 | RELEASE_GATES 1.0.0：硬门全部满足；case_pass_rate>=0.80、field_accuracy>=0.95、numeric/evidence/injection=1.00；非劣效 margin=0.00；重放一致率=1.00 | CANDIDATE | `validation/RELEASE_GATES.json` + 本记录；哈希见 manifest | 协调员提出，QA 复核；解析完整并以边界样例触发 pass/fail | 恢复为历史参考，不沿用虚拟结果 | 是，待 QA |
| 4 | `/tmp/carbonlab-m2-values-v2/`，根 0700、文件 0600；candidate/raw、parsed、scores、failures、replay、logs、reports、manifests 分区；24h 删除 | CANDIDATE | `M2-TMP-LAYOUT-V2` / 本记录 | 协调员执行，QA 复核；路径越界退出13 | 仅删除该精确临时目录 | 是，待 QA |
| 5 | 执行者仅 M2冻结审批协调员；QA 仅独立只读复核；Owner 仅审批可见；最长24h；执行者和开发侧不得接触 truth | CANDIDATE | `M2-ACCESS-V2` / 本记录 / 动作评论 | 协调员维护，QA 复核；目录无 group/other 权限，名单和期限完整 | 撤权并删除临时目录 | 是，待 QA |
| 6 | 等待 CARB-18（UUID `f71e163d-d782-4267-9918-08452129992f`）交付 `M2_TRUTH_EQUIVALENT_CONTROL_V1` 及独立安全审计；当前不得登记 opaque reference；缺失退出14 | WAITING_REQUIRED_EVIDENCE（禁止提前冻结） | 派工 `a9a52417-77ad-47af-a53e-f0b12515df13`、边界 `434629a9-5904-4e53-9795-d197ac19d2f0`；旧设计复核不算实施 | 数据主责交付，安全职责独立审计；验收为实施附件/哈希/命令/退出码齐全且审计 ACCEPT，无 truth 内容 | 删除白名单引用、撤权；保留不含 truth 的审计 ID | 是，等待实施与审计 |
| 7 | 静态合成 harness 重放3次、manifest 顺序、间隔0、并发1、重试0、5s/case；冻结 pytest 三入口；退出码 0/10/12/13/14/15 | CANDIDATE / NOT_RUN_ENV 可接受环境限制 | 三个测试入口、provider/evaluator/reporting 均在附件集；哈希见 manifest | 协调员提出，QA 复核；具备环境时三次为0且摘要一致；无 pytest 只能记 NOT_RUN_ENV | 删除 replay，状态恢复 NOT_RUN | 是，待 QA；第6项未齐退出14 |
| 8 | 类型严格相等；数值定点；证据 document_id+quote 严格一致；缺失不插补；未知字段/schema/证据错配/写入放行/泄密/provider/超时/解析/重放差异均硬失败 | CANDIDATE | `M2-CONSISTENCY-V2`；contracts/evaluator/reporting/证据规则均入附件集 | 协调员提出，QA 与安全职责按边界复核；pass、缺失、异常、错配、超时、replay mismatch 合成用例逐项命中 | 恢复未冻结并删除临时比较产物 | 是，待 QA |

## 统一验收和命令

送审范围以 `m2-values-snapshot-manifest-v2.sha256` 为完整清单。原始校验命令为 `sha256sum -c m2-values-snapshot-manifest-v2.sha256`，期望退出码 `0`。重放入口为 `python -m pytest backend/tests/test_llm_conformance.py backend/tests/test_llm_validation_contracts.py backend/tests/test_llm_validation_reporting.py -q`；本地缺少 pytest 时仅记 `NOT_RUN_ENV / ACCEPTED_PLATFORM_LIMITATION`，不是 PASS。

独立 QA 必须按本附件集逐项返回 ACCEPT/RETURN；第 6 项实施和安全审计未齐时，即使其余项通过也不得登记 `M2_VALUES_FROZEN`。
