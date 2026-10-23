# -*- coding: utf-8 -*-
"""M6 技术标制作 · 纯逻辑层（F1–F11）单测。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "scripts"))

from m6_tech import rules as m6  # noqa: E402


def ch(**kw):
    base = {
        "id": "ch-01", "no": "1", "title": "工程概况与监理工作范围", "level": 1,
        "scoreRefs": [{"idx": 0, "item": "监理大纲（30分）", "weight": 30}],
        "keyPoints": ["监理大纲完整性", "针对性", "监理工作范围"],
        "wordCnt": 3000, "dependsOnMaterials": ["project_overview"],
    }
    base.update(kw)
    return base


def tree(**kw):
    base = {
        "schema": "m6.chapters/v1", "project": "和县2026", "bidMode": "明标",
        "pageConstraint": {"max": 80, "estimate": 72, "charsPerPage": 1000,
                           "source": "招标文件 第X章"},
        "style": {"id": "strict", "name": "严谨正式", "promptRef": "styles.json#strict"},
        "layout": {"preset": "single-column", "palette": "deep-indigo",
                   "cover": "full-block", "decoration": "standard", "font": "gov-gongwen",
                   "imageRatio": "mid", "imageRule": "hybrid", "imageLayout": "split-h",
                   "pageSetup": "p1-standard-a4", "headingSystem": "h1-gbt-arabic",
                   "tocStyle": "t1-jianyu-auto", "tableStyle": "tb1-three-line",
                   "captionSystem": "c2-cy-chapter", "paragraphStyle": "pa7-jianyu-15",
                   "headerFooter": "hf1-classic-enterprise"},
        "terminology": {"招标人": "和县住建局", "项目名称": "和县2026"},
        "personnel": [{"name": "张三", "post": "总监理工程师", "source": "素材清单#personnel[0]"}],
        "chapters": [dict(ch(), status="PENDING",
                          files={"body": "章节/ch-01.md", "meta": "章节/.meta/ch-01.json"})],
    }
    base.update(kw)
    return base


def levels(issues):
    return [i["level"] for i in issues]


def codes(issues):
    return [i["code"] for i in issues]


class TestDraft(unittest.TestCase):
    def test_valid(self):
        ok, issues = m6.validate_chapters_draft({"chapters": [ch()], "notes": ["说明"]}, [{"item": "监理大纲"}])
        self.assertTrue(ok, issues)
        self.assertFalse([i for i in issues if i["level"] == "error"])

    def test_non_dict(self):
        ok, issues = m6.validate_chapters_draft([])
        self.assertFalse(ok)
        self.assertEqual(issues[0]["code"], "draft.type")

    def test_empty_chapters(self):
        ok, issues = m6.validate_chapters_draft({"chapters": []})
        self.assertFalse(ok)
        self.assertEqual(issues[0]["code"], "draft.empty")

    def test_duplicate_no(self):
        ok, issues = m6.validate_chapters_draft({"chapters": [ch(), ch(id="ch-02")]})
        self.assertFalse(ok)
        self.assertIn("ch.no-dup", codes(issues))

    def test_parent_missing(self):
        ok, issues = m6.validate_chapters_draft({"chapters": [ch(no="2.1", level=2)]})
        self.assertFalse(ok)
        self.assertIn("ch.parent", codes(issues))

    def test_sequence_gap(self):
        ok, issues = m6.validate_chapters_draft(
            {"chapters": [ch(), ch(id="ch-03", no="3", level=1)]})
        self.assertFalse(ok)
        self.assertIn("ch.sequence", codes(issues))

    def test_idx_out_of_range(self):
        ok, issues = m6.validate_chapters_draft(
            {"chapters": [ch(scoreRefs=[{"idx": 5, "item": "x"}])]}, [{"item": "x"}])
        self.assertFalse(ok)
        self.assertIn("ch.scoreref-range", codes(issues))

    def test_level_mismatch(self):
        ok, issues = m6.validate_chapters_draft({"chapters": [ch(no="1.1", level=1)]})
        self.assertFalse(ok)
        self.assertIn("ch.level", codes(issues))

    def test_bad_depends_enum(self):
        ok, issues = m6.validate_chapters_draft({"chapters": [ch(dependsOnMaterials=["foo"])]})
        self.assertFalse(ok)
        self.assertIn("ch.depends-enum", codes(issues))

    def test_system_field_is_warn_not_blocking(self):
        ok, issues = m6.validate_chapters_draft({"chapters": [ch(status="PENDING")]})
        self.assertTrue(ok)
        self.assertIn("ch.system-field", codes(issues))

    def test_long_chapter_warn(self):
        ok, issues = m6.validate_chapters_draft({"chapters": [ch(wordCnt=6000)]})
        self.assertTrue(ok)
        self.assertIn("ch.wordcnt-split", codes(issues))


class TestFinal(unittest.TestCase):
    def test_valid(self):
        ok, issues = m6.validate_chapters_final(tree())
        self.assertTrue(ok, issues)

    def test_bad_schema(self):
        ok, issues = m6.validate_chapters_final(tree(schema="x"))
        self.assertFalse(ok)
        self.assertIn("tree.schema", codes(issues))

    def test_bad_status(self):
        t = tree()
        t["chapters"][0]["status"] = "DONE"
        ok, issues = m6.validate_chapters_final(t)
        self.assertFalse(ok)
        self.assertIn("ch.status", codes(issues))

    def test_absolute_path(self):
        t = tree()
        t["chapters"][0]["files"]["body"] = "/tmp/ch-01.md"
        ok, issues = m6.validate_chapters_final(t)
        self.assertFalse(ok)
        self.assertIn("ch.files-path", codes(issues))

    def test_confirm_log_gate(self):
        ok, issues = m6.validate_chapters_final(tree(confirmLog=[{"gate": "bad", "at": "2026-10-21"}]))
        self.assertFalse(ok)
        self.assertIn("tree.confirmlog-gate", codes(issues))

    def test_dark_cover_rejected(self):
        t = tree(bidMode="暗标")
        t["layout"]["cover"] = "image-underlay"
        ok, issues = m6.validate_chapters_final(t)
        self.assertFalse(ok)
        self.assertIn("layout.mixcover", codes(issues))

    def test_unknown_layout_palette(self):
        t = tree()
        t["layout"]["palette"] = "pink"
        ok, issues = m6.validate_chapters_final(t)
        self.assertFalse(ok)
        self.assertIn("layout.unknown", codes(issues))


class TestCoverage(unittest.TestCase):
    def test_covered(self):
        res = m6.build_coverage([{"idx": 0, "item": "监理大纲（30分）", "weight": 30}], [ch()])
        self.assertTrue(res["ok"])
        self.assertEqual(res["rows"][0]["chapters"], ["ch-01"])
        self.assertGreaterEqual(res["rows"][0]["ratio"], 0.5)

    def test_missing(self):
        res = m6.build_coverage([{"idx": 0, "item": "监理大纲", "weight": 30}],
                                [ch(scoreRefs=[{"idx": 1, "item": "x"}])])
        self.assertFalse(res["ok"])
        self.assertEqual(res["rows"][0]["level"], "error")

    def test_weak(self):
        res = m6.build_coverage([{"idx": 0, "item": "监理大纲完整性与针对性（30分）"}],
                                [ch(keyPoints=["施工组织设计", "质量保证体系", "安全文明措施"])])
        self.assertTrue(res["ok"])  # 弱覆盖是 warn，不阻断
        self.assertEqual(res["rows"][0]["level"], "warn")
        self.assertTrue(res["rows"][0]["weak"])

    def test_non_outline_not_enforced(self):
        res = m6.build_coverage([{"idx": 0, "item": "报价分", "kind": "quote"}], [ch()])
        self.assertTrue(res["ok"])
        self.assertIsNone(res["rows"][0]["level"])

    def test_string_idx(self):
        res = m6.build_coverage([{"idx": 0, "item": "监理大纲"}],
                                [ch(scoreRefs=[{"idx": "0", "item": "监理大纲"}])])
        self.assertTrue(res["rows"][0]["covered"])


class TestLength(unittest.TestCase):
    def test_count_chars(self):
        md = "监理大纲\n\n| 项目 | 人数 |\n|---|---|\n| 总监 | 1 |\n"
        c = m6.count_chars(md)
        self.assertEqual(c["body_cjk"], 4)
        self.assertGreaterEqual(c["table_cjk"], 6)
        self.assertEqual(c["cjk"], c["body_cjk"] + c["table_cjk"])

    def test_estimate_pages(self):
        e = m6.estimate_pages(2000, 1000)
        self.assertEqual(e["pages"], 4)
        self.assertEqual(e["charsPerPage"], 1000)
        self.assertEqual(m6.estimate_pages(0, 0)["pages"], 0)

    def test_judge_over(self):
        self.assertEqual(m6.judge_pages(90, {"max": 80})["code"], "A3.over")
        self.assertEqual(m6.judge_pages(40, {"max": 80})["code"], "A3.short")
        self.assertIsNone(m6.judge_pages(60, {"max": 80}))
        self.assertIsNone(m6.judge_pages(60, None))


class TestSensitive(unittest.TestCase):
    def test_mingbiao_empty(self):
        self.assertEqual(m6.scan_sensitive("我公司 13800138000", {}, "明标"), [])

    def test_dark_hits(self):
        text = "我公司 张三 13800138000 test@x.com www.a.com logo"
        hits = m6.scan_sensitive(text, {"persons": ["张三"]}, "暗标")
        types = {h["type"] for h in hits}
        for t in ("自称", "人员姓名", "手机号", "邮箱", "网址", "标识词"):
            self.assertIn(t, types)
        self.assertTrue(all(h["level"] == "error" for h in hits))

    def test_with_name_mode(self):
        hits = m6.scan_sensitive("张三负责", {"persons": ["张三"], "personnelWriteMode": "with-name"}, "暗标")
        self.assertNotIn("人员姓名", {h["type"] for h in hits})

    def test_enterprise_name(self):
        hits = m6.scan_sensitive("由安徽某某工程咨询有限公司承担", {"enterprise_names": ["安徽某某工程咨询有限公司"]}, "暗标")
        self.assertIn("企业名称", {h["type"] for h in hits})


class TestConsistency(unittest.TestCase):
    def test_term_mixed(self):
        issues = m6.check_consistency("招标人要求，甲方负责", {}, [])
        self.assertIn("A5.term", codes(issues))

    def test_term_missing(self):
        issues = m6.check_consistency("甲方负责", {}, [])
        self.assertIn("A5.term-missing", codes(issues))

    def test_person_post_missing(self):
        issues = m6.check_consistency("张三负责现场", {}, [{"name": "张三", "post": "总监理工程师"}])
        self.assertIn("A5.person", codes(issues))

    def test_unknown_post(self):
        issues = m6.check_consistency("监理员负责旁站", {}, [{"name": "张三", "post": "总监理工程师"}])
        self.assertIn("A5.post", codes(issues))

    def test_clean(self):
        issues = m6.check_consistency("招标人要求总监理工程师张三到场",
                                      {}, [{"name": "张三", "post": "总监理工程师"}])
        self.assertEqual(issues, [])

    def test_dark_skips_name(self):
        issues = m6.check_consistency("张三负责", {}, [{"name": "张三", "post": "总监理工程师"}], "暗标")
        self.assertNotIn("A5.person", codes(issues))


class TestPlaceholders(unittest.TestCase):
    def test_hits(self):
        md = "{{待填:人员}}\nTODO\nXXX\n   \n正常"
        hits = m6.scan_placeholders(md)
        types = {h["type"] for h in hits}
        for t in ("待填", "TODO", "XXX", "空白段落"):
            self.assertIn(t, types)
        self.assertTrue(all(h["level"] == "warn" for h in hits))

    def test_clean(self):
        self.assertEqual(m6.scan_placeholders("正文正常，无残留。"), [])


class TestStateMachine(unittest.TestCase):
    def test_valid(self):
        self.assertTrue(m6.validate_transition("PENDING", "CONTEXT_READY")[0])
        self.assertTrue(m6.validate_transition("CHECKED", "CONFIRMED")[0])

    def test_invalid(self):
        ok, reason = m6.validate_transition("PENDING", "WRITTEN")
        self.assertFalse(ok)
        self.assertIn("非法迁移", reason)

    def test_unknown(self):
        self.assertFalse(m6.validate_transition("PENDING", "DONE")[0])
        self.assertFalse(m6.validate_transition("X", "PENDING")[0])

    def test_next_states(self):
        self.assertEqual(m6.next_states("WRITING"), ["WRITTEN", "FAILED"])
        self.assertEqual(m6.next_states("CONFIRMED"), ["WRITING", "FAILED"])


class TestSelfcheck(unittest.TestCase):
    def test_coverage_ok(self):
        md = ('正文\n<!-- M6-COVERAGE\n{"keyPoints": [{"point": "范围", "covered": true}],'
              ' "missingMaterials": [], "notes": ""}\n-->')
        info, err = m6.parse_selfcheck_block(md)
        self.assertEqual(err, "")
        self.assertEqual(info["block"], "M6-COVERAGE")

    def test_revise_ok(self):
        md = ('正文\n<!-- M6-REVISE\n{"changes": [{"where": "2.1"}], "untouched": "其余"}\n-->')
        info, err = m6.parse_selfcheck_block(md)
        self.assertEqual(err, "")
        self.assertEqual(info["block"], "M6-REVISE")

    def test_missing(self):
        info, err = m6.parse_selfcheck_block("正文")
        self.assertIsNone(info)
        self.assertIn("未找到", err)

    def test_bad_json(self):
        info, err = m6.parse_selfcheck_block("<!-- M6-COVERAGE {bad} -->")
        self.assertIsNone(info)
        self.assertIn("JSON", err)

    def test_duplicate_blocks(self):
        md = "<!-- M6-COVERAGE {} --><!-- M6-COVERAGE {} -->"
        info, err = m6.parse_selfcheck_block(md)
        self.assertIsNone(info)
        self.assertIn("多个", err)

    def test_strip(self):
        md = '正文\n<!-- M6-COVERAGE {"keyPoints": [], "missingMaterials": [], "notes": ""} -->\n'
        out = m6.strip_selfcheck_block(md)
        self.assertNotIn("M6-COVERAGE", out)
        self.assertTrue(out.startswith("正文"))


class TestCompareDual(unittest.TestCase):
    def test_coverage_conflict(self):
        cov = m6.build_coverage([{"idx": 0, "item": "监理大纲"}],
                                [ch(scoreRefs=[{"idx": 1, "item": "x"}])])
        diffs = m6.compare_dual({"coverage": cov},
                                {"ch-01": {"keyPoints": [{"point": "x", "covered": True}]}})
        self.assertIn("覆盖结论冲突", {d["type"] for d in diffs})

    def test_length_deviation(self):
        diffs = m6.compare_dual({"chapters": {"ch-01": {"chars": 1000}}},
                                {"ch-01": {"wordCnt": 1500, "keyPoints": [], "notes": ""}})
        self.assertIn("篇幅偏差", {d["type"] for d in diffs})

    def test_only_b(self):
        diffs = m6.compare_dual({"chapters": {"ch-01": {"chars": 1000, "sensitive": [], "placeholders": []}}},
                                {"ch-01": {"keyPoints": [], "notes": "招标要求模糊", "wordCnt": 1000}})
        self.assertIn("仅通道B发现项", {d["type"] for d in diffs})

    def test_only_a(self):
        diffs = m6.compare_dual(
            {"chapters": {"ch-01": {"chars": 1000, "sensitive": [{"text": "我公司", "type": "自称"}],
                                    "placeholders": []}}},
            {"ch-01": {"keyPoints": [], "notes": "", "wordCnt": 1000}})
        self.assertIn("仅通道A发现项", {d["type"] for d in diffs})


class TestLayout(unittest.TestCase):
    BASE = {"preset": "card", "palette": "pine-green",
            "cover": "line-white", "decoration": "克制",
            "font": "elegant-classic",
            "imageRatio": "mid", "imageRule": "hybrid", "imageLayout": "split-h",
            "pageSetup": "p1-standard-a4", "headingSystem": "h1-gbt-arabic",
            "tocStyle": "t1-jianyu-auto", "tableStyle": "tb1-three-line",
            "captionSystem": "c2-cy-chapter", "paragraphStyle": "pa7-jianyu-15",
            "headerFooter": "hf1-classic-enterprise"}

    def test_default_valid(self):
        ok, issues = m6.validate_layout(dict(self.BASE))
        self.assertTrue(ok, issues)

    def test_unknown(self):
        ok, issues = m6.validate_layout(dict(self.BASE, preset="x"))
        self.assertFalse(ok)
        self.assertIn("layout.unknown", codes(issues))

    def test_missing(self):
        ok, issues = m6.validate_layout({"preset": "card"})
        self.assertFalse(ok)
        self.assertIn("layout.missing", codes(issues))
        self.assertTrue(any("layout.font" in i.get("message", "") for i in issues))

    def test_custom_presets(self):
        presets = {"presets": ["only"], "palettes": ["p1"], "covers": ["c1"],
                   "decorations": ["d1"], "fonts": ["f1"],
                   "imageRatios": ["r1"], "imageRules": ["ru1"], "imageLayouts": ["l1"],
                   "pageSetups": ["ps1"], "headingSystems": ["hs1"], "tocStyles": ["tc1"],
                   "tableStyles": ["ta1"], "captionSystems": ["cs1"], "paragraphStyles": ["pa1"],
                   "headerFooters": ["hf1"]}
        ok, _ = m6.validate_layout({"preset": "only", "palette": "p1", "cover": "c1",
                                    "decoration": "d1", "font": "f1",
                                    "imageRatio": "r1", "imageRule": "ru1", "imageLayout": "l1",
                                    "pageSetup": "ps1", "headingSystem": "hs1", "tocStyle": "tc1",
                                    "tableStyle": "ta1", "captionSystem": "cs1", "paragraphStyle": "pa1",
                                    "headerFooter": "hf1"},
                                   presets)
        self.assertTrue(ok)
        ok, issues = m6.validate_layout({"preset": "card", "palette": "p1", "cover": "c1",
                                         "decoration": "d1", "font": "f1",
                                         "imageRatio": "r1", "imageRule": "ru1", "imageLayout": "l1",
                                         "pageSetup": "ps1", "headingSystem": "hs1", "tocStyle": "tc1",
                                         "tableStyle": "ta1", "captionSystem": "cs1", "paragraphStyle": "pa1",
                                         "headerFooter": "hf1"},
                                        presets)
        self.assertFalse(ok)

    def test_dark_image_cover(self):
        ok, issues = m6.validate_layout(dict(self.BASE, cover="image-underlay", font="dark-safe",
                                             headerFooter="hf9-dark-none"), None, "暗标")
        self.assertFalse(ok)
        self.assertIn("layout.mixcover", codes(issues))

    def test_dark_font_forced(self):
        ok, issues = m6.validate_layout(dict(self.BASE, font="gov-gongwen",
                                             headerFooter="hf9-dark-none"), None, "暗标")
        self.assertFalse(ok)
        self.assertIn("layout.mixfont", codes(issues))

    def test_dark_font_safe(self):
        ok, issues = m6.validate_layout(dict(self.BASE, font="dark-safe", palette="steel-cyan",
                                             decoration="minimal", imageRatio="none",
                                             headerFooter="hf9-dark-none"), None, "暗标")
        self.assertTrue(ok, issues)

    def test_dark_image_zero_ok(self):
        ok, issues = m6.validate_layout(dict(self.BASE, font="dark-safe", imageRatio="none",
                                             imageRule="hybrid", imageLayout="split-h",
                                             headerFooter="hf9-dark-none"), None, "暗标")
        self.assertTrue(ok, issues)

    def test_dark_image_safe_combo(self):
        ok, issues = m6.validate_layout(dict(self.BASE, font="dark-safe", imageRatio="mid",
                                             imageRule="dark-safe-img", imageLayout="appendix",
                                             headerFooter="hf9-dark-none"), None, "暗标")
        self.assertTrue(ok, issues)

    def test_dark_image_mix_rejected(self):
        ok, issues = m6.validate_layout(dict(self.BASE, font="dark-safe", imageRatio="mid",
                                             imageRule="hybrid", imageLayout="split-h",
                                             headerFooter="hf9-dark-none"), None, "暗标")
        self.assertFalse(ok)
        self.assertIn("layout.dark-image-mix", codes(issues))

    def test_dark_image_high_ratio_safe_combo(self):
        ok, issues = m6.validate_layout(dict(self.BASE, font="dark-safe", imageRatio="high",
                                             imageRule="dark-safe-img", imageLayout="appendix",
                                             headerFooter="hf9-dark-none"), None, "暗标")
        self.assertTrue(ok, issues)

    def test_image_ratio_chinese_alias(self):
        ok, issues = m6.validate_layout(dict(self.BASE, imageRatio="中图比"))
        self.assertTrue(ok, issues)

    def test_font_chinese_alias(self):
        ok, issues = m6.validate_layout(dict(self.BASE, font="政务公文风"))
        self.assertTrue(ok, issues)

    def test_overrides_warn(self):
        ok, issues = m6.validate_layout(dict(self.BASE, overrides={"bodyFont": "仿宋", "x": 1}))
        self.assertTrue(ok)
        self.assertIn("layout.overrides-key", codes(issues))

    def test_micro_missing(self):
        ok, issues = m6.validate_layout({"preset": "card"})
        self.assertFalse(ok)
        self.assertIn("layout.missing", codes(issues))

    def test_micro_chinese_alias(self):
        ok, issues = m6.validate_layout(dict(self.BASE, pageSetup="标准公文", headingSystem="GB阿拉伯",
                                             tocStyle="剑鱼目录", tableStyle="三线表",
                                             captionSystem="分章编号", paragraphStyle="剑鱼1.5倍"))
        self.assertTrue(ok, issues)

    def test_micro_unknown(self):
        ok, issues = m6.validate_layout(dict(self.BASE, tableStyle="神秘样式"))
        self.assertFalse(ok)
        self.assertIn("layout.unknown", codes(issues))
        self.assertTrue(any("tableStyle" in i.get("message", "") for i in issues))

    def test_micro_dark_headings_warn(self):
        ok, issues = m6.validate_layout(dict(self.BASE, font="dark-safe", imageRatio="none",
                                             headingSystem="h5-jianyu-bold",
                                             headerFooter="hf9-dark-none"), None, "暗标")
        self.assertTrue(ok)
        self.assertIn("layout.dark-heading", codes(issues))

    def test_micro_dark_headings_safe(self):
        ok, issues = m6.validate_layout(dict(self.BASE, font="dark-safe", imageRatio="none",
                                             headingSystem="h2-tender-arabic",
                                             captionSystem="c9-dark-appendix",
                                             headerFooter="hf9-dark-none"), None, "暗标")
        self.assertTrue(ok, issues)

    def test_micro_dark_caption_warn(self):
        ok, issues = m6.validate_layout(dict(self.BASE, font="dark-safe", imageRatio="mid",
                                             imageRule="dark-safe-img", imageLayout="appendix",
                                             headingSystem="h2-tender-arabic",
                                             captionSystem="c2-cy-chapter",
                                             headerFooter="hf9-dark-none"), None, "暗标")
        self.assertTrue(ok)
        self.assertIn("layout.dark-caption", codes(issues))

    def test_header_footer_chinese_alias(self):
        ok, issues = m6.validate_layout(dict(self.BASE, headerFooter="经典企业版"))
        self.assertTrue(ok, issues)

    def test_dark_header_footer_rejected(self):
        ok, issues = m6.validate_layout(dict(self.BASE, font="dark-safe", imageRatio="none",
                                             headerFooter="hf1-classic-enterprise"), None, "暗标")
        self.assertFalse(ok)
        self.assertIn("layout.dark-header-footer", codes(issues))

    def test_dark_header_footer_page_only_ok(self):
        ok, issues = m6.validate_layout(dict(self.BASE, font="dark-safe", imageRatio="none",
                                             headerFooter="hf10-dark-page-only"), None, "暗标")
        self.assertTrue(ok, issues)

    def test_dark_header_footer_none_ok(self):
        ok, issues = m6.validate_layout(dict(self.BASE, font="dark-safe", imageRatio="none",
                                             headerFooter="hf9-dark-none"), None, "暗标")
        self.assertTrue(ok, issues)


class TestDarkLayoutInject(unittest.TestCase):
    def test_inject_keys(self):
        from scripts.m6_tech.sources import DARK_LAYOUT_INJECT
        for k in ("font", "imageRatio", "pageSetup", "headingSystem", "tocStyle",
                  "tableStyle", "captionSystem", "paragraphStyle", "headerFooter"):
            self.assertIn(k, DARK_LAYOUT_INJECT)
        self.assertEqual(DARK_LAYOUT_INJECT["font"], "dark-safe")
        self.assertEqual(DARK_LAYOUT_INJECT["imageRatio"], "none")
        self.assertEqual(DARK_LAYOUT_INJECT["headerFooter"], "hf9-dark-none")

    def test_inject_values_valid(self):
        from m6_tech.sources import DARK_LAYOUT_INJECT
        from m6_tech.rules_base import DEFAULT_LAYOUT
        for k, v in DARK_LAYOUT_INJECT.items():
            self.assertIn(v, DEFAULT_LAYOUT[k], k)


if __name__ == "__main__":
    unittest.main()
