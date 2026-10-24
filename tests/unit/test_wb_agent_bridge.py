# -*- coding: utf-8 -*-
"""unit：wb_agent_bridge —— CLI 解析 / 输出提取 / prompt 组装 / 错误分类。"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from wb_agent_bridge import (  # noqa: E402
    compose_prompt, extract_assistant_text, extract_json_block, find_cli, run_agent,
)


class FindCliTest(unittest.TestCase):
    def test_default_install(self):
        # 默认安装路径存在时返回它（本机官方 CLI）
        p = Path(r"C:\Users\hxjlcj\AppData\Local\codebuddy\bin\codebuddy.exe")
        if p.exists():
            self.assertEqual(find_cli(), str(p))

    def test_env_override(self):
        with tempfile.NamedTemporaryFile(suffix=".exe", delete=False) as f:
            fake = f.name
        try:
            old = os.environ.get("BIDCRAFT_AGENT_CLI")
            os.environ["BIDCRAFT_AGENT_CLI"] = fake
            try:
                self.assertEqual(find_cli(), fake)
            finally:
                if old is None:
                    os.environ.pop("BIDCRAFT_AGENT_CLI", None)
                else:
                    os.environ["BIDCRAFT_AGENT_CLI"] = old
        finally:
            try:
                os.unlink(fake)
            except OSError:
                pass


class ExtractAssistantTextTest(unittest.TestCase):
    def test_plain_text_fallback(self):
        text, parsed = extract_assistant_text("不是 JSON 的原始输出")
        self.assertFalse(parsed)
        self.assertEqual(text, "不是 JSON 的原始输出")

    def test_message_stream(self):
        stream = [
            {"type": "message", "role": "user",
             "content": [{"type": "input_text", "text": "你好"}]},
            {"type": "message", "role": "assistant",
             "content": [{"type": "text", "text": "第一段"}]},
            {"type": "message", "role": "assistant",
             "content": [{"type": "text", "text": "第二段"}]},
        ]
        text, parsed = extract_assistant_text(json.dumps(stream))
        self.assertTrue(parsed)
        self.assertIn("第一段", text)
        self.assertIn("第二段", text)

    def test_empty(self):
        text, parsed = extract_assistant_text("")
        self.assertEqual(text, "")
        self.assertFalse(parsed)


class ExtractJsonBlockTest(unittest.TestCase):
    SKELETON = {"project": "P", "modules": [{"id": "basic", "label": "项目基本信息", "items": []}], "diffs": []}

    def test_fenced_json(self):
        text = "投标要点正文……\n```json\n%s\n```\n结尾" % json.dumps(self.SKELETON, ensure_ascii=False)
        obj, err = extract_json_block(text)
        self.assertIsNone(err)
        self.assertEqual(obj["project"], "P")

    def test_brace_scan_fallback(self):
        text = "投标要点正文……\n" + json.dumps(self.SKELETON, ensure_ascii=False) + "\n（完）"
        obj, err = extract_json_block(text)
        self.assertIsNone(err)
        self.assertEqual(obj["project"], "P")

    def test_missing(self):
        obj, err = extract_json_block("只有文本，没有 JSON")
        self.assertIsNone(obj)
        self.assertIn("未找到", err)

    def test_empty(self):
        obj, err = extract_json_block("")
        self.assertIsNone(obj)


class ComposePromptTest(unittest.TestCase):
    def test_contains_contract_and_original(self):
        tpl = "你是一位资深的招投标与工程监理专家……"
        original = "第一章 招标公告……（1800 行）"
        prompt = compose_prompt(tpl, original, "测试项目")
        self.assertIn("测试项目", prompt)
        self.assertIn(tpl, prompt)
        self.assertIn(original, prompt)
        self.assertIn("机器可解析输出契约", prompt)
        self.assertIn("modules", prompt)


class RunAgentTest(unittest.TestCase):
    """用假 CLI 脚本验证 run_agent 的调用形态与错误分类（不真调 AI）。"""

    def _fake_cli(self, body):
        """写一个假 codebuddy 脚本：把 -p 的 prompt 存文件、回显固定 JSON 消息流。"""
        import textwrap
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "fake_cb.py"
            prompt_log = Path(tmp) / "prompt.txt"
            p.write_text(textwrap.dedent(
                'import json,sys\n'
                'out=json.loads(sys.stdin.read())\n'  # 占位，实际参数不走 stdin
            ), encoding="utf-8")
            # 用 .bat 包装更贴近 Windows 可执行：直接建一个可执行脚本不可行（无 shebang on win），
            # 这里改用 python -c 包装：run_agent 的 cli 参数可以是 ["python", "-c", code]
            code = (
                "import json,sys\n"
                "args=sys.argv[1:]\n"
                "i=args.index('-p')\n"
                "open(%r,'w',encoding='utf-8').write(args[i+1])\n"
                "sys.stdout.write(%s)\n" % (str(prompt_log).replace("'", "\\'"), json.dumps(body))
            )
            return code, prompt_log

    def test_run_agent_ok(self):
        body = json.dumps([
            {"type": "message", "role": "assistant",
             "content": [{"type": "text", "text": "## 投标要点\n…"}]},
        ])
        with tempfile.TemporaryDirectory() as tmp:
            prompt_log = Path(tmp) / "prompt.txt"
            code = (
                "import json,sys\n"
                "args=sys.argv[1:]\n"
                "i=args.index('-p')\n"
                "open(%r,'w',encoding='utf-8').write(args[i+1])\n"
                "sys.stdout.write(%s)\n" % (str(prompt_log).replace("'", "\\'"), repr(body))
            )
            res = run_agent("请解析", timeout=30, cli=[sys.executable, "-c", code])
            self.assertTrue(res["ok"], res.get("error"))
            self.assertEqual(res["rc"], 0)
            self.assertIn("投标要点", res["text"])
            self.assertTrue(prompt_log.exists())

    def test_run_agent_auth_required(self):
        res = run_agent("hi", timeout=30, cli=[sys.executable, "-c",
                                               "import sys; print('Authentication required. Please use /login command', file=sys.stderr)"])
        self.assertFalse(res["ok"])
        self.assertIn("/login", res["error"])

    def test_run_agent_missing_cli(self):
        res = run_agent("hi", timeout=5, cli=None)
        # find_cli 在本机可能命中官方 CLI：若命中则不会走 missing 分支——此用例仅在 CLI 缺失时断言
        if find_cli() is None:
            self.assertFalse(res["ok"])
            self.assertIn("未找到", res["error"])
        else:
            self.skipTest("本机已安装 CLI，缺失场景跳过")

    def test_run_agent_timeout(self):
        res = run_agent("hi", timeout=1, cli=[sys.executable, "-c", "import time; time.sleep(5)"])
        self.assertFalse(res["ok"])
        self.assertIn("超时", res["error"])


if __name__ == "__main__":
    unittest.main()
