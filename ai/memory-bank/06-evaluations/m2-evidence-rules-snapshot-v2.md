# M2 证据规则快照 v2

状态：`CANDIDATE / PENDING_INDEPENDENT_QA`。本快照不修改既有冻结规则，只把本次可重放依赖中的有效规则固定为附件证据。

- 每个证据引用必须同时包含 `document_id` 与非空 `quote`。
- `document_id` 必须来自当前输入文档集合；`quote` 必须是对应原文的连续子串。
- 候选字段证据集合与汇总证据集合按 `(document_id, quote)` 比较；不支持的证据声明计入 `unsupported_evidence_claims`。
- `unsupported_evidence_claims` 的正式硬门为 `0`；证据缺失、错配或伪造不得由平均指标抵消。
- prompt 要求 quote 逐字复制，禁止模型生成或改写引文。
- 实现载体：`backend/validation/contracts.py`、`backend/validation/prompting.py`、`backend/validation/evaluator.py`、`validation/RELEASE_GATES.json`，逐文件 SHA-256 以同送审 manifest 为准。

验收：用合成文档分别构造有效连续引文、未知 document_id、非连续/不存在引文；仅第一项通过，后两项必须形成硬失败。禁止读取 Holdout/Adversarial truth 正文来完成本验收。
