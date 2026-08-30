---
name: carbon-evidence-quality-review
description: Independently review A-02 candidates against owned evidence, units, ontology and deterministic constraints. Use only for A-03; do not repair facts or replace human confirmation.
---

# A-03 碳数据质检

## 目标

独立判断候选字段是否有对应证据、单位是否适用、数据约束是否满足，并输出可复核的发现清单。

## 必须执行

1. 验证候选快照、文件 ID、内容哈希、租户和企业绑定。
2. 对每个关键字段执行“字段—证据”关联检查，文档中出现相同字符串不等于支持该字段。
3. 检查数值精度、正值约束、单位、本体概念和允许的数据来源。
4. 每个警告或阻断项必须关联字段键，并尽可能返回工作表、单元格、原文行号、表头、原始值和上下文摘要。
5. 判断单位时必须同时读取候选值、表头和单位列；不得因为结构化候选只保留数字而制造假警告。
6. 记录使用的 RAG 检索运行 ID、规则版本和每项检查结果。
7. 输出 `pass`、`pass_with_warnings` 或 `fail`；不确定时降低结论而不是猜测。

## 禁止

- 自动改写企业事实或证据。
- 代替 H-01 确认业务数据。
- 选择排放因子、执行排放计算或发布护照。
- 仅凭无关引文存在就判定证据支持。

## 交付

输出必须符合 `output.schema.json`。每项发现包含检查键、字段、结果、说明、检测值、期望值、人工动作和可选原文定位；分数仅代表自动检查覆盖程度，不得表述为事实准确率。

## 停止与交接

任何阻断发现都必须关闭正式写入门禁；警告项必须明确交给 H-01 或 H-02 处理。H-01 未逐项查看原文并提交处置说明前，`pass_with_warnings` 不得授权正式写入。
