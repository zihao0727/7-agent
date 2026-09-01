import json
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent.tools.builtin.lark._base import (
    _content_tokens,
    _extract_doc_ref,
    _looks_like_doc_has_content,
)
from agent.tools.builtin.lark.command_tool import (
    NO_FORMAT_SHORTCUTS,
    LarkCommandTool,
)
from agent.tools.builtin.lark.create_doc_tool import LarkCreateDocTool
from agent.tools.builtin.lark.send_message_tool import LarkSendMessageTool


class LarkCreateDocToolTest(unittest.IsolatedAsyncioTestCase):
    def test_extract_doc_ref_supports_nested_v2_document_response(self):
        payload = {
            "document": {
                "document_id": "PV0VdLI7go8YtbxOLWPcNd00nbc",
                "url": "https://example.feishu.cn/docx/PV0VdLI7go8YtbxOLWPcNd00nbc",
            },
            "permission_grant": {"status": "granted"},
        }

        self.assertEqual(
            _extract_doc_ref(payload),
            "https://example.feishu.cn/docx/PV0VdLI7go8YtbxOLWPcNd00nbc",
        )

    async def test_create_repairs_document_when_initial_content_is_missing(self):
        tool = LarkCreateDocTool()
        calls: list[tuple[list[str], dict]] = []

        async def fake_run_lark_command(account, args, **kwargs):
            calls.append((args, kwargs))
            if args[1] == "+create":
                return {
                    "data": {
                        "document": {
                            "document_id": "doc123",
                            "url": "https://example.feishu.cn/docx/doc123",
                        }
                    }
                }
            fetch_calls_so_far = sum(1 for call, _ in calls if call[1] == "+fetch")
            if args[1] == "+fetch" and fetch_calls_so_far == 1:
                return {"data": {"title": "任务清单", "content": ""}}
            if args[1] == "+update":
                return {"data": {"success": True, "command": "append"}}
            if args[1] == "+fetch":
                return {"data": {"title": "任务清单", "content": "## 今日到期\n\n- 修复文档写入"}}
            raise AssertionError(f"Unexpected command: {args}")

        with (
            patch.object(tool, "_get_account", new=AsyncMock(return_value=object())),
            patch("agent.tools.builtin.lark.create_doc_tool.run_lark_command", new=fake_run_lark_command),
        ):
            output = await tool.execute(
                title="任务清单",
                text="## 今日到期\n\n- 修复文档写入",
                current_user_id=1,
            )

        payload = json.loads(output)
        self.assertTrue(payload["verified"])
        self.assertTrue(payload["repaired"])
        self.assertEqual(payload["doc_ref"], "https://example.feishu.cn/docx/doc123")

        # +create must use v2 flags (--content / --doc-format), title prepended into stdin.
        create_args, create_kwargs = calls[0]
        self.assertEqual(create_args[:2], ["docs", "+create"])
        self.assertIn("--api-version", create_args)
        self.assertEqual(create_args[create_args.index("--api-version") + 1], "v2")
        self.assertIn("--doc-format", create_args)
        self.assertEqual(create_args[create_args.index("--doc-format") + 1], "markdown")
        self.assertIn("--content", create_args)
        self.assertEqual(create_args[create_args.index("--content") + 1], "-")
        self.assertNotIn("--title", create_args)
        self.assertNotIn("--markdown", create_args)
        stdin_payload = create_kwargs.get("stdin") or ""
        self.assertTrue(stdin_payload.startswith("# 任务清单"))
        self.assertIn("## 今日到期", stdin_payload)
        self.assertIn("- 修复文档写入", stdin_payload)

        # +update repair path must use --command append (NOT --mode) and stdin content.
        update_calls = [(args, kwargs) for args, kwargs in calls if args[1] == "+update"]
        self.assertEqual(len(update_calls), 1)
        update_args, update_kwargs = update_calls[0]
        self.assertIn("--command", update_args)
        self.assertEqual(update_args[update_args.index("--command") + 1], "append")
        self.assertNotIn("--mode", update_args)
        self.assertNotIn("--markdown", update_args)
        self.assertIn("--content", update_args)
        self.assertEqual(update_args[update_args.index("--content") + 1], "-")
        self.assertEqual(update_kwargs.get("stdin"), "## 今日到期\n\n- 修复文档写入")

    async def test_lark_command_does_not_add_format_to_docs_create(self):
        tool = LarkCommandTool()
        seen_args = None

        async def fake_run_lark_command(account, args, **kwargs):
            nonlocal seen_args
            seen_args = args
            return {"data": {"doc_id": "doc123", "doc_url": "https://example.feishu.cn/docx/doc123"}}

        with (
            patch.object(tool, "_get_account", new=AsyncMock(return_value=object())),
            patch("agent.tools.builtin.lark.command_tool.run_lark_command", new=fake_run_lark_command),
        ):
            output = await tool.execute(
                command=["docs", "+create", "--title", "任务清单", "--markdown", "正文"],
                identity="bot",
                current_user_id=1,
            )

        self.assertIn("doc123", output)
        self.assertEqual(seen_args[:2], ["docs", "+create"])
        self.assertIn("--as", seen_args)
        self.assertNotIn("--format", seen_args)

    async def test_create_does_not_repair_when_fetched_xml_already_contains_content(self):
        """Regression: lark v2 +fetch returns XML by default. The previous verify
        logic compared the markdown source against the XML blob and always
        failed, causing a redundant +update append that duplicated content and
        ultimately raised. The fixed verifier must accept the XML representation.
        """
        tool = LarkCreateDocTool()
        title = "赵子豪 - 飞书任务清单（2026-05-18）"
        text = (
            "# 赵子豪 - 飞书任务清单\n\n"
            "> 更新时间：2026-05-18 19:30\n\n"
            "## 🔴 近期待办\n\n"
            "| 任务 | 截止日期 |\n|------|---------|\n"
            "| 老师采购报表结合数据库分析 | 2026-05-19 |\n"
        )
        # XML blob shape lark CLI v2 actually returned in the bug report.
        fetched_xml_content = (
            f"<title>{title}</title>"
            "<blockquote><p>更新时间：2026-05-18 19:30</p></blockquote>"
            "<h2>🔴 近期待办</h2>"
            "<table><tbody><tr>"
            "<td><p>老师采购报表结合数据库分析</p></td>"
            "<td><p>2026-05-19</p></td>"
            "</tr></tbody></table>"
        )
        calls: list[tuple[list[str], dict]] = []

        async def fake_run_lark_command(account, args, **kwargs):
            calls.append((args, kwargs))
            if args[1] == "+create":
                return {
                    "data": {
                        "document": {
                            "document_id": "doc999",
                            "url": "https://example.feishu.cn/docx/doc999",
                        }
                    }
                }
            if args[1] == "+fetch":
                return {"data": {"document": {"content": fetched_xml_content}}}
            raise AssertionError(f"Unexpected command: {args}")

        with (
            patch.object(tool, "_get_account", new=AsyncMock(return_value=object())),
            patch("agent.tools.builtin.lark.create_doc_tool.run_lark_command", new=fake_run_lark_command),
        ):
            output = await tool.execute(title=title, text=text, current_user_id=1)

        payload = json.loads(output)
        self.assertTrue(payload["verified"])
        self.assertFalse(payload["repaired"])
        # The bug was: a second +update append was issued. After the fix,
        # +update must NEVER fire when the first fetch already shows content.
        self.assertFalse(any(args[1] == "+update" for args, _ in calls))


class LooksLikeDocHasContentTest(unittest.TestCase):
    def test_xml_fetched_blob_with_cjk_title_and_body_passes(self):
        title = "赵子豪 - 飞书任务清单（2026-05-18）"
        text = "# 赵子豪 - 飞书任务清单\n\n> 更新时间：2026-05-18 19:30\n\n- 老师采购报表结合数据库分析"
        fetched = {
            "document": {
                "content": (
                    f"<title>{title}</title>"
                    "<blockquote><p>更新时间：2026-05-18 19:30</p></blockquote>"
                    "<p>老师采购报表结合数据库分析</p>"
                )
            }
        }
        self.assertTrue(_looks_like_doc_has_content(fetched, title=title, text=text))

    def test_empty_fetched_blob_fails(self):
        self.assertFalse(
            _looks_like_doc_has_content(
                {"document": {"content": ""}},
                title="任务清单",
                text="# 任务清单\n\n## 今日到期\n\n- 修复文档写入",
            )
        )

    def test_unrelated_fetched_blob_fails(self):
        self.assertFalse(
            _looks_like_doc_has_content(
                {"document": {"content": "<p>completely unrelated stuff</p>"}},
                title="赵子豪 - 飞书任务清单",
                text="# 赵子豪 - 飞书任务清单\n\n- 老师采购报表结合数据库分析\n- 大地数据全部下载到本地",
            )
        )

    def test_content_tokens_strips_markdown_noise(self):
        tokens = _content_tokens("# 任务清单\n\n> 更新时间\n\n- 老师采购报表 *bold*")
        # Pure markdown punctuation must not survive.
        self.assertNotIn("#", tokens)
        self.assertNotIn(">", tokens)
        self.assertNotIn("*", tokens)
        # CJK content runs (>= 3 chars) must be picked up.
        self.assertIn("任务清单", tokens)
        self.assertIn("老师采购报表", tokens)


class LarkSendMessageToolTest(unittest.IsolatedAsyncioTestCase):
    """Regression: `im +messages-send` does NOT accept --format. The default
    add_format=True path of run_lark_command would inject --format json and
    cause every send to fail with `unknown flag: --format`.
    """

    async def test_send_message_must_not_inject_format_flag(self):
        tool = LarkSendMessageTool()
        captured: dict = {}

        async def fake_run_lark_command(account, args, **kwargs):
            captured["args"] = args
            captured["add_format"] = kwargs.get("add_format")
            return {"data": {"message_id": "om_xxx"}}

        with (
            patch.object(tool, "_get_account", new=AsyncMock(return_value=object())),
            patch(
                "agent.tools.builtin.lark.send_message_tool.run_lark_command",
                new=fake_run_lark_command,
            ),
        ):
            output = await tool.execute(
                chat_id="oc_xxx",
                text="hello",
                identity="bot",
                current_user_id=1,
            )

        self.assertIn("om_xxx", output)
        self.assertEqual(captured["args"][:2], ["im", "+messages-send"])
        # Must explicitly opt out of run_lark_command's default --format json append.
        self.assertEqual(captured["add_format"], False)
        self.assertNotIn("--format", captured["args"])


class LarkCommandToolFormatBlacklistTest(unittest.IsolatedAsyncioTestCase):
    """Regression: expanded NO_FORMAT_SHORTCUTS so that lark_command no longer
    injects --format json into commands that don't support it.
    """

    def test_blacklist_covers_known_no_format_shortcuts(self):
        # These were verified against `lark-cli ... --help` output and reject --format.
        for entry in {
            ("docs", "+create"),
            ("docs", "+update"),
            ("docs", "+fetch"),
            ("docs", "+media-upload"),
            ("docs", "+whiteboard-update"),
            ("im", "+messages-send"),
            ("sheets", "+create"),
            ("auth", "status"),
            ("auth", "login"),
            ("auth", "check"),
        }:
            self.assertIn(entry, NO_FORMAT_SHORTCUTS, msg=f"{entry} missing from blacklist")

    async def test_lark_command_skips_format_for_im_messages_send(self):
        tool = LarkCommandTool()
        captured: dict = {}

        async def fake_run_lark_command(account, args, **kwargs):
            captured["args"] = args
            return {"data": {"message_id": "om_xxx"}}

        with (
            patch.object(tool, "_get_account", new=AsyncMock(return_value=object())),
            patch(
                "agent.tools.builtin.lark.command_tool.run_lark_command",
                new=fake_run_lark_command,
            ),
        ):
            await tool.execute(
                command=["im", "+messages-send", "--chat-id", "oc_xxx", "--text", "hi"],
                identity="bot",
                current_user_id=1,
            )

        self.assertEqual(captured["args"][:2], ["im", "+messages-send"])
        self.assertNotIn("--format", captured["args"])

    async def test_lark_command_skips_format_for_auth_status(self):
        tool = LarkCommandTool()
        captured: dict = {}

        async def fake_run_lark_command(account, args, **kwargs):
            captured["args"] = args
            return {"data": {"ok": True}}

        with (
            patch.object(tool, "_get_account", new=AsyncMock(return_value=object())),
            patch(
                "agent.tools.builtin.lark.command_tool.run_lark_command",
                new=fake_run_lark_command,
            ),
        ):
            # Note: auth has no domain identity injection, but pass identity=bot
            # explicitly so --as is appended (and we still verify --format is not).
            await tool.execute(
                command=["auth", "status"],
                identity="bot",
                current_user_id=1,
            )

        self.assertEqual(captured["args"][:2], ["auth", "status"])
        self.assertNotIn("--format", captured["args"])

    async def test_lark_command_still_adds_format_for_format_supporting_command(self):
        """Sanity: --format json is still appended for commands that DO accept it
        (e.g. calendar +agenda), so the blacklist hasn't overcorrected.
        """
        tool = LarkCommandTool()
        captured: dict = {}

        async def fake_run_lark_command(account, args, **kwargs):
            captured["args"] = args
            return {"data": {"events": []}}

        with (
            patch.object(tool, "_get_account", new=AsyncMock(return_value=object())),
            patch(
                "agent.tools.builtin.lark.command_tool.run_lark_command",
                new=fake_run_lark_command,
            ),
        ):
            await tool.execute(
                command=["calendar", "+agenda", "--calendar-id", "primary"],
                identity="user",
                current_user_id=1,
            )

        self.assertEqual(captured["args"][:2], ["calendar", "+agenda"])
        self.assertIn("--format", captured["args"])
        fmt_idx = captured["args"].index("--format")
        self.assertEqual(captured["args"][fmt_idx + 1], "json")


if __name__ == "__main__":
    unittest.main()
