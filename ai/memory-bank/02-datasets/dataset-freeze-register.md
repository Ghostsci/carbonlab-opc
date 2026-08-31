# G1-B 数据冻结登记

## 当前登记

- 数据集版本：`synthetic-factory-v1.1.1-g1b-rc1`
- 登记状态：G1-B 标准答案正式冻结
- 人类批准时间：`2026-07-22T08:38:53Z`
- 冻结落地方式：本地 Git 提交 + OPC issue 附件受控冻结存储
- Git 提交：`f192941`（`Submit G1-B synthetic dataset repair package`）
- 冻结附件：`g1b-repair-package-f192941.tar.gz`
- 冻结附件 ID：`019f88e3-1265-791a-9b60-45916725c514`
- 冻结附件 SHA-256：`b5986cd35185553d05546a5bb2867b589e5e6a14a80c4058ac6bc95c9e48f960`
- 文件清单附件：`g1b-repair-files.txt`
- 文件清单附件 ID：`019f88e3-1284-7905-8c95-8ab456d85211`
- 文件清单附件 SHA-256：`82153454d782fa01317c9ab07730c0450a851efe5df0061de2f0ef10b94f5328`
- 数据路径：`validation/datasets/synthetic_factory_v1`
- manifest：`validation/datasets/synthetic_factory_v1/manifest.json`
- scenario_count：39
- dataset_sha256：`42d7c0237c1e8c5e1d8d169825f46ec810b064ce67101fb03ed7e24d6a4a547f`
- schema_version：`1.1.0`
- task_id：`factory_document_extraction_v1`
- 生成器版本：`synthetic-factory-generator-v1.1.1`
- 方法学版本：`M1-methodology-freeze-v1.0`
- 规则版本：`G1-A-electricity-indirect-v1.0`
- 随机种子：Candidate `1001-1015`，Holdout `2001-2015`，Adversarial `3001-3009`

## Split 数量

| Split | 数量 | 种子范围 | 状态 |
|---|---:|---|---|
| Candidate | 15 | `1001-1015` | 可用于开发调试 |
| Holdout | 15 | `2001-2015` | 未见集，正式评测前限制答案可见性 |
| Adversarial | 9 | `3001-3009` | 对抗集，正式评测前限制答案可见性 |

## 冻结条件

G1-B 正式冻结已满足：

- QA 复核 39 条确定性重算 `fail_count=0`。
- QA 复核 manifest/hash 与仓库提交一致。
- QA 确认可见性边界不向开发侧暴露 Holdout/Adversarial 标准答案。
- 人类负责人批准 G1-B 正式冻结。

冻结后禁止静默修改。任何数据、truth、manifest、哈希、生成器或规则变更必须升级数据集版本并重新走 QA 复核和人类审批。
