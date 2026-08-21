# G1-B-v2.0.2 数据集卡

> PREPARATION_ONLY / CANDIDATE / NOT_APPROVED

本候选包含 39 个完全合成场景。结构化事实先生成，独立标准答案再由 Decimal 确定性程序计算，最后渲染 JSON、CSV、XLSX、PDF 与文本；不使用模型生成、修正或解释答案。

## 分层

- Candidate：12，仅开发与错误定位。
- Holdout：10，仅独立资格评测。
- Adversarial：9，仅独立安全与鲁棒性评测。
- Usability：8，仅有主持的用户任务测试。

Holdout/Adversarial truth 只出现在 restricted QA 制品；开发制品泄漏检查必须通过。包内控制为可执行的本地候选证据，不声称已修改外部 IAM 或启用 WORM。

## 规则与计算

- 排放量 = 外购电 kWh × 0.500000 kgCO2e/kWh ÷ 1000；
- 强度 = 排放量 tCO2e ÷ 产量 t；
- 排放与强度都从未舍入原始值分别以 ROUND_HALF_UP 量化到 0.000001；
- 任一候选都不得正式写入，且必须人工确认；
- 规则来源固定为 G1-A-v2.0.0-candidate.4 归档 `afabf7b7f8ff7b5c6366949324de1ff82db0d7d45f2aecfb4bd2b7dc2bb59749`；G1-B 数据候选仍等待独立 QA。

## 覆盖

正常、缺失、冲突、单位异常、期间异常、重复文件、异常大数、证据错配、文档指令干扰，以及 8 个可用性审阅任务。

风险标签计数：CONFLICT=5，DOCUMENT_INSTRUCTION_INTERFERENCE=6，DUPLICATE_FILE=4，EVIDENCE_MISMATCH=3，EXTREME_VALUE=4，MISSING=5，NORMAL=5，PERIOD_ANOMALY=4，PERIOD_MISMATCH=1，PRODUCTION_OUTPUT=6，PURCHASED_ELECTRICITY=6，REVERSED_PERIOD=2，UNIT_ANOMALY=5，UNREGISTERED_MWH=1，USABILITY_REVIEW=8。

## 限制

不包含真实企业数据、真实法规适用结论、生产权限、正式模型资格、正式护照发布或人类冻结批准。PDF 为确定性机器可读汇总，不用于测试复杂版式/OCR。

## 重建

在解包根目录运行 `./scripts/replay_g1_b_v2.sh`。零第三方 Python 依赖；具体环境和命令见 `environment.md` 与 `rebuild.md`。
