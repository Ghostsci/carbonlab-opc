# M2 实际运行值审批包 v0.2

## 审批结论

依据 `DEC-20260814-02`，审批对象不是“是否由人类填写具体值”，而是对协调员已提出的 `M2_VALUES_CANDIDATE_V2` 做独立 QA。1—5、7—8 状态统一为 `CANDIDATE / PENDING_INDEPENDENT_QA`；第 6 项为 `WAITING_REQUIRED_EVIDENCE`。当前 `PREPARATION_ONLY / NOT_READY_NOT_RUN`。

| # | 审批对象 | 当前值摘要 | 当前缺口 | 通过标准 |
|---:|---|---|---|---|
| 1 | 模型与随机性 | static/static-v1/in-process，确定性、无网络/凭据 | QA 未 ACCEPT | 配置和代码哈希一致、重复输出一致 |
| 2 | prompt | M2-PROMPT-BUNDLE-V2 | QA 未 ACCEPT | 五文件清单/哈希及双编译一致 |
| 3 | 阈值 | RELEASE_GATES 1.0.0、margin 0、replay 1 | QA 未 ACCEPT | 阈值完整且边界测试正确 |
| 4 | 结果目录 | `/tmp/carbonlab-m2-values-v2/` | QA 未 ACCEPT | 0700/0600、无越界、可精确删除 |
| 5 | 人员 | 协调员/QA/Owner 最小角色，24h | QA 未 ACCEPT | 名单、用途、期限、撤销完整 |
| 6 | Truth 控制 | 不登记引用，等待 CARB-18 | 实施包及独立安全审计未完成 | 两者完成且不含 truth 正文 |
| 7 | 重放 | 静态合成三次、冻结测试入口 | QA 未 ACCEPT；pytest 可为 NOT_RUN_ENV | 可用环境三次一致，或如实记录环境限制 |
| 8 | 一致性 | 严格一致、缺失不插补、硬失败 | QA 未 ACCEPT | 合成正反例逐项命中 |

审批请求：仅请模型评测与质量保证工程师对本次固定附件集进行一次独立 QA。QA 不替代第 6 项安全审计；Owner 不需要逐项补写候选值。所有项目在 QA ACCEPT 且第 6 项闭环前仍阻断 `M2_VALUES_FROZEN` 和 M2-FORMAL。
