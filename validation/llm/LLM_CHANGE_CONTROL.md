# LLM Provider 与模型变更控制 V1

> 2026-07-11 审计更正：下方冻结资格结果由存在字段证据错配漏洞的旧评分器生成，现已全部失效。当前模型注册表状态为 `requalification_required_after_evaluator_hardening`，不得继续按“已资格”使用。

每次 Provider、模型名、模型版本、系统契约、任务 Prompt、输出 Schema 或重要参数变化都视为一个新候选版本。

候选版本必须记录：

- Provider 与模型；
- API base；
- 操作契约 SHA-256；
- 任务规范 SHA-256；
- Schema SHA-256；
- 数据集 manifest SHA-256；
- temperature、max tokens 和超时；
- 运行报告与失败案例；
- 基线版本和回滚 Git commit。

禁止仅凭人工抽看几条回答切换默认模型。模型通过资格测试后仍需影子运行；任何硬门禁退化立即回退。

## 2026-07-11 DeepSeek V4 Flash candidate 调优记录

1. 预实时版本 Git：`13d8a65`，标签 `zcy-llm-validation-pre-live-20260711`；
2. candidate v1：14/15 场景通过。一个冲突场景虽提供两条正确证据和顶层冲突说明，但省略字段自身 `uncertainty_reason`，严格校验失败；
3. 修复：输出 Schema 升至 1.1.0，把每个候选字段的六个键以及顶层冲突/缺失数组改为必填；Prompt 明确顶层冲突说明不能替代字段原因；
4. candidate v2：15/15 场景、135/135 字段通过，硬违规为 0；
5. 此后冻结契约、任务、Schema、数据集与 Prompt 编译逻辑。holdout/adversarial 结果不得用于静默修改本冻结版本。

以上仅是合成 candidate 调优记录，不是生产模型批准。正式资格结论以冻结 Git 上的 holdout + adversarial 报告为准。

## 历史冻结资格结果（已失效）

- 冻结标签：`zcy-llm-contract-v1.1-frozen-20260711`；
- V4 Flash 首次 holdout+adversarial：24/24；
- V4 Flash 同配置重复：24/24，预登记 2% 成对非劣效差异为 0；
- V4 Pro 在不修改契约的 candidate smoke 为 15/15，holdout+adversarial 为 24/24；相对 Flash 的预登记 2% 成对非劣效差异为 0；
- 当前选择：无人工影子默认候选、无替代候选、无生产批准模型；Flash/Pro 旧报告只保留为审计历史。

## 评分器加固后的重新资格要求

1. 真实引文必须与当前字段的冻结证据绑定，不能用同一文档包中的无关真引文代替；
2. 冲突字段必须覆盖全部冻结证据，字段证据与顶层冲突摘要必须一致；
3. 旧 holdout/adversarial 已用于诊断，不得继续作为新 Prompt 的盲测集；
4. 新资格运行前先冻结新的未见场景、评分语义、Prompt 与回滚标签；
5. Provider URL 与所有 JSON/Markdown 报告必须通过 token、access token、Authorization、Bearer 等凭据泄漏门禁。
6. 每份新报告必须携带与资格锁一致的 evaluation policy SHA-256；旧 `legacy-unpinned` 报告不得参与成对提升比较。

加固评分器冻结标签：`zcy-llm-evaluator-v1.3-frozen-20260711`，对应提交 `8244225`。资格锁 V1.3 在任何 Provider API 调用前解析标签、核对提交、重算冻结评分器字节，并拒绝冻结路径的工作树漂移。

详细报告见 `validation/reports/`、`validation/comparisons/` 与 `validation/MODEL_BASELINE_REGISTRY.json`。
