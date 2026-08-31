# 操作手册：独立重放 M4 合成验收

## 前提

1. 在一次性目录准备 `main@c4f0b5bab63572dd0b9722be7aa12293fc3fb2b8` 源码。
2. 对 `input-evidence/M3_MINIMUM_CLOSED_LOOP_V1.0.3_CORRECTED_CANONICAL.tar.gz` 复算 SHA-256，必须为 `60abf4fd50a1b1922f31958c4a50ec56330da5b251b1a761973295cd5b178d63`。
3. 审计 tar 成员路径后解包，运行包内 `sha256sum -c validation/m3_candidate_passport_v1/SHA256SUMS`。
4. 在一次性源码副本 dry-run 并应用 `M3_MINIMUM_CLOSED_LOOP_V1.0.3.patch`；比较补丁生成的四个文件与归档副本。
5. 将 `requirements-m4.txt` 安装到任务专用依赖目录，不写系统环境。

## 执行

在本归档根目录运行：

```text
python3 scripts/run_all.py \
  --source-root <一次性源码副本> \
  --deps-dir <任务专用依赖目录> \
  --artifact-root .
```

验收时检查：

- `results/replay-summary.json` 中 8 项均为 `PASS`；
- 三个 `run_sha256` 相同且 `semantic_consistency_rate` 为 `100%`；
- `logs/m3-pytest-replay-*.log` 三轮均为 `19 passed`；
- `sha256sum -c SHA256SUMS` 全部通过；
- `formal_write_allowed` 与 `publish_allowed` 在全部候选证据中均为 false；
- 没有使用外部 LLM、真实数据、生产权限或远端业务写入。

## 回滚

完成复核后删除一次性源码副本和任务专用依赖目录。不得反向修改远端基线或 M1—M3 冻结证据。
