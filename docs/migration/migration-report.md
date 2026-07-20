# CarbonLab OPC 迁移报告

## 1. 迁移结论

零碳云已从旧平台代码库中提取为独立的 OPC 最小闭环仓库。本次为干净迁移，不继承旧 Git 历史，不修改旧仓库，不新增复赛业务功能。

| 项目 | 结果 |
|---|---|
| 新仓库本地路径 | `/Users/Ghost/Documents/carbonlab-opc` |
| GitHub 远程 | `https://github.com/Ghostsci/carbonlab-opc` |
| 默认分支 | `main` |
| 远程可见性 | Private |
| 来源提交 | `ad5a5eb9b421879fa633042cb87d040892d99d7b` |
| 来源标签 | `zcy-p0-product-value-slice-20260714` |
| 旧历史 | 未复制 |
| 迁移状态 | 本地验证完成；GitHub `main` 分支已建立并完成首次推送 |

## 2. 实际迁移内容

### 2.1 后端

- auth、health、upload、ai、passports 五类 API；
- 文档解析、OCR、OpenAI-compatible 候选提取；
- 活动数据确认、精确单位、规则记录、CBAM 归集和 SEE；
- 工厂碳数据护照账户、快照、方法复核、发布、重放和共享；
- 核心模型、数据库和必要 Alembic 迁移链；
- 76 个迁移范围内的 Pytest 测试。

### 2.2 前端

- 登录；
- 文件接入、识别、候选查看和人工确认；
- 工厂碳数据护照、版本、追溯、重放和授权共享；
- 公共布局、鉴权上下文和构建配置。

### 2.3 验证和数据

- Candidate、Holdout、Adversarial 合成数据集；
- Usability/产品验收样例；
- 模型操作契约、Schema、评分器和报告工具；
- 历史模型报告、登记表和旧资格锁（均明确为当前失效，仅供回放）。

### 2.4 工程交付

- `.env.example`；
- Dockerfile 和 Docker Compose；
- README、系统架构、迁移、交接、运行和 OPC 接管文档；
- AI memory-bank 治理与任务目录。

## 3. 未迁移内容

- 碳市场、碳价、绿色金融、碳资产和收益分成；
- ERP、供应商门户、核查工作台、减排和 AgentOps 业务界面；
- 小程序、营销页、PPT、截图和私人笔记；
- `competition/` 未跟踪目录；
- 旧日志、缓存、构建产物、上传文件和本地数据库；
- 真实凭据、测试固定密码和真实企业数据；
- 旧仓库 Git 历史。

## 4. 迁移适配

1. FastAPI 入口由旧平台 30 余个业务路由缩小为 5 类核心路由；
2. AI API 只保留候选提取，不暴露旧知识问答和因子推荐表面；
3. 前端路由和菜单缩小为登录、文件接入、护照；
4. 数据库迁移 005 去除旧数据库名 `carbon_footprint` 的硬编码，改为当前连接数据库；
5. Docker 构建上下文包含 backend、scripts 和 validation，保证赛事复现；
6. 演示账号密码改为运行时环境变量，不写入仓库或终端输出；
7. 旧资格锁移入 `validation/history/`，新仓库不伪造旧 Git 标签；
8. 历史模型登记保持 `production_eligible=false`；
9. 删除与未迁移 dashboard overview API 对应的测试，不把额外业务路由迁回来；
10. 前端移除未使用依赖并升级 React Router，生产依赖审计为 0 个已知漏洞。

## 5. 实际验证结果

执行日期：2026-07-20。

| 检查 | 实际命令/方式 | 结果 |
|---|---|---|
| Python 导入 | 导入 `backend.models` 和 `backend.main` | 通过 |
| 后端测试 | `python3 -m pytest -q backend/tests` | 76 passed |
| 前端安装 | `npm ci` / `npm install` | 通过 |
| 前端构建 | `npm run build` | 通过 |
| 前端 lint | `npm run lint` | 0 errors / 1 warning |
| 前端生产依赖 | `npm audit --omit=dev` | 0 vulnerabilities |
| Compose 语法 | `docker compose config --quiet` | 通过 |
| 后端 Docker 构建 | `docker compose build backend` | 通过 |
| PostgreSQL 迁移 | PostgreSQL 16，Alembic 001→032 | 通过 |
| 容器内健康检查 | TestClient 调用 `/api/health` 并连接 PostgreSQL | 200 / database ok |
| 合成护照种子 | 容器内运行 `scripts.seed_passport_demo` | 通过，生成不完整和完整参考两条路径 |

未执行：

- 真实外部 LLM 调用：本次迁移不得产生正式比赛评测结果，且仓库无有效资格锁；
- 真实企业文件测试：尚未获得数据和人类批准；
- 非专业用户正式可用性测试：需要赛事阶段组织参与者；
- 生产部署、负载和高可用验证：超出本次迁移范围。

## 6. 基础敏感信息检查

- 未迁移 `.env`、私钥、真实 Token、真实 API Key；
- `.env.example` 仅保留变量名和不可用/本地示例；
- 固定演示密码已改为 `CARBONLAB_DEMO_PASSWORD` 运行时输入；
- `/Users/Ghost` 仅存在于迁移审计的“旧项目来源路径”记录，不存在于运行代码；
- `sk-`、`ghp_` 等文本命中来自扫描规则示例、测试 canary 或静态资源字节，不是可用凭据；
- 临时 `backend/.uploads/` 曾在本地测试中生成，已在推送前从提交历史移除并加入 `.gitignore`。

## 7. 已知问题

1. 当前没有有效模型资格锁，必须重新冻结后才能进行模型准入；
2. 前端 lint 有 1 条 Fast Refresh 结构警告，不影响构建；
3. Alembic 历史链仍会创建部分旧平台表，这是护照 schema 的历史依赖，不代表对应业务已迁移；
4. Docker Compose 是赛事复现和本地开发配置，不是生产高可用方案；
5. 真实企业数据、法定方法学和用户可用性尚未验证；
6. GitHub 仓库为 Private；赛事平台协作者和后续公开范围仍需由人类负责人决定。

## 8. 逐文件清单

最终提交文件列表见 `docs/migration/migrated-files.txt`。未迁移类别和原因见 `migration-manifest.md`。
