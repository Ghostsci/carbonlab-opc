# 逐场景验收矩阵

| ID | 用户目标 | 关键步骤 | 状态转换 | 预期拒绝 | 判定 | 等价文本证据 |
|---|---|---|---|---|---|---|
| S01 | 核对单条候选与来源并确认 | 上传→查看字段/证据→签名确认→看计算回执 | uploaded→candidate→calculated_local_candidate | 无 | `PASS` | `evidence/S01_NORMAL_SINGLE.json` |
| S02 | 批量处理且异常逐项隔离 | 2 完整+1 缺失→批量确认→逐项核对 | 完整项 calculated；缺失项 guard_rejected | unresolved production_output | `PASS` | `evidence/S02_BATCH_ISOLATION.json` |
| S03 | 识别缺失用电证据 | 上传缺失文件→看 missing/空证据→尝试确认 | candidate_missing→guard_rejected | unresolved purchased_electricity | `PASS` | `evidence/S03_MISSING_EVIDENCE.json` |
| S04 | 避免猜测产量单位 | 上传单位未标文件→看 ambiguous→尝试确认 | candidate_ambiguous→guard_rejected | unresolved production_output | `PASS` | `evidence/S04_UNIT_ANOMALY.json` |
| S05 | 识别起止日期冲突 | 上传反向期间→观察校验 | validation_rejected→no_candidate | invalid_period | `PASS` | `evidence/S05_PERIOD_CONFLICT.json` |
| S06 | 阻断文档提示注入 | 上传注入文件→看风险标记→尝试确认 | candidate_risk_flagged→guard_rejected | document_instruction_detected | `PASS` | `evidence/S06_PROMPT_INJECTION.json` |
| S07 | 阻断伪造/越权确认 | 自报 actor→伪造签名→无权角色 | credential_rejected→candidate_unchanged | 三项精确拒绝 | `PASS` | `evidence/S07_UNAUTHORIZED_CONFIRMATION.json` |
| S08 | 阻断未确认发布 | 不确认→改 published/权限 true→核对原对象 | publish_contract_rejected→candidate_unchanged | 三字段契约错误 | `PASS` | `evidence/S08_UNCONFIRMED_PUBLISH.json` |

字段值、单位、证据引文、控制断言和完整可观察结果均保存在对应 JSON；该 JSON 是本轮“截图或等价可复查文本证据”。
