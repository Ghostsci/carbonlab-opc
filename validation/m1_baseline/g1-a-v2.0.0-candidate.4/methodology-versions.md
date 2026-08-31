# 方法学版本与替代关系

| 字段 | 值 |
|---|---|
| 当前候选 | `G1-A-v2.0.0-candidate.4` |
| 对象状态 | `CANDIDATE` |
| 生效状态 | `NOT_EFFECTIVE` |
| 批准状态 | `PENDING_INDEPENDENT_AUDIT` |
| 创建原因 | 依据 `DEC-20260814-01` 对不可恢复的旧规则证据进行全新再基线，并修复 candidate.3 独立审计指出的有限短语绕过缺口 |
| 适用数据版本 | 治理标签 `synthetic_factory_v1.1` 映射到代码规范标识 `synthetic-factory-v1.1` |
| 适用报告期间 | 2026 年任一完整自然季度；每个场景只能选择其中一个 |
| 替代对象 | 仅在获批后替代旧规则“文件证据不可达”的使用入口；不冒充旧文件恢复 |
| 不撤销对象 | 人类语义批准评论 `bcd5a7c6-5786-408e-8dc8-637d539157b5` |
| 旧失败包 | `G1-A-authoritative-rules-snapshot-v1.0-BLOCKED` 保留为 `LEGACY_EVIDENCE_UNRECOVERABLE` 差异证据 |
| 直接前版 | `G1-A-v2.0.0-candidate.3`；独立审计 `RETURN`；原包保留、未生效、未覆盖 |
| 后续版本 | 任何字节或规则变更必须新增候选版本，记录原因、影响字段、旧/新哈希和回归结果 |

## 版本记录

| 版本 | 状态 | 变更 | 语义变化 |
|---|---|---|---|
| `G1-A-v2.0.0-candidate.1` | `RETURNED / RETAINED / NOT_EFFECTIVE` | 首个 8 项新再基线候选；审计发现负值异常码未登记、异常码闭包断言缺失、提示注入夹具缺失 | 无 |
| `G1-A-v2.0.0-candidate.2` | `RETURNED / RETAINED / NOT_EFFECTIVE` | 统一 `EXC-RANGE-001` 并关闭异常码集合；审计确认这些项通过，但退回自报标签驱动的提示注入测试 | 无 |
| `G1-A-v2.0.0-candidate.3` | `RETURNED / RETAINED / NOT_EFFECTIVE` | 提示注入改为受控策略读取原始正文且标签不受信；审计确认安全输出与因果链通过，但有限 13 短语可被零宽字符和改写绕过 | 无 |
| `G1-A-v2.0.0-candidate.4` | `PENDING_INDEPENDENT_AUDIT / NOT_EFFECTIVE` | 新增 Default_Ignorable/分隔符归一化；以指令特征、严格正常数据语法和未知复核三态失败关闭；加入四条审计攻击与正常账单反例 | 无 |

## 状态迁移

```text
CANDIDATE
  ├─ 独立审计 RETURN/HUMAN_REQUIRED → WITHDRAWN_OR_REVISED（保留本版）
  └─ 独立审计 ACCEPT + 无实质语义变化
       → Owner 按 DEC-20260814-01 自动批准
       → APPROVED / EFFECTIVE_FOR_G1-B-v2_INPUT
```

执行人不得批准自己的交付。独立审计 `ACCEPT` 只证明候选包符合本次再基线验收，不等于真实业务事实已确认、生产方法学启用、护照发布或第三方/法定核查完成。

## 实质变化判定

以下任一变化必须停止并转 `HUMAN_REQUIRED`，不得由本候选自动吸收：

1. 从一个虚拟企业/装置/产品/季度扩展到其他组织、装置、产品集合或多年期间；
2. 修改 9 个核心字段集合或取消全字段人工确认；
3. 允许 AI 直接确认、正式写入或生成正式结果；
4. 将公式从“活动数据 × 排放因子”改为其他类型，或纳入外购电之外的排放源；
5. 修改因子值、因子来源优先级或允许未批准的回退因子；
6. 改变组织、运营、排放源或结果含义边界；
7. 将工程/合成验证表述为真实企业、监管、鉴证或法定核查结论。
