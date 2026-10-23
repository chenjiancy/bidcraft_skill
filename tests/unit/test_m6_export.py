# -*- coding: utf-8 -*-
"""T10 tech-export 单元测试：fixture 迷你项目 → 导出 docx → 回读校验 + 页数回写（契约 §4 验收）。"""
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "scripts"))

REPO = Path(__file__).resolve().parents[2]
PRESETS_SRC = REPO / "共享资源" / "技术标风格" / "layout-presets.json"

from _shared import core  # noqa: E402

from m6_tech import export  # noqa: E402


def _ent(args):
    return core.Library(Path(args.root)).resolve(getattr(args, "enterprise", "测试企业"))

def _mk_project(root, dark=False):
    """在临时软件根下造：共享资源/技术标风格/layout-presets.json + <企业>/项目级/DEMO项目/技术标/..."""
    shared = root / "共享资源" / "技术标风格"
    shared.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(str(PRESETS_SRC), str(shared / "layout-presets.json"))
    ent = root / "测试企业"
    proj = ent / "项目级" / "DEMO项目"
    tech = proj / "技术标"
    for d in ("章节", "章节/.meta", "检查", "产出", "源文件"):
        (tech / d).mkdir(parents=True, exist_ok=True)
    (tech / "章节" / "ch-01").mkdir(parents=True, exist_ok=True)
    (tech / "章节" / "ch-02").mkdir(parents=True, exist_ok=True)
    # 章节树（含 files.body / layout）
    ch1 = {"id": "ch-01", "title": "第一章 工程概况与监理工作范围", "status": "WRITTEN",
           "files": {"body": "章节/ch-01/正文.md"}}
    ch2 = {"id": "ch-02", "title": "第二章 监理工作依据、目标与内容", "status": "WRITTEN",
           "files": {"body": "章节/ch-02/正文.md"}}
    layout = {"preset": "single-column", "palette": "deep-indigo", "cover": "full-block",
              "decoration": "standard", "font": "gov-gongwen", "imageRatio": "mid",
              "imageRule": "hybrid", "imageLayout": "split-h", "pageSetup": "p1-standard-a4",
              "headingSystem": "h1-gbt-arabic", "tocStyle": "t1-jianyu-auto",
              "tableStyle": "tb1-three-line", "captionSystem": "c2-cy-chapter",
              "paragraphStyle": "pa7-jianyu-15", "headerFooter": "hf1-classic-enterprise"}
    if dark:
        layout.update({"font": "dark-safe", "cover": "none", "decoration": "none",
                       "imageRatio": "none", "headerFooter": "hf9-dark-none"})
    tree = {"schema": "m6.tree/v1", "project": "DEMO项目", "layout": layout, "confirmed": True,
            "chapters": [ch1, ch2]}
    (tech / "章节树.json").write_text(json.dumps(tree, ensure_ascii=False), encoding="utf-8")
    body1 = (
        "# 一、工程概况\n"
        "本工程为市政务服务中心项目，总建筑面积约 8.6 万 m²，框架剪力墙结构。\n"
        "## （一）项目理解\n"
        "监理工作覆盖质量、进度、投资、安全环保与合同信息管理五大目标。\n"
        "- 质量控制：材料进场验收与旁站监理\n"
        "- 进度控制：总控计划动态纠偏\n"
        "| 序号 | 控制项 | 措施 |\n"
        "| --- | --- | --- |\n"
        "| 1 | 质量 | 三检制 |\n"
        "| 2 | 进度 | 周报纠偏 |\n"
        "### 1. 人员配置\n"
        "总监理工程师 1 名，专业监理工程师 4 名。\n"
    )
    body2 = (
        "# 一、监理依据\n"
        "依据《建设工程监理规范》GB/T 50319-2013 及招标文件。\n"
        "## （一）工作目标\n"
        "确保工程质量合格，争创省级优质工程。\n"
        "| 目标 | 要求 |\n"
        "| --- | --- |\n"
        "| 质量 | 一次验收合格率 100% |\n"
        "| 工期 | 满足合同节点 |\n"
        "### 1. 制度保障\n"
        "建立例会制度、旁站制度、见证取样制度。\n"
        "#### （1）例会制度\n"
        "每周监理例会，形成会议纪要闭环。\n"
    )
    (tech / "章节" / "ch-01" / "正文.md").write_text(body1, encoding="utf-8")
    (tech / "章节" / "ch-02" / "正文.md").write_text(body2, encoding="utf-8")
    ctx = {"schema": "m6.ctx/v1", "chapter": "ch-01", "project": "DEMO项目",
           "context": {"tender_points": ["暗标" if dark else "明标"], "pageBudget": 900}}
    (tech / "章节" / ".meta" / "ch-01.json").write_text(json.dumps(ctx, ensure_ascii=False), encoding="utf-8")
    (tech / "章节" / ".meta" / "ch-02.json").write_text(json.dumps(ctx, ensure_ascii=False), encoding="utf-8")
    return tech


class _A:
    def __init__(self, root, enterprise="测试企业", project="DEMO项目", override="", bid_mode="", out=""):
        self.root = str(root)
        self.enterprise = enterprise
        self.project = project
        self.override = override
        self.bid_mode = bid_mode
        self.out = out


class TechExportTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="t10_export_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def test_export_mingbiao(self):
        tech = _mk_project(self.tmp, dark=False)
        code = export.cmd_tech_export(_A(self.tmp))
        self.assertEqual(code, 0)
        out = tech / "产出" / "技术标_DEMO项目.docx"
        self.assertTrue(out.is_file(), "docx 未产出")
        from docx import Document
        doc = Document(str(out))
        self.assertGreater(len(doc.paragraphs), 0, "段落数必须 > 0")
        xml = doc.element.xml
        self.assertIn("TOC", xml, "目录域缺失")
        self.assertIn("fldChar", xml, "域字符缺失")
        meta = json.loads((tech / "章节" / ".meta" / "export.json").read_text(encoding="utf-8"))
        self.assertEqual(meta["schema"], "m6.export/v1")
        self.assertFalse(meta["dark"])
        self.assertGreater(meta["pages_estimate"], 0)
        self.assertEqual(meta["chapters"], 2)

    def test_export_anbiao(self):
        tech = _mk_project(self.tmp, dark=True)
        code = export.cmd_tech_export(_A(self.tmp))
        self.assertEqual(code, 0)
        out = tech / "产出" / "技术标_DEMO项目.docx"
        self.assertTrue(out.is_file())
        meta = json.loads((tech / "章节" / ".meta" / "export.json").read_text(encoding="utf-8"))
        self.assertTrue(meta["dark"])
        # 暗标强制：font=dark-safe / headerFooter=hf9 / 无封面（检查段落首段非封面标题）
        self.assertEqual(meta["layout"]["font"], "dark-safe")
        self.assertEqual(meta["layout"]["headerFooter"], "hf9-dark-none")

    def test_export_override_and_bid_page(self):
        tech = _mk_project(self.tmp, dark=False)
        # 明标覆盖 palette=steel-cyan + headerFooter 保留默认；再验证 --bid-mode 强制暗标 hf10 页码双态
        code = export.cmd_tech_export(_A(self.tmp, override="palette=steel-cyan;headerFooter=hf2-centered-solemn"))
        self.assertEqual(code, 0)
        meta = json.loads((tech / "章节" / ".meta" / "export.json").read_text(encoding="utf-8"))
        self.assertEqual(meta["layout"]["palette"], "steel-cyan")
        tech2 = _mk_project(self.tmp / "anbiao", dark=False)
        code = export.cmd_tech_export(_A(self.tmp / "anbiao", project="DEMO项目", bid_mode="暗标",
                                         override="headerFooter=hf10-dark-page-only"))
        self.assertEqual(code, 0)
        meta2 = json.loads((tech2 / "章节" / ".meta" / "export.json").read_text(encoding="utf-8"))
        self.assertTrue(meta2["dark"])
        self.assertEqual(meta2["layout"]["headerFooter"], "hf10-dark-page-only")

    def test_export_rejects_unconfirmed(self):
        tech = _mk_project(self.tmp, dark=False)
        tree_p = tech / "章节树.json"
        tree = json.loads(tree_p.read_text(encoding="utf-8"))
        tree["confirmed"] = False
        tree_p.write_text(json.dumps(tree, ensure_ascii=False), encoding="utf-8")
        with self.assertRaises(core.LibraryError):
            export.cmd_tech_export(_A(self.tmp))


if __name__ == "__main__":
    unittest.main(verbosity=2)
