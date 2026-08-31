# 零碳云 CarbonLab

**AI 原生制造企业碳数据提取、核算与可信护照系统**

> OPC 深化项目公开代码仓库。当前成熟度为 **V3 内部测试**：网页闭环和合成数据验证已经完成，但尚未进入真实企业试点，不替代法定核查或监管申报。

## 当前版本

- 最新分支：`main`
- 产品代码冻结：`219b7cc30b901750c8136495a7a45aba6cc21116`
- 产品标签：`zcy-standard-data-ledger-v1.0.1-20260831`
- 赛事平台最新交接说明：[`docs/competition/CARBONLAB_V3_PLATFORM_HANDOFF_20260831.md`](docs/competition/CARBONLAB_V3_PLATFORM_HANDOFF_20260831.md)

## 项目解决什么问题

制造企业的碳数据通常散落在电费单、生产台账、发票和表格中。CarbonLab 不让大模型直接决定正式结果，而是建立以下责任链：

```text
原始文件
→ AI 提取候选并定位证据
→ A-03 质检和风险提示
→ H-01 人工确认企业事实
→ 标准化数据台账
→ H-02 人工确认方法和因子
→ R-01 Decimal 确定性计算
→ A-04 护照编制
→ H-03 复核、冻结和发布
```

统一原则：**AI 提议，规则检查，人类确认，确定性计算，授权发布，全程留痕。**

## 当前可运行页面

- `/upload`：数字员工工作台；
- `/data-ledger`：标准化数据台账；
- `/calculations`：核算工作台；
- `/passports`：工厂碳数据护照；
- `/agent-ops`：数字员工治理与执行 Trace。

## 已实现能力

- PDF、CSV、XLSX 和文本类文件接入、哈希和证据存储；
- 字段候选提取、原始工作表/单元格/文本行定位；
- A-01 至 A-04 固定 Skill 数字员工和可查看执行 Trace；
- H-01 企业事实确认、H-02 因子确认、H-03 授权发布；
- 版本化碳数据本体与混合 RAG；
- ActivityData 追加式正式账本和标准化数据台账；
- Decimal、单位/basis 校验和确定性排放计算；
- 工厂碳数据护照的归集、复核、冻结、发布和重放；
- 租户/企业隔离、版本、哈希和审计记录；
- Mac Apple Silicon 与 Windows x64 离线演示包候选。

## V3 内部验证

- 12 份 XLSX × 50 条明细，共 600 条合成明细；
- 12/12 完成上传、提取、质检、确认和确定性计算；
- 缺失、负数、错误单位和多账期等异常被 fail-closed；
- 1000 行合成工作簿完成证据定位与闭环验证；
- 后端全量测试：`149 passed`；
- 前端 production build：通过；
- Mac arm64 离线环境实际运行通过；
- Windows amd64 镜像和离线包完成架构与完整性验证。

详细报告：

- [`validation/competition_batch_v2/VALIDATION_RESULTS.md`](validation/competition_batch_v2/VALIDATION_RESULTS.md)
- [`docs/competition/MINIMUM_DEMO_DELIVERY_REPORT_20260821.md`](docs/competition/MINIMUM_DEMO_DELIVERY_REPORT_20260821.md)
- [`docs/competition/CARBONLAB_V3_PLATFORM_HANDOFF_20260831.md`](docs/competition/CARBONLAB_V3_PLATFORM_HANDOFF_20260831.md)

## 尚未完成或不得宣称

- 尚未使用真实企业生产资料完成试点；
- 尚未完成法定核查、监管申报或第三方认证；
- 尚未证明所有供电公司、ERP、SAP、MES 版式均可识别；
- 扫描图片型票据 OCR 不属于当前离线 Demo 稳定范围；
- 不提供碳交易、绿证撮合、绿色金融或自动报关；
- 合成测试结果不得写成客户效果、收入或企业反馈。

## 技术栈

- 前端：React、TypeScript、Vite、Tailwind CSS；
- 后端：Python、FastAPI、Pydantic、SQLAlchemy；
- 数据库：PostgreSQL、Alembic；
- AI：OpenAI-compatible Provider、固定 Skill、本体与混合 RAG；
- 测试：Pytest、TypeScript build、ESLint；
- 交付：Docker Compose、跨架构离线镜像。

## 本地运行

```bash
cp .env.example .env
# 配置本地数据库密码和 JWT_SECRET；核心离线演示不需要外部 LLM Key
docker compose up --build
```

访问：

- 前端：`http://localhost:5173`
- 后端文档：`http://localhost:8000/docs`
- 健康检查：`http://localhost:8000/api/health`

不要提交 `.env`、真实 API Key、真实企业文件或个人信息。

## 当前结论

本仓库证明的是：**最小碳数据工作流能够在合成数据和受控环境中运行、阻断、重放和追溯。**

下一步是非项目成员可用性测试，以及使用脱敏真实工厂资料开展人工专家与系统并行的 V4 影子试用。
