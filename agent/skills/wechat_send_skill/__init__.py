"""
WechatSendSkill —— 按姓名发送微信消息
"""

from __future__ import annotations

from pathlib import Path

from agent.skills.base import BaseSkill
from agent.tools.builtin.wechat_send_by_name import WechatSendByNameTool


class WechatSendSkill(BaseSkill):
    """根据接收人姓名发送微信消息或链接。"""

    name = "wechat_send"
    description = "根据姓名发送微信消息（支持文字与链接，message 与 url 至少一项）"
    skill_md_path = Path(__file__).parent / "SKILL.md"

    def get_tools(self) -> list:
        return [WechatSendByNameTool()]
