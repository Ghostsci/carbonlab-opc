# 迁移清单

## 1. 清单规则

- 来源基准：`/Users/Ghost/Documents/carbon-footprint-agent-product` @ `ad5a5eb9b421879fa633042cb87d040892d99d7b`。
- 新仓库采用干净历史，不复制旧 `.git`。
- “迁移”只表示文件进入候选仓库，不表示功能已经通过验证。
- 最终逐文件清单由 `docs/migration/migrated-files.txt` 固化；本表记录迁移决策和处理方式。

## 2. 计划迁移内容

| 原文件或目录 | 新位置 | 是否迁移 | 迁移原因 | 依赖 | 处理方式 | 验证结果 |
|---|---|---:|---|---|---|---|
| `backend/api/auth.py` | 同路径 | 是 | 登录、当前用户和人类审批身份 | JWT、用户、租户 | 直接复制，迁移后测试 | 待验证 |
| `backend/api/health.py` | 同路径 | 是 | 运行状态检查 | 数据库 | 直接复制 | 待验证 |
| `backend/api/upload.py` | 同路径 | 是 | 文件接入和人工确认入口 | 文档、活动入账、存储 | 直接复制并检查边界 | 待验证 |
| `backend/api/ai.py` | 同路径 | 是 | 文档理解和候选提取 | AI 封装、知识/因子服务 | 直接复制并限制为候选 | 待验证 |
| `backend/api/passports.py` | 同路径 | 是 | 护照账户、版本、追溯和共享 | 护照服务、权限 | 直接复制 | 待验证 |
| 上述 API 的 Python 依赖闭包 | 原相对路径 | 是 | 维持既有技术栈和领域不变量 | 52 个核心源码文件 | 依赖图筛选后复制 | 待验证 |
| `backend/main.py` | 同路径 | 是 | FastAPI 入口 | 五个保留路由 | 重建最小入口，不复制无关路由 | 待验证 |
| `backend/alembic/` | 同路径 | 是 | 护照表依赖既有 schema 链 | PostgreSQL、Alembic | 排除缓存，适配模型注册 | 待验证 |
| `backend/tests/` 相关测试 | 同路径 | 部分 | 核心流程回归 | Pytest | 只复制护照、上传、Quantity、LLM 验证测试及必要夹具 | 待验证 |
| `backend/validation/*.py` | 同路径 | 是 | 合成工厂数据、盲测和模型比较 | Pydantic、Provider | 排除缓存和生成报告 | 待验证 |
| `scripts/seed_passport_demo.py` | 同路径 | 是 | 创建可演示的模拟护照 | 核心模型/服务 | 复制并清理本地配置 | 待验证 |
| `scripts/generate_factory_validation_dataset.py` | 同路径 | 是 | 生成随机结构化工厂数据 | validation | 直接复制 | 待验证 |
| `scripts/run_llm_conformance.py` | 同路径 | 是 | 运行模型一致性验证 | Provider、数据集 | 复制；不得内置 Key | 待验证 |
| `scripts/compare_llm_conformance.py` | 同路径 | 是 | 比较基线/替代模型 | 验证报告 | 直接复制 | 待验证 |
| `frontend/src/pages/Login.tsx` | 同路径 | 是 | 身份入口 | AuthContext | 直接复制 | 待验证 |
| `frontend/src/pages/Upload.tsx` | 同路径 | 是 | 文件接入、候选查看和确认 | upload/ai API | 直接复制并核对 API | 待验证 |
| `frontend/src/pages/InstallationPassports.tsx` | 同路径 | 是 | 护照展示和追溯 | passports API | 直接复制 | 待验证 |
| 前端公共壳层和上下文 | 原相对路径 | 是 | 页面运行、鉴权、租户上下文 | React Router | 筛选复制并精简菜单 | 待验证 |
| `frontend/src/App.tsx` | 同路径 | 是 | 路由入口 | 三个页面 | 重建最小路由集合 | 待验证 |
| `frontend/package*.json`、构建配置 | 同路径 | 是 | 保持可安装和构建 | npm | 复制后去除未使用依赖（仅在验证安全时） | 待验证 |
| `.env.example` | 根目录 | 是 | 配置契约 | 前后端环境变量 | 重建，仅保留非敏感示例 | 待验证 |
| Dockerfile / Compose | 原相对位置 | 部分 | 本地可复现 | PostgreSQL、前后端 | 只保留开发/基础运行所需并注明非生产 | 待验证 |
| 护照与 LLM 验证技术文档 | `docs/validation/`、`docs/architecture/` | 部分 | 交接方法和边界 | 无 | 只迁移当前有效版本，清除旧绝对路径 | 待验证 |

## 3. 需要修改路径或配置的内容

1. FastAPI 入口只注册 health、auth、upload、ai、passports；
2. 前端只保留 `/login`、`/upload`、`/passports` 和默认跳转；
3. API、数据库、JWT、存储和模型 Provider 均通过环境变量配置；
4. 上传目录使用仓库相对路径或显式环境变量；
5. Alembic 模型注册移除未迁移业务模型；
6. 任何旧项目绝对路径仅可出现在本迁移审计的来源记录中，不得进入运行配置。

## 4. 需要拆分的模块

| 模块 | 拆分原因 | 本轮保留 |
|---|---|---|
| `backend/main.py` | 原入口暴露 30 余个旧平台路由 | 5 个核心路由和必要中间件 |
| `frontend/src/App.tsx` | 原入口挂载大量非赛事页面 | 登录、文件接入、护照 |
| `frontend/src/components/Layout.tsx` | 原菜单反映完整旧平台 | 最小闭环导航 |
| `scripts/` | 含压力、运维和历史状态脚本 | 护照演示、合成数据、模型验证 |
| `docs/` | 含大量战略、审查和历史材料 | 架构、验证、迁移和交接资料 |

## 5. 明确不迁移

| 原内容 | 是否迁移 | 原因 |
|---|---:|---|
| 旧 `.git/` | 否 | 建立干净、可审计的新历史 |
| `competition/` | 否 | 未进入来源提交，属于临时赛事材料 |
| 碳市场/碳价/绿色金融/资产/减排模块 | 否 | 超出复赛最小闭环 |
| ERP、供应商门户、核查工作台、AgentOps 页面 | 否 | 超出本轮交付边界 |
| 小程序、营销页、展示原型 | 否 | 不是核心运行依赖 |
| 旧 PPT、截图、下载文件、私人笔记 | 否 | 非代码交接基线且存在隐私/陈旧风险 |
| 缓存、构建产物、上传文件、日志、本地数据库 | 否 | 不可复现或可能含敏感数据 |
| 真实 API Key、Token、密码和测试账号 | 否 | 安全要求禁止提交 |

## 6. 敏感信息处理

- 不复制任何 `.env`；
- 新建 `.env.example`，仅包含变量名和安全示例；
- 不复制历史生成报告和日志；
- 提交前扫描 `sk-`、`ghp_`、`github_pat_`、`AKIA`、私钥头、密码/Token/API Key/数据库连接模式；
- 发现 canary 或示例命中时，也必须确认不会被误认为真实凭据；
- 扫描结果写入 `docs/migration/migration-report.md`。

## 7. 待人工确认

1. GitHub 仓库由个人账号还是组织创建；
2. 仓库保持 private 还是公开；
3. 最终远程 URL；
4. 赛事平台账号和 8 名数字员工/6 个专项组的实际标识；
5. 真实企业数据接入审批；
6. 方法学冻结、数据冻结和模型准入决定。

上述事项不阻塞本地迁移和验证，但阻塞远程推送或正式赛事结论。
