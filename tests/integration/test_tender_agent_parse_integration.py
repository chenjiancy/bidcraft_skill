# -*- coding: utf-8 -*-
"""integration：tender-agent-parse —— 假 CLI 全链路：临时库建企业/项目/原文 →
命令执行 → 投标要点 md+json 校验落盘（复用规则校验，不真调 AI）。"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))


def run_cli(root, *argv):
    """跑 bidcraft.py（root 指向临时库根）。"""
    env = dict(os.environ)
    env["BIDCRAFT_LIB_ROOT"] = str(root)
    r = subprocess.run(
        [sys.executable, "-X", "utf8", str(REPO / "scripts" / "bidcraft.py")] + list(argv),
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120, env=env)
    return r


def write_fake_cli(prompt_log, body):
    """生成假 codebuddy CLI：把 -p 的 prompt 写入 prompt_log，stdout 回显固定 JSON 消息流。"""
    import textwrap
    code = textwrap.dedent(
        """\
        import json,sys
        args=sys.argv[1:]
        i=args.index('-p')
        open(PROMPT_LOG,'w',encoding='utf-8').write(args[i+1])
        sys.stdout.write(BODY)
        """).replace("PROMPT_LOG", repr(str(prompt_log))).replace("BODY", repr(body))
    return code


def make_fake_response(project, modules, diffs=None):
    """构造一个符合 rules.validate_points_json 的投标要点 JSON 骨架（最小有效集）。"""
    doc = {
        "project": project,
        "modules": modules,
        "diffs": diffs or [],
    }
    md = (
        "# 投标要点 %s\n\n"
        "## 模块一 项目基本信息\n"
        "- 项目名称：%s（原文 P1）\n\n"
        "```json\n%s\n```\n"
    ) % (project, project, json.dumps(doc, ensure_ascii=False))
    return md


BASIC_MODULES = [
    {"id": "basic", "title": "项目基本信息", "type": "info",
     "items": [{"name": "项目名称", "value": "通道B测试项目", "source": "P1"}]},
    {"id": "qualification", "title": "资格条件", "type": "qualification", "items": []},
    {"id": "staff", "title": "人员配备", "type": "staff", "items": []},
    {"id": "project_overview", "title": "项目概况", "type": "overview", "items": []},
    {"id": "scoring", "title": "评标办法", "type": "scoring", "items": []},
    {"id": "pricing", "title": "报价要求", "type": "pricing", "items": []},
    {"id": "submission", "title": "响应文件编制", "type": "submission", "items": []},
    {"id": "reject", "title": "废标红线", "type": "reject", "items": []},
    {"id": "pending", "title": "待确认项", "type": "pending", "items": []},
]


class TenderAgentParseIntegrationTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.enterprise = "测试企业"
        self.project = "通道B测试项目"
        (self.root / self.enterprise).mkdir(parents=True)
        # 企业 + 项目级目录 + 招标原文
        r = run_cli(self.root, "init-enterprise", "--name", self.enterprise)
        self.assertEqual(r.returncode, 0, r.stderr or r.stdout)
        r = run_cli(self.root, "tender-init", "--project", self.project)
        self.assertEqual(r.returncode, 0, r.stderr or r.stdout)
        r = run_cli(self.root, "tender-extract", "--project", self.project,
                    "--text-file", str(self._write_original()))
        self.assertEqual(r.returncode, 0, r.stderr or r.stdout)
        # 假 CLI（.py 直跑）：记录 prompt + 回显固定 JSON 消息流
        self.prompt_log = Path(self._tmp.name) / "prompt.txt"
        self.fake_body = json.dumps([
            {"type": "message", "role": "assistant",
             "content": [{"type": "text", "text": make_fake_response(self.project, BASIC_MODULES)}]},
        ])
        self.fake_cli_py = Path(self._tmp.name) / "fake_codebuddy.py"
        self.fake_cli_py.write_text(write_fake_cli(self.prompt_log, self.fake_body),
                                    encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def _write_original(self):
        p = Path(self._tmp.name) / "招标原文.txt"
        p.write_text("第一章 招标公告……\n招标编号：TR-2026-001\n投标截止：2026-12-31\n",
                     encoding="utf-8")
        return p

    def test_agent_parse_full_pipeline(self):
        # 用 --cli 注入假 CLI（.py 直跑：bridge 用当前解释器启动）
        r = run_cli(self.root, "tender-agent-parse", "--project", self.project,
                    "--cli", str(self.fake_cli_py))
        self.assertEqual(r.returncode, 0, r.stderr or r.stdout)
        self.assertIn("已由 agent 桥自动完成", r.stdout)
        # 落盘产物存在且结构合法
        tdir = (self.root / self.enterprise / "项目级" / self.project / "招标解析")
        json_p = tdir / ("投标要点_%s.json" % self.project)
        md_p = tdir / ("投标要点_%s.md" % self.project)
        self.assertTrue(json_p.exists(), "投标要点 json 未落盘")
        self.assertTrue(md_p.exists())
        doc = json.loads(json_p.read_text(encoding="utf-8"))
        self.assertEqual(doc["project"], self.project)
        self.assertGreaterEqual(len(doc["modules"]), 9)
        # prompt 确实传入了原文与契约
        prompt = self.prompt_log.read_text(encoding="utf-8")
        self.assertIn("第一章 招标公告", prompt)
        self.assertIn("机器可解析输出契约", prompt)

    def test_agent_parse_missing_original(self):
        # 删除原文 → 命令应明确报错（不落盘）
        tdir = (self.root / self.enterprise / "项目级" / self.project / "招标解析")
        for f in tdir.glob("原文_*.txt"):
            f.unlink()
        r = run_cli(self.root, "tender-agent-parse", "--project", self.project,
                    "--cli", str(self.fake_cli_py))
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("未找到 原文", r.stderr or r.stdout)


if __name__ == "__main__":
    unittest.main()

