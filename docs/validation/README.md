# 验证材料入口

可执行验证材料保留在仓库根目录 `validation/`：

- `PRODUCT_VALIDATION_PROTOCOL.md`：产品验证协议；
- `datasets/synthetic_factory_v1/`：Candidate、Holdout、Adversarial 数据集；
- `product_acceptance_v1/`：可用性和产品验收样例；
- `llm/LLM_OPERATING_CONTRACT.md`：模型操作契约；
- `MODEL_BASELINE_REGISTRY.json`：历史模型登记状态；
- `history/QUALIFICATION_LOCK_SOURCE_20260711.json`：旧仓库历史锁，仅供审计。

当前不存在 `validation/QUALIFICATION_LOCK.json`。这表示新仓库尚未完成方法、数据和模型的重新冻结；任何模型都不得被描述为已获生产准入。
