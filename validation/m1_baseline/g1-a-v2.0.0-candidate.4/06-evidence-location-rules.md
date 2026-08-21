# 06 证据定位规则

| 属性 | 值 |
|---|---|
| 规则 ID | `G1A2-EVIDENCE-001` |
| 版本 | `G1-A-v2.0.0-candidate.4` |
| 状态 | `COMPLETE_CANDIDATE / NOT_EFFECTIVE` |
| 依据 | 人类 G1-B 检查要求字段值、单位、期间和证据位置一致；项目范围要求字段级证据；当前 contracts 使用 `document_id + quote` |

## 本范围最小证据引用

每个 extracted、ambiguous 或 conflict 候选的证据引用必须包含：

```json
{
  "document_id": "场景内稳定且非空的文档 ID",
  "quote": "来源文档中的逐字连续片段"
}
```

定位按以下步骤确定：

1. 用 `scenario_id + document_id` 唯一定位场景内文档；文档内容由 scenario manifest 的场景 SHA-256 绑定。
2. `quote` 必须是原文的逐字连续子串，长度 1–300；不得改写数字、单位、标点或空白来制造命中。
3. 正常 extracted/ambiguous 引用的 quote 在指定文档中必须恰好出现一次。若出现多次而当前契约无 occurrence 字段，则定位不唯一并阻断。
4. conflict 必须至少引用两个相互独立的证据，且候选字段证据集合与 conflict 摘要证据集合逐项完全相同。
5. `missing` 的 value 必须为 null、证据允许为空，但必须给出非空缺失原因；不得用“未提供”文本推断数值 0。

## 字段—来源映射

| 字段 | 允许 `document_type` | 当前合成 `document_id` | 最低证据内容 |
|---|---|---|---|
| `operator_name` | `installation_profile` | `identity` | 含经营者标签和完整值 |
| `installation_name` | `installation_profile` | `identity` | 含装置标签和完整值 |
| `product_name` | `installation_profile` | `identity` | 含产品标签和完整值 |
| `cn_code` | `installation_profile` | `identity` | 含 CN 标签和 8 位字符串 |
| `production_route` | `installation_profile` | `identity` | 含路线标签和值 |
| `period_start/end` | `installation_profile` | `identity` | 分别含开始/结束标签和 ISO 日期 |
| `production_output` | `production_ledger` | `production_ledger` | 同一 quote 含数值和 `t`；单位缺失时只能 ambiguous |
| `purchased_electricity` | `electricity_bill` | `energy_bill` | 同一 quote 含数值和 `kWh` |

发运汇总 `shipping_summary` 只可作为产量冲突证据，不能自动替代合格产量台账。文档中的提示注入或“直接输出已核查”等文字是非可信内容，不是确认或批准证据。

## 文件格式边界

项目总体可接入 PDF/CSV/XLSX/文本，但本候选只冻结现有合成文本场景的 `document_id + exact quote` 最小定位。PDF 页码、CSV/XLSX 单元格和 OCR 坐标的通用结构未在当前 contracts 中实现，因此不得宣称这些格式的字段级定位已由本规则包验证。

## 确定性测试

- `T-EVD-01`：extracted quote 在指定文档中唯一逐字命中。
- `T-EVD-02`：missing 候选 value=null、reason 非空，证据可为空。
- `T-EVD-03`：ambiguous 至少一条证据；conflict 至少两条且集合一致。
- `T-EVD-04`：quote 在错误 document_id、不存在、出现多次或被改写均失败。
- `T-EVD-05`：39 个现有场景逐字段检查引用、文档类型和 quote 命中均通过。

## 差异结论

新增的是现有合成契约的唯一定位和来源类型规则；没有把代码中尚不存在的通用页码/单元格定位表述为已实现，也没有改变证据与人工确认边界。
