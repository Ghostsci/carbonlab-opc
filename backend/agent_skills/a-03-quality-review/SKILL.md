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
4. 记录使用的 RAG 检索运行 ID、规则版本和每项检查结果。
5. 输出 `pass`、`pass_with_warnings` 或 `fail`；不确定时降低结论而不是猜测。

## 禁止

- 自动改写企业事实或证据。
- 代替 H-01 确认业务数据。
- 选择排放因子、执行排放计算或发布护照。
- 仅凭无关引文存在就判定证据支持。

## 交付

输出必须符合 `output.schema.json`，每项发现包含检查键、结果、说明和可选证据引用。

## 停止与交接

任何阻断发现都必须关闭正式写入门禁；警告项必须明确交给 H-01 或 H-02 处理。
