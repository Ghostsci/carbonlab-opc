# 07 异常处理规则

| 属性 | 值 |
|---|---|
| 规则 ID | `G1A2-EXCEPTION-001` |
| 版本 | `G1-A-v2.0.0-candidate.4` |
| 状态 | `COMPLETE_CANDIDATE / NOT_EFFECTIVE` |
| 依据 | AI 仅 candidate、9 字段全人工确认的批准语义；current contracts 的 missing/ambiguous/conflict；`DEC-20260814-01` 异常细节授权 |

## 通用动作

任何异常都不得靠常识、AI 置信度、代码默认值、跨场景复制、取平均、填 0、选择最新因子或自动改期解决。失败运行只记录 `validation_attempt` 和异常代码；不得创建排放结果。人工修正必须形成新 candidate_version、保留旧值/证据/原因，并重新确认。

## 异常表

| 异常 ID | 触发条件 | 固定动作 | 解除条件 |
|---|---|---|---|
| `EXC-MISSING-001` | 9 字段任一缺失、空白或条件信息不全 | 状态 `missing`；阻断；不得填 0 | 新版本带直接证据并确认 |
| `EXC-AMBIGUOUS-001` | 数值可见但单位/口径不明，或定位不唯一 | value=null；保留证据和原因；阻断 | 人工基于可读证据创建新版本 |
| `EXC-CONFLICT-001` | 同字段有两个不同值或期间/对象不一致 | value=null；完整保留双方证据；不得自动择一 | 人工决定并记录理由/版本 |
| `EXC-CONFIRM-001` | 未确认、AI/无权 actor、hash/版本不匹配或确认已撤销 | 阻断，不产生结果 | 有效人工确认事件且当前有效 |
| `EXC-RANGE-001` | 空字符串、CN 非 8 位、产量<=0、电量<0、非有限数或超 28/12 | 拒绝，不截断/取绝对值 | 新版本合法值 |
| `EXC-UNIT-001` | 单位缺失、未知、非固定单位或量纲不约消 | ambiguous/阻断；不猜测换算 | 直接单位证据和新确认版本 |
| `EXC-PERIOD-001` | 不属于四个 2026 完整自然季度、活动不完整覆盖或跨季度 | 阻断；不拆分、不外推 | 同期完整证据新版本 |
| `EXC-EVIDENCE-001` | quote 不命中/多次命中、错误文档类型、证据集合不一致 | 证据结论非 SUPPORTED；阻断 | 可唯一定位的直接证据 |
| `EXC-FACTOR-MISSING-001` | 无获批且精确适用的因子 | 阻断；禁止代码/行业默认回退 | 获批因子记录可验证 |
| `EXC-FACTOR-CONFLICT-001` | 多于一个同时适用因子或值/版本不一致 | 整次阻断；不自动择一 | 新版本明确唯一因子 |
| `EXC-DUPLICATE-001` | 同一场景/字段/证据重复提交 | 相同内容 hash 幂等，不重复加总；不同值转 conflict | 去重或人工冲突处理 |
| `EXC-PRECISION-001` | 二进制 float、超精度、提前舍入或舍入模式不明 | 阻断并保留原始文本 | 规范十进制新版本 |
| `EXC-PROMPT-INJECTION-001` | 文档被分类为指令，或未命中严格正常数据语法而需复核 | 隔离；formal_write=false；确认状态不变；不创建确认事件或结果 | 不能由该文本解除；独立人工复核 |
| `EXC-BOUNDARY-001` | 非合成、跨企业/装置/产品/季度、非外购电或结果被扩大解释 | 阻断并隔离 | 回到获批边界或进入 HUMAN_REQUIRED |
| `EXC-VERSION-001` | 规则/字段/因子/单位/数据版本/hash 不一致 | 阻断，不混用版本 | 精确版本链闭合 |

## 冲突优先级

异常没有自动“数据来源优先级”。`installation_profile`、`production_ledger`、`electricity_bill` 只定义允许来源类型，不意味着其中任一文件可覆盖另一个文件的冲突。因子没有“最新优先”；本范围只允许唯一获批记录。

## 确定性测试

测试夹具覆盖缺失、单位歧义、产量冲突、未确认、撤销、负值、错季度、证据错位、零/多因子、重复、超精度和提示注入。负外购电与零/负产量统一返回已登记的 `EXC-RANGE-001`。所有失败项必须返回固定异常 ID 且 `result_created=false`；合法 0 kWh 必须与 missing 区分。

异常码集合必须闭包：`test-cases.json` 中所有非 `PASS*` 预期状态，以及校验器所有可执行分支可发出的 `EXC-*`，都必须存在于 `rules.json.exceptions.codes`。校验器从运行状态函数的语法树提取字面异常码，并递归提取夹具异常码；任一未声明代码使验证非零退出。`--inject-undeclared-code` 是固定负向重放，必须返回退出码 1。

提示指令判定只接受不可由文档控制的 `rules.json.exceptions.prompt_injection_policy.content_classifier` 作为策略入口，只读取原始 `document_content`。归一化顺序固定为 Unicode NFKC、casefold、移除 Unicode `Cf` 及登记的 Default_Ignorable 范围，再折叠空白、标点和分隔符为紧凑字母数字串；因此零宽字符和分隔符混淆不能拆断特征。夹具的 `case_type`、`untrusted_document_label` 与 `expected_outcome` 只用于编排和断言，分类器不读取这些字段。

分类采用三态失败关闭：控制/绕过特征与受治理目标或特权动作联合出现，或受治理目标与特权动作联合出现时为 `INSTRUCTION`；只在完整命中冻结的账单/台账正常数据语法时为 `BENIGN_DATA`；其他内容一律为 `REVIEW_REQUIRED`。`INSTRUCTION` 与 `REVIEW_REQUIRED` 均返回 `EXC-PROMPT-INJECTION-001`，有限短语不再是唯一安全判据。四条审计攻击（中文释义绕过、含 U+200B 的拆分、英文改写、CONFIRMED 状态修改）必须全部归类 `INSTRUCTION`，正常外购电对账单必须归类 `BENIGN_DATA`，未知备注必须归类 `REVIEW_REQUIRED`。

所有三态均由冻结的 `safe_output` 强制 `formal_write_allowed=false`、确认状态 `UNCHANGED`、`confirmation_event_created=false`、`result_created=false`；正常数据的 PASS 也只表示候选仍隔离，不代表确认或产生正式结果。恶意正文故意带 `BENIGN` 标签仍被拦截，正常正文故意带 `INJECTION` 标签仍按正文归类。`--inject-prompt-label-mismatch` 将正常账单正文替换为含 U+200B 的审计攻击但保留 benign 期望，必须非零退出。文档文本始终不是授权或确认事件。

## 差异结论

异常规则没有改变已批准业务事实，只把 existing fail-closed 行为和本次获授权细节写成唯一动作。未分配真实角色或修改系统权限。
