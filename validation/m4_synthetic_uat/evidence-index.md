# 证据索引

| 证据 | 路径 | 用途 |
|---|---|---|
| 固定 M3 归档 | `input-evidence/M3_MINIMUM_CLOSED_LOOP_V1.0.3_CORRECTED_CANONICAL.tar.gz` | 唯一候选输入，SHA-256 固定 |
| M3 DevSecOps 报告 | `input-evidence/CARB-16_M3_V1.0.3_CORRECTED_CANONICAL_DEVSECOPS.md` | 基线、补丁、三轮与限制复验 |
| M3 独立 QA 报告 | `input-evidence/CARB-16_M3_V1.0.3_CORRECTED_CANONICAL_INDEPENDENT_QA.md` | `ACCEPT` 及适用边界 |
| checkout 证据 | `environment/checkout-evidence.json` | URL、branch、SHA、命令、退出码和替代闭包 |
| 执行账本 | `environment/execution-ledger.json` | 每条运行命令、退出码、日志和工作区边界 |
| 冻结计划 | `test-plan.md` | 场景、成功条件、严重错误和观察点 |
| 主持指南 | `moderator-guide.md` | 不诱导、不改答案、不删失败的统一流程 |
| 逐场景矩阵 | `scenario-matrix.md` | 目标、步骤、状态、拒绝、判定与证据映射 |
| 逐场景文本证据 | `evidence/S*.json` | 候选字段、证据、可观察结果和控制检查 |
| 三轮原始场景证据 | `evidence/run-{1,2,3}/S*.json` | 三轮逐项留痕 |
| 三轮完整结果 | `results/replay-{1,2,3}.json` | canonical 对象与 run hash |
| 一致性摘要 | `results/replay-summary.json` | 8/8 分类、三轮哈希、一致率与候选 verdict |
| 制品契约自检 | `results/artifact-verification.json` | 16/16 输入、结果、权限和凭据落盘检查 |
| 失败样本 | `results/failure-samples.json` | 保留所有 expected rejection，不删除负面路径 |
| 原始日志 | `logs/` | M3 pytest、M4 重放、finalize、依赖检查 |
| 限制矩阵 | `limitations-matrix.md` | PASS 与 NOT_RUN_ENV 分离 |
| 演示脚本 | `demo-script.md` | 本地候选演示顺序和边界话术 |
| 操作手册 | `operation-manual.md` | 独立重放方法 |
| 候选 verdict | `verdict.md` | 事实、判断、限制和独立复核条件 |
| 回滚 | `rollback.md` | 精确删除边界 |
| 文件哈希 | `SHA256SUMS` | 包内逐文件完整性 |
