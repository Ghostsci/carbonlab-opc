# 零碳云模型验证实验室

> 当前状态（2026-07-11）：字段级证据评分器正在独立复核，历史模型资格已失效；当前没有可进入人工影子的默认模型。

这套工具回答的不是“某个模型聪不聪明”，而是一个可执行问题：

> 在同一任务契约、同一数据集和同一门禁下，当前模型能否可靠地产生**待人工确认的候选数据**，并且更换模型后是否发生退化？

## 组成

- `llm/LLM_OPERATING_CONTRACT.md`：所有 Provider 都必须读取的操作手册；
- `llm/TASK_CATALOG.json`：允许和禁止的任务；
- `llm/schemas/`：严格、拒绝额外字段的输出 Schema；
- `datasets/synthetic_factory_v1/`：固定种子生成的 candidate / holdout / adversarial 场景；
- `RELEASE_GATES.json`：在查看模型结果前登记的门槛；
- `reports/`：不含原始回答和密钥的可提交报告；
- `runs/`：本机调试用原始模型回答，已被 Git 忽略。

## 为什么“先读操作手册”仍不等于不会出错

操作手册统一了任务语义，但不同模型仍可能在 Schema、证据定位、拒绝猜测和提示词注入上表现不同。因此可替换性来自三层，而不是一句 Prompt：

```text
同一操作契约
→ 同一严格 Schema
→ 同一成对资格测试 + 影子运行 + 可回滚版本
```

## 运行方式

密钥只放在 Git 忽略、权限为 `600` 的本机文件中，不能作为命令行参数：

```bash
set -a
source .secrets/deepseek.env
set +a

backend/.venv/bin/python scripts/run_llm_conformance.py \
  --splits candidate \
  --record-only
```

候选集只用于发现错误和改 Prompt。冻结契约后再运行：

```bash
backend/.venv/bin/python scripts/run_llm_conformance.py \
  --splits holdout adversarial
```

更换模型时，先在看结果前登记非劣效界值，再做成对比较：

```bash
backend/.venv/bin/python scripts/compare_llm_conformance.py \
  validation/reports/BASELINE.json \
  validation/reports/CANDIDATE.json \
  --margin 0.02 \
  --output validation/reports/COMPARISON.json
```

比较通过也只允许进入人工并行的影子阶段；不能自动写正式账本、发布护照或对外宣称法规核验通过。

## 结果解释

- **合成验证绿色**：说明已覆盖的文字场景、契约和适配器可以进入人工影子试验；
- **不代表**：真实 PDF/OCR、脏数据、法规适用性、客户接受、付费意愿或绝对零错误；
- **正式数值**：始终由 `Decimal` / `Quantity` 确定性内核计算；
- **正式动作**：始终由确定性门禁与有权限的人确认。
