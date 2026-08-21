# 竞赛最小演示交付说明（competition/minimum-demo-delivery）

基线：main `c4f0b5b`（docs: add project handoff and OPC takeover guide）。

本分支把 OPC 平台工单中已通过独立 QA 验收的 M1–M6 里程碑成果，以源代码、测试代码和必要文档的形式合入仓库。每个里程碑一个提交：

| 提交 | 里程碑 | 版本 | 内容 |
|---|---|---|---|
| feat(m1) | M1 权威规则与标准答案基线 | G1-A-v2.0.0-candidate.4 / G1-B-v2.0.2 | 8 项权威核算规则、rules.json、验证脚本、候选/留存/对抗/可用性场景与黄金答案 |
| feat(m2) | M2 合成数据正式评测闭包 | M2_FORMAL_REFROZEN_PATCH_AND_PYTEST_V4 | 冻结登记、访问审计链、三轮重放日志、providers.py 延迟导入修复、依赖锁定 |
| feat(m3) | M3 候选护照最小闭环 | M3_MINIMUM_CLOSED_LOOP_V1.0.3_CORRECTED_CANONICAL | `backend/services/candidate_passport_v1.py`、19 项测试、证据与补丁 |
| feat(m4) | M4 合成用户验收 | M4_SYNTHETIC_UAT_V1.0.0 | 测试计划、场景矩阵、操作手册、演示脚本与执行记录 |
| feat(m5) | M5 候选交付证据包 | M5_CANDIDATE_DELIVERY_EVIDENCE_PACK_V1.0.3 | 交付清单、限制矩阵、独立重放证据 |
| feat(m6) | M6 本地候选收官 | M6_LOCAL_CANDIDATE_CLOSURE_V1.0.1 | 发布门禁策略、风险登记、负向拒绝样本与验收结论 |

材料位置：`validation/m1_baseline/`、`validation/m2_formal_evaluation/`、`validation/m3_candidate_passport_v1/`、`validation/m4_synthetic_uat/`、`validation/m5_delivery_evidence/`、`validation/m6_local_candidate_closure/`。

## 运行最小闭环测试

```bash
pip install pytest "pydantic>=2" pydantic-settings fastapi sqlalchemy python-jose
python -m pytest backend/tests/test_candidate_passport_v1.py -q
# 预期：19 passed（正常链路、未确认拦截、伪造签名/错误 audience/过期身份/越权角色拒绝、批处理确定性）
```

完整前后端启动方式见根目录 README（Docker Compose）。

## 边界声明

- 全部数据为合成数据；成果状态为 `SYNTHETIC_ONLY / LOCAL_CANDIDATE`。
- 不含真实企业数据、生产凭证、API Key 或个人信息。
- 不代表真实企业试点、生产部署或正式护照发布。

## 已知排除项

- G1-B 包内嵌的 `sources/G1-A-v2.0.0-candidate.4.tar` 副本未提交（G1-A 已以展开形式在同一提交中入库）。
- M2 依赖 wheelhouse 二进制未提交；依赖版本以 `validation/m2_formal_evaluation/requirements-py312.lock` 锁定，校验清单保留（`wheelhouse-py312.sha256`）。
