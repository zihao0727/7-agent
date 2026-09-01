import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent.tools.builtin.bash import POWERSHELL_UTF8_PREAMBLE, _build_shell_command


class BashToolEncodingTest(unittest.TestCase):
    def test_powershell_commands_force_utf8_get_content_and_output(self):
        command = _build_shell_command("type report.md", "powershell")

        self.assertIn("-Command", command)
        script = command[-1]
        self.assertTrue(script.startswith(POWERSHELL_UTF8_PREAMBLE))
        self.assertIn("$PSDefaultParameterValues['Get-Content:Encoding'] = 'UTF8'", script)
        self.assertTrue(script.endswith("type report.md"))

    def test_cmd_commands_are_not_rewritten(self):
        self.assertEqual(_build_shell_command("type report.md", "cmd"), ["cmd", "/c", "type report.md"])


if __name__ == "__main__":
    unittest.main()
