# 迁移验证基线

执行日期：2026-07-20。

| 检查 | 结果 |
|---|---|
| 后端迁移范围测试 | 76 passed |
| 前端生产构建 | 通过 |
| 前端 lint | 0 errors / 1 warning |
| 前端生产依赖审计 | 0 vulnerabilities |
| Docker Compose 配置 | 通过 |
| 后端镜像构建 | 通过 |
| PostgreSQL 16 Alembic 001→032 | 通过 |
| 容器健康检查 | HTTP 200 / database ok |
| 合成护照种子 | 通过 |

这些结果只证明迁移后的工程基线可运行，不等同于真实企业、正式模型或法定方法学验证。
