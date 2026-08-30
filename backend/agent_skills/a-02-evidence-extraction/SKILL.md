---
name: carbon-evidence-extraction
description: Extract carbon-data field candidates with source references for A-02. Use after document intake; candidates remain unconfirmed and must never be written as formal facts.
---

# A-02 碳证据提取

## 目标

从已登记文件中提出结构化字段候选，让每个候选都能回到具体源文件和可核验位置。

## 必须执行

1. 读取 A-01 已确认的文件身份和服务器内容哈希。
2. 提取当前文档类型允许的字段，保留原始表示、标准化值、置信度和证据引用。
3. 数值保持字符串精度；不得经 `float` 静默改值。
4. 找不到证据的字段标记为待确认，不利用常识补齐。
5. 输出候选后交给 A-03 独立质检。

## 禁止

- 把候选字段称为已确认事实。
- 编造页码、单元格、引用或企业信息。
- 自动修正原始数据、选择方法学或执行排放计算。
- 写入正式活动账本。

## 交付

输出必须符合 `output.schema.json`。每个字段至少包含键、值、状态和来源引用；无法定位时来源引用必须为空并说明原因。

## 停止与交接

内容不足、字段冲突、单位不明或证据定位失败时保留异常，不得强行给出高置信结果。
