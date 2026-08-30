---
name: carbon-passport-compilation
description: Compile an installation carbon passport draft from formal, approved records for A-04. Use only after human gates and deterministic calculation; never alter ledger facts or publish externally.
---

# A-04 碳护照编制

## 目标

把装置身份、正式活动数据、证据、人工确认、规则版本和确定性计算结果装配成可复放的护照草稿。

## 必须执行

1. 只读取当前租户和企业范围内的正式记录。
2. 验证 H-01 企业事实确认、H-02 方法学确认和 R-01 计算结果均存在。
3. 保存每个组成记录的稳定 ID、版本、内容哈希和来源关系。
4. 对缺失项给出明确评估，不利用模型补造正式事实。
5. 生成草稿后交给 H-03 最终复核与发布。

## 禁止

- 修改活动账本、因子快照、计算结果或历史护照版本。
- 把草稿描述为法定核查结论。
- 自动发布、自动创建外部共享或绕过 H-03。
- 在护照中写入未脱敏的密钥、提示词或模型隐藏推理。

## 交付

输出必须符合 `output.schema.json`，包含护照草稿版本、完整度、质量等级、派生来源和下一责任门。

## 停止与交接

正式数据缺失、版本冲突、哈希校验失败或归属不一致时停止编制，并输出阻断项。
