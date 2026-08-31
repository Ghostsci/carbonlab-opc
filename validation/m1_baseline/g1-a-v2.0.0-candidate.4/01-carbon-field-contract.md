# 01 字段契约

| 属性 | 值 |
|---|---|
| 规则 ID | `G1A2-FIELD-001` |
| 版本 | `G1-A-v2.0.0-candidate.4` |
| 状态 | `COMPLETE_CANDIDATE / NOT_EFFECTIVE` |
| 语义依据 | 批准评论 `bcd5a7c6-5786-408e-8dc8-637d539157b5` |
| 技术补齐授权 | `DEC-20260814-01` / `c30ece05-998e-4c96-bea4-5c9c3083dce7` |
| 代码观察 | `backend/validation/contracts.py`、`backend/validation/synthetic_factory.py` |

## 通用字段规则

候选包必须包含全部 9 个字段对象；“对象必填”不等于可以填造业务值。字段对象状态只能为 `extracted`、`missing`、`ambiguous`、`conflict`。所有对象的 `requires_human_confirmation` 必须为 `true`，AI 输出的整个候选对象必须固定 `formal_write_allowed=false`。

字段从 candidate 成为本次确定性计算输入，必须同时满足：状态为 `extracted`、值和单位符合本契约、证据结论为 `SUPPORTED`、有效人工确认事件与候选内容 SHA-256/版本精确绑定、确认未撤销、无开放阻断异常。置信度、模型名称或单一候选均不能替代人工确认。本包只定义语义门，不创建或授予任何人员权限。

## 9 个核心字段

| 代码 / 中文名 | 类型与是否必填 | 允许单位 | 报告期间 | 允许来源文件类型 | 合法范围 | 缺失/冲突/异常动作 | 人工确认 |
|---|---|---|---|---|---|---|---|
| `operator_name` / 经营者名称 | 非空字符串；候选对象必填；正式输入必填 | 无 | 场景级，不随期间变化 | `installation_profile` | 去除首尾空白后 1–200 字符；不得由文件名推断 | 空值=`missing`；多来源不同值=`conflict`；不自动择一 | 必须 |
| `installation_name` / 生产装置名称 | 非空字符串；对象/正式输入必填 | 无 | 场景级 | `installation_profile` | 1–200 字符；一个场景恰一个值 | 同上；跨装置证据阻断 | 必须 |
| `product_name` / 产品名称 | 非空字符串；对象/正式输入必填 | 无 | 场景级 | `installation_profile` | 1–200 字符；一个场景恰一个值 | 空值/多值失败关闭 | 必须 |
| `cn_code` / CN 编码 | 字符串；对象/正式输入必填 | 无 | 场景级 | `installation_profile` | 精确 8 位 ASCII 数字 `^[0-9]{8}$` | 保留前导零；禁止数值化；非法格式阻断 | 必须 |
| `production_route` / 生产路线 | 非空字符串；对象/正式输入必填 | 无 | 场景级 | `installation_profile` | 1–80 字符；本版不新增路线枚举；代码现值 `bf_bof/eaf` 只是观察值 | 未知非空值不能由 AI 映射；须人工确认；空值阻断 | 必须 |
| `period_start` / 期间开始 | ISO 日期字符串；对象/正式输入必填 | 无 | 见期间规则 | `installation_profile` | 仅四个允许季度起始日 | 与 `period_end` 不组成允许日期对即阻断 | 必须 |
| `period_end` / 期间结束 | ISO 日期字符串；对象/正式输入必填 | 无 | 见期间规则 | `installation_profile` | 仅四个允许季度结束日 | 与 `period_start` 不组成允许日期对即阻断 | 必须 |
| `production_output` / 合格产量 | 规范十进制字符串；对象/正式输入必填 | `t` | 与报告季度完全一致 | `production_ledger` | `>0`；最大精度 28、最大小数位 12；拒绝 float、NaN、Infinity、千分位进入正式值 | 缺失、单位未标、冲突、非正或超精度均阻断；不得填 0 | 必须 |
| `purchased_electricity` / 外购电量 | 规范十进制字符串；对象/正式输入必填 | `kWh` | 与报告季度完全一致 | `electricity_bill` | `>=0`；最大精度 28、最大小数位 12；拒绝 float、NaN、Infinity、千分位进入正式值 | 缺失/冲突/负值/单位错/超精度阻断；0 与缺失严格区分 | 必须 |

## 状态机

```text
AI/导入创建候选 → UNCONFIRMED
UNCONFIRMED + 有效人工确认（SUPPORTED 证据、对象 hash/版本匹配） → CONFIRMED
UNCONFIRMED + 人工拒绝 → REJECTED
CONFIRMED + 撤销事件 → REVOKED
REJECTED/REVOKED 不得原位复活；修正必须创建新 candidate_version
```

只有 9/9 当前版本均为 `CONFIRMED` 时，场景才满足 G1-A-v2 输入完整性。该条件用于合成规则包重放，不表示真实企业事实已确认。

## 确定性测试

- `T-FLD-01`：字段集合必须精确等于批准的 9 项，多/少任一项失败。
- `T-FLD-02`：任一字段 `requires_human_confirmation=false` 失败。
- `T-FLD-03`：单一高置信 AI extracted 候选仍为 UNCONFIRMED，不产生结果。
- `T-FLD-04`：8 位 CN 作为字符串保留；7/9 位或非数字失败。
- `T-FLD-05`：产量 0、负电量、二进制浮点或超 28/12 精度失败。

## 差异结论

相对批准语义没有字段增删，也没有降低人工确认要求；新增的是可程序化类型、范围、来源映射和状态门。相对当前 contracts 完全保留 9 字段、四类 candidate 状态和 `formal_write_allowed=false`。
