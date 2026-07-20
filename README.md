# 零碳云 CarbonLab

**AI 原生制造企业碳数据提取、核算与可信护照系统**

> OPC 复赛深化阶段独立仓库。当前是可运行的 P0 候选版本，主要使用合成数据；不代表真实企业试点完成，也不替代法定核查。

## 1. 项目解决什么问题

制造企业的碳数据通常散落在电费单、生产台账、发票和表格中。真正困难的不是“让 AI 读一个 PDF”，而是把每一个进入正式核算的数字都回答清楚：

1. 数字来自哪份原始文件、哪一段或哪个单元格；
2. AI 提取错了时，谁确认、修改或拒绝；
3. 单位、规则和计算是否可以确定性重放；
4. 对外分享时，接收方看到的是哪个冻结版本。

CarbonLab 把这条链做成“工厂碳数据护照”：AI 负责提出候选，人负责确认，规则引擎负责计算，系统负责保留证据和版本。

## 2. 本轮最小闭环

```text
原始文件接入
→ 文件分类
→ AI 候选字段提取
→ 字段级证据关联
→ 人工确认 / 修改 / 拒绝
→ 确定性单位校验与计算
→ 证据留存与结果重放
→ 版本冻结与发布
→ 工厂碳数据护照展示、追溯和授权共享
```

## 3. 已实现能力

- PDF、CSV、XLSX 和文本类文件接入、哈希与处理状态；
- OpenAI-compatible 模型封装和结构化候选提取；
- 字段值、证据原文及位置的验证契约；
- 人工确认后写入正式活动数据的 API；
- Decimal 精确数值、单位/basis 校验和确定性计算；
- 租户、企业、原始文档、活动、结果和规则的来源链；
- 工厂/装置护照账户、快照、复核、冻结、发布、重放和最小授权共享；
- Candidate、Holdout、Adversarial 合成数据集和 Usability 样例；
- 可替换模型的一致性评测工具；
- 登录、文件接入与确认、护照展示三类最小前端页面。

## 4. 未完成或尚未验证

- 尚未完成真实制造企业试点；
- 尚未完成非专业用户正式可用性测试；
- 当前没有有效的“准入模型资格锁”，任何模型都不得被宣称已获生产准入；
- 历史 DeepSeek 报告仅用于审计回放，其登记状态明确为失效；
- 尚未完成方法学、数据集和模型准入的人类正式冻结；
- 不提供碳交易、绿证撮合、绿色金融、自动监管申报或法定核查替代。

## 5. AI 与人的边界

| 环节 | AI 可以做 | AI 不得做 | 人类责任 |
|---|---|---|---|
| 文件理解 | 分类、提候选、给置信度 | 把候选直接写正式账本 | 查看原文和候选 |
| 证据 | 标记页码/表格/段落 | 用无关引文支持字段 | 确认字段与证据匹配 |
| 数值 | 识别原始字符串 | 猜测缺失数值、改写精度 | 确认值、单位和原因 |
| 计算 | 解释计算含义 | 代替确定性引擎算正式结果 | 批准输入与规则 |
| 发布 | 生成摘要建议 | 冻结或发布护照 | 复核并执行发布 |

## 6. 技术栈

- 前端：React 19、TypeScript 6、Vite 8、Tailwind CSS；
- 后端：Python 3.12、FastAPI、Pydantic、SQLAlchemy；
- 数据库：PostgreSQL 16、Alembic；
- AI：OpenAI-compatible Provider，可替换模型；
- 测试：Pytest、TypeScript build、ESLint；
- 交付：Docker Compose。

## 7. 目录结构

```text
backend/                 FastAPI、领域服务、模型、迁移和测试
frontend/                登录、文件接入和护照页面
scripts/                 演示数据与模型验证脚本
validation/              数据集、契约、历史报告和验证规则
docs/architecture/       系统架构
docs/migration/          旧项目审查、清单和迁移报告
docs/handoff/            运行、状态和赛事平台接管说明
ai/memory-bank/          治理、方法、任务和阶段门记忆
```

## 8. 首次运行

### Docker Compose（推荐）

```bash
cp .env.example .env
# 修改 .env 中的数据库密码、JWT_SECRET；需要真实模型时再填写 LLM 配置
docker compose up --build
```

访问：

- 前端：`http://localhost:5173`
- 后端文档：`http://localhost:8000/docs`
- 健康检查：`http://localhost:8000/api/health`

停止：

```bash
docker compose down
```

彻底重置本地数据：

```bash
docker compose down -v
```

### 创建合成演示数据

演示密码必须由本地环境提供，不写入仓库：

```bash
CARBONLAB_DEMO_PASSWORD='<仅本地使用的密码>' \
docker compose run --rm -e CARBONLAB_DEMO_PASSWORD backend \
python -m scripts.seed_passport_demo
```

演示邮箱为 `demo@huasheng-steel.com`；所有页面和数据均标记为 DEMO ONLY。

## 9. 测试

后端：

```bash
python3 -m pytest -q backend/tests
```

前端：

```bash
cd frontend
npm ci
npm run build
npm run lint
```

数据库迁移：

```bash
docker compose run --rm backend alembic -c backend/alembic.ini upgrade head
```

实际迁移验证结果见 `docs/migration/migration-report.md`。

## 10. 环境变量

复制 `.env.example` 后填写。核心变量：

- `DATABASE_URL`
- `JWT_SECRET`
- `CORS_ALLOWED_ORIGINS`
- `STORAGE_BACKEND`
- `LLM_API_BASE`
- `LLM_API_KEY`
- `LLM_MODEL`
- `CARBONLAB_DEMO_PASSWORD`（只在创建本地演示账号时临时提供）

不要提交 `.env`、真实 Key、真实企业文件或个人信息。

## 11. 当前成果边界

本仓库证明的是：最小业务链能够在合成数据上运行、测试和重放。它没有证明模型已经适用于所有工厂文件，也没有证明结果获得监管或第三方核查认可。

## 12. 交接入口

赛事平台按顺序读取：

1. `docs/handoff/opc-platform-takeover.md`
2. `docs/handoff/project-handoff.md`
3. `docs/handoff/feature-status-matrix.md`
4. `docs/handoff/runbook.md`
5. `ai/memory-bank/tasks/master-plan.md`
6. `ai/memory-bank/tasks/week-01.md`

详细迁移来源和取舍见 `docs/migration/`。
