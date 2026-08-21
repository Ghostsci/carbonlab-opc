# M3 合成本地候选确认契约 V1.0.3

运行输入契约只接受 `scenario_id + documents`，禁止携带或读取数据集 `truth/expected`。`static/static-v1` 必须从不可信文档生成输出，且输出只进入 `candidate`。逐字段值、单位、证据原文和期间通过程序语义绑定后，仍必须提交服务端认证边界签发的确认凭据；使用点强制校验签名、`passport_confirmation` 类型、`carbon-passport-confirmation` audience、expiry、actor 与授权 role。无令牌、伪造签名、错误 audience、过期身份和越权角色均失败关闭。

本候选闭环只允许 `candidate → rejected` 或 `candidate → calculated`。`calculated` 仍固定 `formal_write_allowed=false`、`publish_allowed=false`，不代表正式账本事实、模型启用或护照发布。

计算规则仅为合成测试冻结规则 `synthetic-electricity-rule-v1`：外购电 kWh × 0.500000 kgCO2e/kWh ÷ 1000，使用 Decimal 和单位引擎执行。

限制：本阶段实现签名凭据的验证边界，不新增生产数据库/API 的签发端点；生产接入时只能在真实用户认证和授权完成后由服务端签发短时确认凭据，签名密钥不得暴露给请求调用方。真实业务事实、正式方法学和正式证据规则仍待人类确认。
