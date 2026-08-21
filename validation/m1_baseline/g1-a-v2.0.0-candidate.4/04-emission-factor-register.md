# 04 排放因子登记表

| 属性 | 固定值 |
|---|---|
| 规则 ID | `G1A2-FACTOR-001` |
| 因子 ID | `EF-SYN-PURCHASED-ELECTRICITY-2026-001` |
| 因子版本 | `G1-A-v2.0.0-candidate.4` |
| 值 | `0.500000` |
| 单位 | `kgCO2e/kWh` |
| 排放源 | `purchased_electricity` |
| 因子性质 | 项目内合成测试常量；不是官方、地域或企业因子 |
| 地域 | `NOT_APPLICABLE_SYNTHETIC` |
| 年份/期间 | 仅 2026 年四个允许自然季度 |
| 数据版本 | 治理标签 `synthetic_factory_v1.1` ↔ 代码标识 `synthetic-factory-v1.1` |
| 来源 | 人类批准评论 `bcd5a7c6-5786-408e-8dc8-637d539157b5` |
| 当前状态 | `CANDIDATE / NOT_EFFECTIVE`，待本包独立审计及 Owner 自动批准 |
| 撤销/替代 | 新再基线记录；不冒充或恢复旧因子文件；未撤销原评论语义 |

## 来源优先级与唯一选择

本范围不存在地域、技术或供应商因子选择。固定优先级只有：

1. 获批且 hash/版本/数据版本/2026 季度/排放源全部精确匹配的本因子记录；
2. 无可用因子，失败关闭。

代码硬编码值、模型建议、行业平均值、外部公开值、最新年份值或“最接近”值均没有回退资格。若输入集合出现第二个同时适用因子，即触发冲突并整次阻断，不按日期、版本号、置信度或输入顺序自动选择。

## 适用性谓词

```text
factor_applicable(f, case) :=
  f.id == EF-SYN-PURCHASED-ELECTRICITY-2026-001
  AND f.value == 0.500000
  AND f.unit == kgCO2e/kWh
  AND f.dataset_version == synthetic-factory-v1.1
  AND case.period in allowed_2026_quarters
  AND case.source == purchased_electricity
  AND case.synthetic == true
  AND f.status == APPROVED
```

候选阶段最后一项恒为 false，因此本包自身不能放行 G1-B；Owner 自动批准后才可生成状态为 APPROVED 的不可变版本记录。

## 确定性测试

- `T-FAC-01`：值和单位精确匹配、数据版本/期间/排放源/合成标签匹配且批准后，唯一选中。
- `T-FAC-02`：因子缺失或仍为 CANDIDATE，不生成结果。
- `T-FAC-03`：出现两个同时适用因子，冲突阻断。
- `T-FAC-04`：真实数据标签、2027 期间、非外购电源或其他数据版本均阻断。
- `T-FAC-05`：39 个现有场景的 truth 因子字符串均精确为 `0.500000`。

## 差异结论

因子值、单位、用途和来源优先级没有变化；新增 ID、版本、适用谓词、候选状态和替代关系。它把代码中的相同常量降为实现观察，把获批规则记录设为唯一可消费来源。
