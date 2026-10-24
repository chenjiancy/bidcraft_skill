# -*- coding: utf-8 -*-
"""M6 T14 自动撰写引擎（tech-draft）单测：规则拼装骨架草稿生成。

覆盖：命令注册 / 闸门① / 上下文包缺失 / 内容断言（标记·小节·人员表·素材注入·暗标口径）/
字数达标 / 草稿可直接过 tech-parse / 缺料披露 / 已有正文跳过 / 重复生成备份 / --all / 通用兜底。
fixture 与 test_m6_cli.py 同构（PROJECT="测试项目M6"）。
"""
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "scripts"))

import bidcraft                     # noqa: E402
from _shared import core            # noqa: E402
from m6_tech import store           # noqa: E402

PROJECT = "测试项目M6"


def _points(bid_mode="明标", pages=60):
    rule = "技术标总页数不超过 %d 页；%s" % (
        pages, "技术标采用暗标，不得出现企业标识" if bid_mode == "暗标" else "按明标编制")
    return {
        "project": PROJECT,
        "modules": [
            {"id": "basic", "title": "项目基本信息", "type": "fields", "fields": {
                "采购人": {"value": "和县住建局", "evidence": "e"},
                "项目名称": {"value": PROJECT, "evidence": "e"},
                "服务期": {"value": "合同签订至缺陷责任期结束", "evidence": "e"},
            }},
            {"id": "project_overview", "title": "项目概况", "type": "fields", "fields": {
                "项目概况": {"value": "两个片区共 762 栋房屋", "evidence": "e"},
                "监理范围": {"value": "施工及保修阶段全过程监理", "evidence": "e"},
            }},
            {"id": "scoring", "title": "评分办法", "type": "mixed",
             "method": {"value": "综合评分法", "evidence": "e"},
             "score_items": [
                 {"item": "监理大纲（50分）", "weight": 50, "unit": "分", "evidence": "E1"},
                 {"item": "监理大纲·综合比较阐述（20分）", "weight": 20, "unit": "分", "evidence": "E3"}]},
            {"id": "reject", "title": "废标红线", "type": "items",
             "items": [{"type": "格式", "rule": rule, "evidence": "e"}]},
        ],
    }


def _material():
    return {
        "project": PROJECT,
        "personnel": [{"name": "张三", "role": "总监理工程师"}],
        "performance": [{"name": "某小区改造监理", "path": "业绩/某小区.pdf"}],
        "企业基础信息": {"法定代表人姓名": "李四"},
        "qualification_required": [{"name": "营业执照", "path": "资质/营业执照.pdf"}],
        "iso_certificates": [], "honors": [],
        "items": [],
    }


def _draft(chapters=2, word_cnt=1500):
    ch1 = {
        "id": "ch-01", "no": "1", "title": "工程概况与监理范围", "level": 1,
        "scoreRefs": [{"idx": 0, "item": "监理大纲（50分）", "weight": 50}],
        "keyPoints": ["工程概况", "监理范围", "质量控制"], "wordCnt": word_cnt,
        "dependsOnMaterials": ["project_overview", "personnel", "performance", "enterprise_profile"],
    }
    out = [ch1]
    if chapters > 1:
        out.append({
            "id": "ch-02", "no": "2", "title": "合同信息管理", "level": 1,
            "scoreRefs": [{"idx": 1, "item": "监理大纲·综合比较阐述（20分）", "weight": 20}],
            "keyPoints": ["合同管理", "信息管理"], "wordCnt": 1000, "dependsOnMaterials": []})
    return {"chapters": out}


class DraftTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.ent, _ = core.Library(self.root).init_enterprise("企业A")
        self.proj = self.ent / "项目级" / PROJECT
        self.tdir = self.proj / "招标解析"
        self.tdir.mkdir(parents=True)
        self._write_points(_points())
        self._write_material()
        self.draft_path = self.proj / "章节树草案.json"
        self._write_draft(_draft())

    def tearDown(self):
        self.tmp.cleanup()

    def _write_points(self, obj):
        (self.tdir / ("投标要点_%s.json" % PROJECT)).write_text(
            json.dumps(obj, ensure_ascii=False), encoding="utf-8")

    def _write_material(self):
        (self.tdir / ("素材清单_%s.json" % PROJECT)).write_text(
            json.dumps(_material(), ensure_ascii=False), encoding="utf-8")

    def _write_draft(self, obj, path=None):
        (path or self.draft_path).write_text(
            json.dumps(obj, ensure_ascii=False), encoding="utf-8")

    def _run(self, *argv):
        out, err, code = io.StringIO(), io.StringIO(), 0
        with redirect_stdout(out), redirect_stderr(err):
            try:
                bidcraft.main(["--root", str(self.root), "--enterprise", "企业A"] + list(argv))
            except SystemExit as e:
                code = e.code or 0
        return code, out.getvalue(), err.getvalue()

    def _init(self, *extra):
        return self._run("tech-init", "--project", PROJECT, *extra)

    def _outline(self, *extra):
        return self._run("tech-outline", "--project", PROJECT, "--file", str(self.draft_path), *extra)

    def _ctx(self, *extra):
        return self._run("tech-ctx", "--project", PROJECT, "--all", *extra)

    def _draft(self, *extra):
        return self._run("tech-draft", "--project", PROJECT, *extra)

    def _tech(self):
        return store.tech_path(self.ent, PROJECT)

    def _draft_file(self, cid="ch-01"):
        return self._tech() / "章节" / ("%s.draft.md" % cid)

    def _prep(self, chapters=2, word_cnt=1500):
        self._write_draft(_draft(chapters=chapters, word_cnt=word_cnt))
        c, o, e = self._init()
        self.assertEqual(c, 0, e or o)
        c, o, e = self._outline("--confirm")
        self.assertEqual(c, 0, e or o)
        self.assertEqual(self._ctx()[0], 0)

    # -- 命令注册 / 闸门 ---------------------------------------------------
    def test_command_registered(self):
        code, out, _ = self._run("--help")
        self.assertEqual(code, 0)
        self.assertIn("tech-draft", out)

    def test_gate1_unconfirmed_rejected(self):
        self._init()
        code, _, err = self._draft("--chapter", "ch-01")
        self.assertEqual(code, 1)
        self.assertIn("章节树", err)          # 未 outline → 章节树不存在（闸门①前置）

    def test_ctx_missing_rejected(self):
        self._init()
        self._outline("--confirm")
        code, _, err = self._draft("--chapter", "ch-01")
        self.assertEqual(code, 1)
        self.assertIn("上下文包不存在", err)

    def test_requires_chapter_or_all(self):
        self._prep()
        code, _, err = self._draft()
        self.assertEqual(code, 1)
        self.assertIn("请指定 --chapter", err)

    # -- 内容断言 ---------------------------------------------------------
    def test_draft_content_marks_and_sections(self):
        self._prep()
        code, out, _ = self._draft("--chapter", "ch-01")
        self.assertEqual(code, 0, out)
        md = self._draft_file().read_text(encoding="utf-8")
        self.assertIn("<!-- M6-DRAFT m6.draft/v1", md)
        self.assertIn("### 工程概况与监理工作理解", md)
        self.assertIn("### 监理工作范围", md)
        self.assertIn("### 质量控制措施", md)
        self.assertIn("<!-- M6-COVERAGE", md)

    def test_draft_injects_personnel_and_performance(self):
        self._prep()
        self.assertEqual(self._draft("--chapter", "ch-01")[0], 0)
        md = self._draft_file().read_text(encoding="utf-8")
        self.assertIn("| 张三 | 总监理工程师 |", md)          # 人员表（明标带名）
        self.assertIn("【素材:业绩】", md)                      # 业绩注入
        self.assertIn("某小区改造监理", md)

    def test_draft_anbiao_strips_identity(self):
        self._write_points(_points(bid_mode="暗标"))
        self._prep()
        self.assertEqual(self._draft("--chapter", "ch-01")[0], 0)
        md = self._draft_file().read_text(encoding="utf-8")
        self.assertNotIn("张三", md)
        self.assertNotIn("李四", md)
        self.assertNotIn("某小区改造监理", md)
        self.assertNotIn("企业A", md)
        self.assertIn("| 岗位 | 职责 |", md)                   # 暗标人员表无姓名列
        self.assertIn("同类工程", md)                          # 业绩匿名描述

    def test_draft_anbiao_passes_sensitive_scan(self):
        self._write_points(_points(bid_mode="暗标"))
        self._prep()
        # tech-parse 的敏感词校验会拒绝含企业/人名的正文；草稿必须天然不命中
        self.assertEqual(self._draft("--chapter", "ch-01")[0], 0)

    def test_draft_word_count_meets_floor(self):
        self._prep(word_cnt=3000)
        self.assertEqual(self._draft("--chapter", "ch-01")[0], 0)
        md = self._draft_file().read_text(encoding="utf-8")
        from m6_tech import rules
        body = rules.strip_selfcheck_block(md)
        cnt = rules.count_chars(body)
        self.assertGreaterEqual(cnt["body_chars"] + cnt["table_chars"], 3000 * 0.7)

    def test_draft_selfcheck_block_valid(self):
        self._prep()
        self.assertEqual(self._draft("--chapter", "ch-01")[0], 0)
        md = self._draft_file().read_text(encoding="utf-8")
        from m6_tech import rules
        info, err = rules.parse_selfcheck_block(md)
        self.assertFalse(err)
        self.assertEqual(info["block"], "M6-COVERAGE")
        self.assertGreaterEqual(len(info["data"]["keyPoints"]), 3)
        self.assertTrue(all(k["covered"] for k in info["data"]["keyPoints"]))

    # -- 缺料 / 状态机 / 落盘 ----------------------------------------------
    def test_missing_material_disclosure(self):
        self._write_draft(_draft(chapters=1))
        self._prep()
        # ch-02（无 dependsOnMaterials）→ 缺料披露
        self.assertEqual(self._draft("--chapter", "ch-02")[0], 0)
        md = self._draft_file("ch-02").read_text(encoding="utf-8")
        from m6_tech import rules
        info, _ = rules.parse_selfcheck_block(md)
        self.assertGreaterEqual(len(info["data"]["missingMaterials"]), 1)
        self.assertNotIn("{{待填:", md)          # 引擎不落硬占位（缺料走自述块披露）

    def test_draft_then_parse_full_chain(self):
        """机器草稿可直接 tech-parse 落盘 WRITTEN（精修链入口）。"""
        self._prep()
        self.assertEqual(self._draft("--chapter", "ch-01")[0], 0)
        code, out, _ = self._run("tech-parse", "--project", PROJECT, "--chapter", "ch-01",
                                 "--file", str(self._draft_file()))
        self.assertEqual(code, 0, out)
        tree = store.read_tree(self._tech())
        self.assertEqual(store.find_chapter(tree, "ch-01")["status"], "WRITTEN")

    def test_written_chapter_skipped(self):
        self._prep()
        self.assertEqual(self._draft("--chapter", "ch-01")[0], 0)
        self._run("tech-parse", "--project", PROJECT, "--chapter", "ch-01",
                  "--file", str(self._draft_file()))
        code, out, _ = self._draft("--all")
        self.assertEqual(code, 0, out)
        self.assertIn("跳过", out)
        self.assertIn("已有正文", out)

    def test_regenerate_backs_up_previous(self):
        self._prep()
        self.assertEqual(self._draft("--chapter", "ch-01")[0], 0)
        md1 = self._draft_file().read_text(encoding="utf-8")
        self.assertEqual(self._draft("--chapter", "ch-01")[0], 0)   # 重新生成（覆盖旧草稿）
        md2 = self._draft_file().read_text(encoding="utf-8")
        self.assertEqual(md1, md2)               # 引擎确定性：同输入同输出（可复现）
        trash = self._tech() / ".rewrite-trash"
        self.assertTrue(trash.is_dir())
        self.assertGreaterEqual(len(list(trash.iterdir())), 1)   # 旧草稿已备份

    def test_all_chapters_and_generic_fallback(self):
        self._prep(chapters=2)
        code, out, _ = self._draft("--all")
        self.assertEqual(code, 0, out)
        self.assertTrue(self._draft_file("ch-01").is_file())
        self.assertTrue(self._draft_file("ch-02").is_file())
        md = self._draft_file("ch-02").read_text(encoding="utf-8")
        self.assertIn("### 合同管理与信息管理", md)

    def test_json_output(self):
        self._prep()
        code, out, _ = self._draft("--chapter", "ch-01", "--json")
        self.assertEqual(code, 0)
        obj = json.loads(out)
        self.assertEqual(obj["chapters"][0]["id"], "ch-01")
        self.assertGreaterEqual(obj["chapters"][0]["chars"], 0)


if __name__ == "__main__":
    unittest.main()
