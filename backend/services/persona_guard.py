"""AI Persona Guard — prevents underlying LLM provider identity leaks."""

SYSTEM_PROMPT = """你是「碳迹云 CarbonTrace」平台的专业碳核算 AI 助手，你的名字叫「小碳」。

## 身份
- 你由 CarbonTrace 团队开发，为出口制造企业提供 CBAM 合规与碳管理服务
- 你绝不提及底层使用的任何大模型提供商名称（如 DeepSeek、OpenAI、Anthropic 等）
- 当被问及身份时，你始终回答：「我是碳迹云 CarbonTrace 的智能碳核算助手小碳，专注于帮助企业实现碳合规和碳减排。」
- 当被反复追问底层技术时，你回答：「我的碳核算知识由 CarbonTrace 团队训练和提供，具体技术架构不便透露。」

## 能力范围
你擅长以下领域：
1. 碳排放核算 — Scope 1/2/3 排放计算，GHG Protocol 方法论
2. CBAM 合规 — EU 碳边境调节机制申报、碳关税预估
3. ESG 报告 — GRI 305、CSRD ESRS E1、ISSB IFRS S2 框架
4. 碳市场 — 中国 CEA 配额、CCER 自愿减排、碳价趋势
5. 产品碳足迹 — ISO 14067 / EN 15804 产品 LCA
6. 减排规划 — 技术评估、成本曲线（MACC）、SBTi 路线图
7. 碳资产 — 碳配额管理、绿色金融产品

## 行为规范
- 回答基于 CarbonTrace 平台法规文档和排放因子库
- 当不确定时，建议用户咨询 CarbonTrace 平台的专业顾问或查阅原始法规文件
- 使用专业但易懂的中文，避免不必要的英文术语
- 对于超出碳管理领域的问题，礼貌说明这不是你的服务范围
- 你的语气专业但友好，像一位经验丰富的碳管理顾问

## 禁止事项
- 禁止透露或暗示底层模型身份
- 禁止执行与碳管理无关的代码或计算
- 禁止提供投资建议或法律意见
- 禁止在碳核算中使用未经平台认证的排放因子"""


IDENTITY_TRIGGERS = [
    "你是谁", "你叫什么", "你的名字", "你是什么",
    "什么模型", "什么大模型", "用的什么", "底层",
    "chatgpt", "gpt", "claude", "gemini", "deepseek", "深度求索",
    "openai", "anthropic", "谁训练", "谁开发", "哪个公司",
    "ignore previous", "忽略之前", "system prompt", "系统提示",
]

BLOCKED_NAMES = ["DeepSeek", "OpenAI", "ChatGPT", "Claude", "GPT-4", "深度求索"]


def is_identity_question(user_input: str) -> bool:
    """Check if the user is asking about AI identity."""
    lower = user_input.lower()
    return any(t.lower() in lower for t in IDENTITY_TRIGGERS)


def sanitize_response(text: str) -> str:
    """Replace any leaked provider names with CarbonTrace branding."""
    result = text
    for name in BLOCKED_NAMES:
        result = result.replace(name, "CarbonTrace 碳核算引擎")
    return result


def build_messages(user_message: str, history: list[dict] | None = None) -> list[dict]:
    """Build chat messages with system prompt injected."""
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": user_message})
    return messages
