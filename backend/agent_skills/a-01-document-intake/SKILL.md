---
name: carbon-document-intake
description: Register and classify an owned factory document before any carbon-data extraction. Use only for A-01 intake work; never infer missing business facts or write formal ledger data.
---

# A-01 碳数据收件

## 目标

把一个租户与企业范围内的原始文件登记为可追踪的数据对象，输出文件身份、类型和基础完整性结果。

## 必须执行

1. 使用服务器保存的文件 ID、租户、企业和 SHA-256，不信任客户端替代值。
2. 检查扩展名、MIME、大小、重复内容和可处理性。
3. 只输出文档分类与完整性结果，不提取或确认业务事实。
4. 无法识别时返回 `unknown` 或阻断原因，不猜测。

## 禁止

- 修改原文件或其哈希。
- 根据文件名补造企业、期间、数量等字段。
- 写入正式活动账本、选择排放因子或生成排放结果。

## 交付

输出必须符合 `output.schema.json`，并带有来源文件 ID、内容哈希、处理状态和下一岗位 `A-02`。

## 停止与交接

文件不受支持、内容损坏、租户归属不明或安全检查失败时停止，并明确交给人工处理。
