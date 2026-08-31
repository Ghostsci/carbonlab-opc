# M4_SYNTHETIC_UAT_V1.0.0 manifest

## 结论

- 阶段候选 verdict：`ACCEPT`
- 独立复核：仍需由模型评测与质量保证工程师执行；本主责未自审批准。
- 运行模式：`SYNTHETIC_ONLY_LOCAL_CANDIDATE`
- 场景：8/8 `PASS`
- 三轮语义一致率：`100%`
- 三轮 canonical SHA-256：`a08a2451a7083933ff314a009e29a04266b7dcc9203c069700df623cb327a997` / 同值 / 同值
- M3 回归：三轮各 `19 passed`，exit 0
- 制品契约自检：16/16 `PASS`

## 固定输入闭包

- 仓库 URL：`https://github.com/Ghostsci/carbonlab-opc.git`
- 声明分支：`main`
- 固定 commit：`c4f0b5bab63572dd0b9722be7aa12293fc3fb2b8`
- 固定 tree：`29276451fd21482cffdab828c655bfbb5c428221`
- 唯一 M3 输入：`M3_MINIMUM_CLOSED_LOOP_V1.0.3_CORRECTED_CANONICAL`
- M3 归档附件 ID：`01a000aa-67f3-7155-accd-e1971424770a`
- M3 归档 SHA-256：`60abf4fd50a1b1922f31958c4a50ec56330da5b251b1a761973295cd5b178d63`
- M3 独立 QA 评论：`80d96eac-c79b-4474-a929-f3a785252726`，verdict `ACCEPT`
- M3 Owner 退出登记：`d99ea43f-98b5-43f4-bcba-ef6df3a914d4`
- 未采用：未经独立验证的 V1.0.4。

`opc repo checkout` 已物化固定 ref 的源码，但本地 `.git` 指向缺失的工作树管理目录，Git 身份命令 exit 128；重试 checkout 因同名任务分支已存在而 exit 255。这两项如实分类为 `NOT_RUN_ENV`。本轮通过已验收 M3 归档、独立 DevSecOps/QA 报告、归档哈希、包内 10/10 哈希、标准补丁 dry-run/apply 与逐字节比对建立替代输入闭包；详见 `environment/checkout-evidence.json`。

## 场景结果

| ID | 覆盖 | 分类 | 可观察结果 |
|---|---|---|---|
| S01 | 正常单条 | `PASS` | 候选→签名确认→确定性计算；1764.5905 tCO2e |
| S02 | 批量 | `PASS` | 两个完整项计算；一个缺失项逐项拒绝 |
| S03 | 缺失证据 | `PASS` | 用电字段 missing、证据为空、确认被拒绝 |
| S04 | 单位异常 | `PASS` | 产量保持 ambiguous，不猜单位、不计算 |
| S05 | 期间冲突 | `PASS` | `invalid_period`，候选生成前拒绝 |
| S06 | 提示注入 | `PASS` | 风险标记，签名凭据不能绕过 guard |
| S07 | 未授权确认 | `PASS` | 自报身份、伪造签名、无权角色均拒绝 |
| S08 | 未确认发布 | `PASS` | published/两个 true 标志均由契约拒绝 |

逐场景用户目标、步骤、候选字段、字段级证据、状态转换、预期拒绝、控制检查及等价文本证据见 `evidence/*.json`；三轮原始对象见 `results/replay-*.json`。

## 硬门核验

- AI 输出在有效签名确认前保持 `candidate`；异常或越权不产生确认记录。
- 排放量由 `synthetic-electricity-rule-v1` 和 Decimal/Quantity 引擎确定性计算，不由 AI 生成。
- 确认动作不能携带自报 actor；签名伪造和无权角色均 fail-closed。
- 所有可生成护照始终 `formal_write_allowed=false`、`publish_allowed=false`。
- 缺失、单位异常、期间冲突、提示注入和未确认发布均 fail-closed。
- 外部 LLM 调用 0；真实数据、个人信息、生产凭据、生产权限、远端业务写入、费用、正式发布和赛事提交均为 0。

## 完整命令与退出码

机器可读执行账本位于 `environment/execution-ledger.json`。核心执行包括：

```text
PYTHONPATH=<task-deps>:<isolated-source> python3 -m pytest backend/tests/test_candidate_passport_v1.py -q
python3 scripts/run_synthetic_uat.py --output-dir . --run-index 1
python3 scripts/run_synthetic_uat.py --output-dir . --run-index 2
python3 scripts/run_synthetic_uat.py --output-dir . --run-index 3
python3 scripts/run_synthetic_uat.py --output-dir . --finalize
```

以上 M3 pytest 三轮、M4 三轮及 finalize 均 exit 0。原始日志位于 `logs/`。
`scripts/verify_artifact.py` 对场景数、枚举、三轮哈希、确定性结果、签名确认、两个权限标志、失败样本、输入哈希、凭据不落盘和零外部调用执行 16 项自检，结果见 `results/artifact-verification.json`，16/16 `PASS`。

## 限制

- `NOT_RUN_ENV`：真实非专业用户、真实企业文件、生产签发端点、Docker、实时数据库/迁移、正式账本写入、正式护照发布和赛事提交。
- 本轮程序执行时间不是用户任务耗时；不存在真实用户完成率、求助次数或用户原话。
- 平台 checkout 的 Git 元数据限制未伪装为 PASS，不影响已验收 V1.0.3 归档字节和本地场景重放，但独立复核应保留该限制。

## 责任分工

- 主责执行人：用户研究与赛事交付经理。
- 独立复核人：模型评测与质量保证工程师。
- 决策人：项目 Owner 代理｜需求澄清与决策中枢。

## 边界表达

已完成工程正确性、模型候选质量和基础可用性验证，尚未完成真实企业产业场景验证。

## 回滚

精确步骤见 `rollback.md`。删除任务专用隔离副本和候选输出即可；归档保留 manifest、哈希、日志、失败样本、verdict 和回滚记录，且不触碰 M1—M3 冻结证据或远端基线。
