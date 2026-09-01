from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from backend.state import AppState


WEB_RESEARCH_HINTS = (
    "最新", "今天", "现在", "新闻", "价格", "天气", "搜索", "搜一下", "查一下", "联网",
    "官网", "链接", "引用", "来源", "比较", "推荐", "航班", "酒店", "法律", "医疗",
    "金融", "股票", "汇率", "政策", "发布",
)

BROWSER_ACTION_HINTS = (
    "浏览器", "网页", "打开网页", "打开网站", "访问", "进入", "点击", "截图", "截屏",
    "表单", "填写", "提交", "登录", "登出", "滚动", "翻页", "上传",
)

FILE_HINTS = (
    "文件", "附件", "上传", "pdf", "word", "excel", "csv", "表格", "图片", "截图",
    "压缩包", "目录", "文档", "合同", "简历",
)

HIGH_STAKES_HINTS = ("医疗", "用药", "法律", "合同", "诉讼", "投资", "理财", "税务", "保险")
DESTRUCTIVE_HINTS = ("删除", "清空", "覆盖", "移动", "改名", "发送", "发给", "提交", "支付")


SKILL_KEYWORDS: dict[str, tuple[str, ...]] = {
    "browser_skill": ("浏览器", "网页", "打开", "点击", "截图", "登录"),
    "code_runner_skill": ("代码", "运行", "脚本", "python", "javascript", "报错"),
    "office-file-analyst": ("office", "word", "excel", "ppt", "表格", "文档", "合同"),
    "pdf2zh_translator": ("pdf", "翻译", "论文"),
    "word_to_pdf_skill": ("word转pdf", "docx", "转成pdf"),
    "text_to_image_skill": ("画图", "生成图片", "海报", "插画"),
    "wechat_send_skill": ("微信", "发消息"),
    "lark": ("飞书", "lark", "多维表格", "云文档", "日历"),
    "stock_quote_skill": ("股票", "行情", "股价", "基金"),
    "archive_download_skill": ("压缩包", "zip", "下载", "打包"),
    "knowledge_base": ("知识库", "文档库", "资料库", "已上传", "索引", "引用来源"),
    "skill_creator": ("创建技能", "写技能", "设计技能", "skill", "SKILL.md", "agents/openai.yaml"),
}


@dataclass
class IntentRoute:
    intent: str
    recommended_skills: list[str]
    requires_network: bool
    prefers_web_search: bool
    prefers_browser_interaction: bool
    requires_files: bool
    requires_permission: bool
    risk_level: str
    verification_policy: str
    reasons: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "intent": self.intent,
            "recommended_skills": self.recommended_skills,
            "requires_network": self.requires_network,
            "prefers_web_search": self.prefers_web_search,
            "prefers_browser_interaction": self.prefers_browser_interaction,
            "requires_files": self.requires_files,
            "requires_permission": self.requires_permission,
            "risk_level": self.risk_level,
            "verification_policy": self.verification_policy,
            "reasons": self.reasons,
        }


def _latest_user_text(messages: list[dict[str, Any]]) -> str:
    for message in reversed(messages):
        if message.get("role") != "user":
            continue
        content = message.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = []
            for part in content:
                if isinstance(part, dict):
                    text = part.get("text") or part.get("content")
                    if isinstance(text, str):
                        parts.append(text)
            return "\n".join(parts)
    return ""


def _has_uploads(messages: list[dict[str, Any]]) -> bool:
    for message in messages:
        if message.get("experimental_attachments") or message.get("attachments"):
            return True
        content = message.get("content")
        if isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and part.get("type") in {"image_url", "file"}:
                    return True
    return False


def classify_intent(messages: list[dict[str, Any]], state: AppState) -> IntentRoute:
    text = _latest_user_text(messages)
    lower = text.lower()
    reasons: list[str] = []

    prefers_web_search = any(hint in text for hint in WEB_RESEARCH_HINTS)
    prefers_browser_interaction = any(hint in text for hint in BROWSER_ACTION_HINTS)
    requires_network = prefers_web_search or prefers_browser_interaction
    if prefers_web_search:
        reasons.append("用户问题更像信息检索，优先使用 web_search 获取来源和最新信息")
    if prefers_browser_interaction:
        reasons.append("用户问题包含页面交互动作，适合使用 browser_skill 操作网页")

    requires_files = _has_uploads(messages) or any(hint in lower or hint in text for hint in FILE_HINTS)
    if requires_files:
        reasons.append("用户提到了文件/附件/图片/表格等材料")

    high_stakes = any(hint in text for hint in HIGH_STAKES_HINTS)
    destructive = any(hint in text for hint in DESTRUCTIVE_HINTS)
    requires_permission = destructive or bool(re.search(r"\b(send|delete|remove|rm|pay|submit)\b", lower))
    if requires_permission:
        reasons.append("任务可能修改外部状态、发送信息或删除/覆盖内容")

    recommended: list[str] = []
    active = set(state.skill_registry.active_names())
    for skill_name, keywords in SKILL_KEYWORDS.items():
        if skill_name in active and any(keyword in lower or keyword in text for keyword in keywords):
            recommended.append(skill_name)

    if prefers_browser_interaction and "browser_skill" in active and "browser_skill" not in recommended:
        recommended.append("browser_skill")
    if requires_files and "office-file-analyst" in active and "office-file-analyst" not in recommended:
        recommended.append("office-file-analyst")

    if high_stakes:
        risk_level = "high"
    elif requires_permission:
        risk_level = "medium"
    else:
        risk_level = "low"

    if high_stakes or prefers_web_search:
        verification_policy = (
            "回答必须给出来源链接、检索或资料日期，并区分事实、推断和建议；"
            "高风险主题必须提醒用户咨询专业人士。"
        )
    elif requires_files:
        verification_policy = "回答应引用所依据的文件名、页码/表格/片段位置；不确定时说明缺少哪些材料。"
    else:
        verification_policy = "回答应说明依据和不确定性；不要编造来源。"

    if re.search(r"(总结|整理|归纳|摘要)", text):
        intent = "summarize"
    elif re.search(r"(安排|提醒|每天|每周|定时|计划|待办)", text):
        intent = "workflow"
    elif requires_network:
        intent = "research"
    elif requires_files:
        intent = "file_analysis"
    elif requires_permission:
        intent = "external_action"
    else:
        intent = "general_chat"

    return IntentRoute(
        intent=intent,
        recommended_skills=recommended[:5],
        requires_network=requires_network,
        prefers_web_search=prefers_web_search,
        prefers_browser_interaction=prefers_browser_interaction,
        requires_files=requires_files,
        requires_permission=requires_permission,
        risk_level=risk_level,
        verification_policy=verification_policy,
        reasons=reasons,
    )


def format_route_for_prompt(route: IntentRoute) -> str:
    skills = ", ".join(route.recommended_skills) if route.recommended_skills else "无明确推荐"
    reasons = "; ".join(route.reasons) if route.reasons else "普通对话，无特殊风险线索"
    return (
        "Intent routing metadata:\n"
        f"- intent: {route.intent}\n"
        f"- recommended skills: {skills}\n"
        f"- requires network: {route.requires_network}\n"
        f"- prefer web search: {route.prefers_web_search}\n"
        f"- prefer browser interaction: {route.prefers_browser_interaction}\n"
        f"- requires files: {route.requires_files}\n"
        f"- requires permission: {route.requires_permission}\n"
        f"- risk level: {route.risk_level}\n"
        f"- reasons: {reasons}\n"
        f"- verification policy: {route.verification_policy}\n"
        "Use this metadata to choose tools conservatively. Ask for confirmation before irreversible or external actions."
    )
