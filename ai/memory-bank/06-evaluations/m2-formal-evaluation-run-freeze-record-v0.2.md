# M2 正式评测实际运行冻结记录 v0.2

## 结论

本记录与 `M2_VALUES_CANDIDATE_V2` 统一：8 项不再标为“待人类逐项填写/审批”，而是 1—5、7—8 为 `CANDIDATE / PENDING_INDEPENDENT_QA`，第 6 项为 `WAITING_REQUIRED_EVIDENCE`。整体仍为 `PREPARATION_ONLY / NOT_READY_NOT_RUN`，不得启动 M2-FORMAL。

## 8 项运行状态

| # | 项目 | 状态 | 运行登记 |
|---:|---|---|---|
| 1 | provider/model/随机性 | CANDIDATE | static/static-v1/in-process；temperature 0、seed 20260814、并发1、重试0、无网络/凭据 |
| 2 | prompt hash | CANDIDATE | `M2-PROMPT-BUNDLE-V2` 五文件及逐文件哈希，以 snapshot manifest 为准 |
| 3 | M2 阈值 | CANDIDATE | RELEASE_GATES 1.0.0 + margin 0.00 + replay 1.00 |
| 4 | 结果目录 | CANDIDATE | `/tmp/carbonlab-m2-values-v2/`，0700/0600，分区固定，24h 删除 |
| 5 | 执行/可见人员 | CANDIDATE | 协调员执行、QA 只读复核、Owner 审批可见，最长24h |
| 6 | Truth 等价控制 | WAITING_REQUIRED_EVIDENCE | 等待 CARB-18 实施包及独立安全审计；不得登记 opaque reference；缺失退出14 |
| 7 | 重放计划 | CANDIDATE | 合成静态 harness 三次；pytest 三入口；无环境只记 NOT_RUN_ENV |
| 8 | 一致性/失败规则 | CANDIDATE | 严格一致、缺失不插补、硬失败不可平均抵消 |

完整值、负责人、验收、回滚及阻断影响以同附件集 `m2-values-candidate-v2.md` 为准；全部直接依赖以 `m2-values-snapshot-manifest-v2.sha256` 为准。独立 QA ACCEPT 和第 6 项实施/审计均完成前，不得冻结 VALUES。
