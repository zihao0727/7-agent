"""
浏览器自动化 Skill —— 类 Manus 网页抓取与交互能力

激活后向 Agent 提供以下工具：
  browser_navigate       导航到 URL
  browser_screenshot     截图
  browser_extract_text   提取文本
  browser_extract_attrs  提取 HTML 属性
  browser_extract_table  解析表格 → JSON/CSV
  browser_scroll         滚动页面
  browser_click          点击元素
  browser_extract_list   分页/无限滚动列表抓取
"""

from pathlib import Path

from agent.skills.base import BaseSkill
from agent.tools.base import BaseTool
from agent.tools.builtin.browser_tools import (
    BrowserClickTool,
    BrowserExtractAttrsTool,
    BrowserExtractListTool,
    BrowserExtractTableTool,
    BrowserExtractTextTool,
    BrowserNavigateTool,
    BrowserScreenshotTool,
    BrowserScrollTool,
)


class BrowserSkill(BaseSkill):
    name = "browser"
    description = (
        "浏览器自动化：导航网页、截图、提取文本/属性/表格、"
        "分页抓取与无限滚动，适合网页信息采集场景"
    )
    skill_md_path = Path(__file__).parent / "SKILL.md"

    def get_tools(self) -> list[BaseTool]:
        return [
            BrowserNavigateTool(),
            BrowserScreenshotTool(),
            BrowserExtractTextTool(),
            BrowserExtractAttrsTool(),
            BrowserExtractTableTool(),
            BrowserScrollTool(),
            BrowserClickTool(),
            BrowserExtractListTool(),
        ]
