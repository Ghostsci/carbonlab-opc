# CarbonLab OPC 运行手册

## 1. 推荐环境

- Docker Desktop 28+；
- Docker Compose v2；
- 本地空闲端口：5173、8000；
- 如不用 Docker：Python 3.12、Node 22、PostgreSQL 16。

## 2. 首次安装

```bash
git clone https://github.com/Ghostsci/carbonlab-opc.git
cd carbonlab-opc
cp .env.example .env
```

编辑 `.env`：

- 设置数据库密码；
- 设置长随机 `JWT_SECRET`；
- 需要调用模型时再填写 LLM Provider；
- 不要把 `.env` 提交到 Git。

## 3. Docker 启动

```bash
docker compose up --build
```

后端启动命令会先执行：

```bash
alembic -c backend/alembic.ini upgrade head
```

打开：

- `http://localhost:5173`
- `http://localhost:8000/docs`
- `http://localhost:8000/api/health`

## 4. 仅验证数据库迁移

```bash
docker compose run --rm backend alembic -c backend/alembic.ini upgrade head
```

查看当前版本：

```bash
docker compose run --rm backend alembic -c backend/alembic.ini current
```

## 5. 创建合成演示数据

```bash
CARBONLAB_DEMO_PASSWORD='<仅本地使用的密码>' \
docker compose run --rm -e CARBONLAB_DEMO_PASSWORD backend \
python -m scripts.seed_passport_demo
```

演示邮箱：`demo@huasheng-steel.com`。

脚本是幂等的，可以重复运行；它创建一条故意不完整路径和一条完整参考路径。所有内容均为 DEMO ONLY。

## 6. 本地非 Docker 启动

后端：

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
alembic -c backend/alembic.ini upgrade head
uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

前端（另一个终端）：

```bash
cd frontend
npm ci
npm run dev
```

## 7. 测试

```bash
python3 -m pytest -q backend/tests
```

```bash
cd frontend
npm ci
npm run build
npm run lint
npm audit --omit=dev
```

## 8. 生成合成数据集

```bash
python3 scripts/generate_factory_validation_dataset.py
```

不要覆盖已冻结数据。当前新仓库没有有效资格锁，正式冻结必须经过人类批准并形成单独提交和标签。

## 9. 运行模型一致性测试

前提：人类批准 Provider、模型和数据集；Key 只在当前终端环境提供。

```bash
python3 scripts/run_llm_conformance.py --help
```

在没有 `validation/QUALIFICATION_LOCK.json` 时，不得生成或宣称正式资格结论。

## 10. 常见故障

### 端口已占用

停止占用 5173/8000 的旧服务，或修改 Compose 端口映射。不要同时启动旧项目和新项目的同端口服务。

### 登录提示来源不允许

检查 `.env` 的 `CORS_ALLOWED_ORIGINS` 是否包含实际前端地址，然后重启后端。

### 数据库连接失败

```bash
docker compose ps
docker compose logs db
docker compose logs backend
```

确认 `DATABASE_URL` 的用户名、密码、主机 `db` 和数据库名一致。

### 上传后没有 AI 结果

- 先确认规则解析是否已经得到候选；
- 外部模型需要 `LLM_API_BASE`、`LLM_API_KEY`、`LLM_MODEL`；
- 无模型配置时，不要把空结果解释为系统已验证失败。

### 模型资格检查失败

当前预期状态就是“无有效资格锁”。先读 `validation/MODEL_BASELINE_REGISTRY.json` 和 `docs/handoff/opc-platform-takeover.md`，不要复制旧标签伪造通过。

## 11. 清理和重置

停止容器：

```bash
docker compose down
```

删除数据库卷和上传卷：

```bash
docker compose down -v
```

删除本地 Python/前端缓存：

```bash
rm -rf .pytest_cache backend/**/__pycache__ frontend/node_modules frontend/dist
```

## 12. 生产边界

本手册用于本地开发和赛事复现。生产上线前还需要独立完成域名、HTTPS、备份、密钥管理、监控、容灾和真实数据协议；这些不属于本次迁移交付。
