"""对话 Agent —— 理解+决策一体（轻量模型 deepseek-chat）"""
import re
from datetime import datetime
from agents.base import get_utility_llm
from core.logger import get_logger

logger = get_logger(__name__)

# ═══════════════════════════════════════════════════
# 归一化匹配基础设施
# ═══════════════════════════════════════════════════

# 技能别名归一化表
SKILL_ALIASES = {
    "react.js": "react", "reactjs": "react",
    "node.js": "nodejs", "node": "nodejs",
    "kubernetes": "k8s", "k8s": "kubernetes",
    "postgresql": "postgres", "postgres": "postgresql",
    "golang": "go", "go语言": "go",
    "mysql数据库": "mysql", "python3": "python", "python语言": "python",
    "javascript": "js", "js": "javascript",
    "typescript": "ts", "ts": "typescript",
    "vue.js": "vue", "vuejs": "vue",
    "angular.js": "angular", "angularjs": "angular",
}

# 停用词（不是技能，但会被正则匹配到）
STOP_WORDS = {
    'the', 'and', 'for', 'with', 'from', 'this', 'that', 'are', 'was', 'not',
    'can', 'has', 'have', 'had', 'but', 'all', 'any', 'each', 'every',
    '可以', '能够', '用户', '问题', '分析', '数据', '系统', '技术', '开发',
    '工作', '需要', '通过', '使用', '支持', '提供', '进行', '实现', '以及',
    '或者', '相关', '包括', '根据', '目前', '基于', '其中', '不同', '比较',
    '了解', '熟悉', '掌握', '具备', '优先', '经验', '能力', '岗位', '招聘',
    '要求', '职责', '任职', '薪资', '待遇', '公司', '团队', '项目', '产品',
}

def normalize_entity(text: str) -> str:
    """归一化实体：小写、去中文后缀、查别名"""
    t = text.lower().strip()
    for suffix in ['框架', '数据库', '语言', '工具', '平台', '引擎', '服务器', '中间件']:
        if t.endswith(suffix) and len(t) > len(suffix):
            t = t[:-len(suffix)]
    return SKILL_ALIASES.get(t, t)

def build_known_set(knowledge: list[str]) -> set:
    """从 knowledge 构建归一化的已知实体集合"""
    known = set()
    for k in knowledge:
        for token in re.findall(r'[A-Za-z+#.0-9]{2,}|[一-鿿]{2,8}', k):
            normalized = normalize_entity(token)
            known.add(normalized)
            known.add(token.lower())
    return known

def extract_entities(text: str) -> set:
    """从文本中提取所有疑似技术实体（不仅限粗体），过滤停用词"""
    entities = set()
    for match in re.finditer(r'[A-Za-z+#.][A-Za-z+#.0-9]{1,}|[一-鿿]{2,8}', text):
        token = match.group().strip()
        if len(token) < 2:
            continue
        lower = token.lower()
        if lower in STOP_WORDS:
            continue
        if lower in {normalize_entity(s) for s in STOP_WORDS}:
            continue
        entities.add(lower)
    return entities

SYSTEM_PROMPT = """你是求职助手 JobLab，帮助用户分析岗位技能需求、规划职业发展。

## 核心原则
- 当前日期: {today}
- 所有涉及时间的回答必须以这个日期为准
- 不确定时**追问用户细节**，不要猜测也不要撒手不管
- 例如用户只说了"我想找工作"，追问他想找什么方向、在哪个城市、有什么技能背景
- 例如用户问薪资，如果JD中没有薪资信息，诚实告知并建议他搜索具体薪资数据

## 回复协议
回复中用标记指定动作（普通对话不写）：
- [SEARCH:关键词] — 需要从知识库检索数据，包括：用户问具体技术细节、要求提供链接/URL/招聘入口/投递渠道、查询公司信息等
- [ANALYZE:岗位名] — 需要搜索最新招聘市场分析技能（用户确认要分析某个岗位，或知识库无结果时主动建议）
- [RESEARCH:目标] — 用户要做求职研究（含"研究/调研/全面分析/帮我看看"等），需拆解为技能+薪资+面试等多维度并行调研
- 普通对话（问候/闲聊/概念解释）不写标记
- **重要**：即使用户问的问题知识库可能没有答案，也必须先尝试 [SEARCH:]，搜索无结果后再告知用户并建议 [ANALYZE:]

## 回答规则
1. 当上下文包含技能排名时，列出 Top 技能和出现频次
2. 当上下文包含 JD 片段时，引用来源（公司名）并**必须附上 `链接:` 字段中的 URL**，让用户可直接点击查看原始招聘信息
3. 当用户明确要链接/网址/投递入口时，优先从上下文的 `链接:` 行提取并列出
4. 回答简洁，最多 500 字
5. 用户追问确认"好的/可以/帮我分析"时，参考上一轮的岗位名执行分析
6. 当上下文包含编号来源（如 [1] [2]）时，在相关陈述后必须标注来源编号，例如："Python 是最热门的技能 [1]"
7. 不确定来源的信息不要编造，可以标注 [?]
"""


class ChatAgent:

    @staticmethod
    def verify_citations(response: str, knowledge: list[str]) -> tuple[str, list]:
        """
        全文实体溯源校验。
        - 从回复中提取所有技术实体（不仅限粗体）
        - 归一化后与 knowledge 对照
        - 未验证的实体用 ~~删除线~~ 标记
        - 返回 (修正后的回复, 未验证实体列表)
        """
        if not knowledge:
            return response, []

        known = build_known_set(knowledge)

        # 提取回复中所有技术实体
        claimed = extract_entities(response)

        # 归一化后对比
        unverified = []
        for entity in claimed:
            normalized = normalize_entity(entity)
            if normalized not in known and entity not in known:
                unverified.append(entity)

        if not unverified:
            return response, []

        logger.info(f"溯源校验: {len(unverified)} 个未验证实体: {', '.join(unverified[:8])}")

        # 在回复中用 ~~删除线~~ 标记未验证实体（最多标记每个3次）
        marked = response
        for entity in sorted(unverified, key=len, reverse=True):  # 长的先标记，避免子串误伤
            pattern = re.compile(
                r'(?<![A-Za-z])' + re.escape(entity) + r'(?![A-Za-z])',
                re.IGNORECASE
            )
            marked = pattern.sub(f'~~{entity}~~', marked, count=3)

        # 末尾汇总提示
        warning_items = ', '.join(f'`{e}`' for e in unverified[:5])
        marked += f'\n\n> ⚠️ 以下内容未在数据来源中找到依据，仅供参考: {warning_items}'

        return marked, unverified

    @staticmethod
    def apply_corrections(response: str, unverified: list) -> str:
        """对已标记 ~~删除线~~ 的回复做最终清理，确保格式正确"""
        if not unverified:
            return response
        return response  # 标记已在 verify_citations 中完成

    @staticmethod
    def parse(response: str) -> tuple[str, str]:
        """
        解析 ChatAgent 回复中的标记（检查全部行）。
        返回 (action, arg)，action 为 "search"/"analyze"/"chat"
        """
        for line in response.split("\n"):
            line = line.strip()
            if line.startswith("[SEARCH:") and line.endswith("]"):
                return "search", line[9:-1]
            if line.startswith("[ANALYZE:") and line.endswith("]"):
                return "analyze", line[10:-1]
            if line.startswith("[RESEARCH:") and line.endswith("]"):
                return "research", line[11:-1]
        return "chat", ""

    def reply(self, user_message: str, context: str) -> tuple[str, dict]:
        weekdays = ["周一","周二","周三","周四","周五","周六","周日"]
        now = datetime.now()
        today = now.strftime("%Y年%m月%d日") + " " + weekdays[now.weekday()]
        prompt = SYSTEM_PROMPT.format(today=today)
        prompt += f"\n\n{context}\n\n用户：{user_message}"
        msg = get_utility_llm().invoke(prompt)
        response = msg.content.strip()
        usage = msg.response_metadata.get("token_usage", {})
        logger.debug(f"ChatAgent 回复: {len(response)} 字")
        return response, {"prompt_tokens": usage.get("prompt_tokens", 0), "completion_tokens": usage.get("completion_tokens", 0)}
