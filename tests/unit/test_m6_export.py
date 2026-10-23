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
from docx import Document  # noqa: E402


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

    # ---- 渲染层范式差异化（T11 试水：tabular / card / image-left）----
    def _tables_of(self, tech):
        from docx import Document
        doc = Document(str(tech / "产出" / "技术标_DEMO项目.docx"))
        return [t for t in doc.tables]

    def test_export_preset_tabular(self):
        """tabular：列表项转为序号/内容双列数据行，表格数 > 基准（md 表 2 个）。"""
        tech = _mk_project(self.tmp, dark=False)
        code = export.cmd_tech_export(_A(self.tmp, override="preset=tabular"))
        self.assertEqual(code, 0)
        tables = self._tables_of(tech)
        self.assertGreater(len(tables), 2, "tabular 应把列表转为数据行表")
        self.assertTrue(any(len(t.columns) == 2 for t in tables), "应有双列数据行表")

    def test_export_preset_card(self):
        """card：列表项转为单列卡片（全边框 + 底纹），存在 1 列表格。"""
        tech = _mk_project(self.tmp, dark=False)
        code = export.cmd_tech_export(_A(self.tmp, override="preset=card"))
        self.assertEqual(code, 0)
        tables = self._tables_of(tech)
        self.assertGreater(len(tables), 2)
        self.assertTrue(any(len(t.columns) == 1 for t in tables), "应有单列卡片表")

    def test_export_preset_image_left_degrade(self):
        """image-left：fixture 无图时安全降级单栏，导出正常且表格数 = 基准。"""
        tech = _mk_project(self.tmp, dark=False)
        code = export.cmd_tech_export(_A(self.tmp, override="preset=image-left"))
        self.assertEqual(code, 0)
        tables = self._tables_of(tech)
        self.assertEqual(len(tables), 2, "无图时应保持 md 表格数（降级不引入额外表）")

    def test_export_anbiao_forces_single_column(self):
        """暗标强制单栏：override preset=tabular 也不得引入数据行表（渲染层兜底）。"""
        tech = _mk_project(self.tmp, dark=True)
        code = export.cmd_tech_export(_A(self.tmp, override="preset=tabular"))
        self.assertEqual(code, 0)
        tables = self._tables_of(tech)
        self.assertEqual(len(tables), 2, "暗标必须保持单栏，列表不得转表")
        meta = json.loads((tech / "章节" / ".meta" / "export.json").read_text(encoding="utf-8"))
        self.assertTrue(meta["dark"])

    # ---- 铺开 7 范式（two-column/divider/data-row/image-right/hybrid-flow/minimal-clean/表格化增强）----
    def test_export_preset_two_column(self):
        """two-column：正文节 w:cols num=2，节数 ≥2。"""
        from docx.oxml.ns import qn as _qn
        tech = _mk_project(self.tmp, dark=False)
        code = export.cmd_tech_export(_A(self.tmp, override="preset=two-column"))
        self.assertEqual(code, 0)
        doc = Document(str(tech / "产出" / "技术标_DEMO项目.docx"))
        secs = doc.sections
        self.assertGreaterEqual(len(secs), 2, "two-column 必须有正文新节")
        last_cols = secs[-1]._sectPr.find(_qn("w:cols"))
        self.assertEqual(last_cols.get(_qn("w:num")), "2", "正文节必须双栏")
        first_cols = secs[0]._sectPr.find(_qn("w:cols"))
        self.assertTrue(first_cols is None or first_cols.get(_qn("w:num")) in (None, "1"),
                        "封面/目录节必须保持单栏")

    def test_export_preset_divider(self):
        """divider：至少 3 个章节标题带段落底边框（分隔页色条）+ outlineLvl 0。"""
        from docx.oxml.ns import qn as _qn
        tech = _mk_project(self.tmp, dark=False)
        code = export.cmd_tech_export(_A(self.tmp, override="preset=divider"))
        self.assertEqual(code, 0)
        doc = Document(str(tech / "产出" / "技术标_DEMO项目.docx"))
        hits = 0
        for p in doc.paragraphs:
            pPr = p._p.pPr
            if pPr is not None and pPr.find(_qn("w:pBdr")) is not None and p.text.startswith("第"):
                hits += 1
        self.assertGreaterEqual(hits, 2, "divider 章标题必须带分隔色条")

    def test_export_preset_data_row(self):
        """data-row：列表转数据行表（序号窄列 + 内容列），表格数 > 基准。"""
        tech = _mk_project(self.tmp, dark=False)
        code = export.cmd_tech_export(_A(self.tmp, override="preset=data-row"))
        self.assertEqual(code, 0)
        tables = self._tables_of(tech)
        self.assertGreater(len(tables), 2, "data-row 应把列表转为数据行表")
        self.assertTrue(any(len(t.columns) == 2 for t in tables), "应有双列数据行表")

    def test_export_preset_image_right_degrade(self):
        """image-right：fixture 无图时安全降级单栏，导出正常且表格数 = 基准。"""
        tech = _mk_project(self.tmp, dark=False)
        code = export.cmd_tech_export(_A(self.tmp, override="preset=image-right"))
        self.assertEqual(code, 0)
        tables = self._tables_of(tech)
        self.assertEqual(len(tables), 2, "无图时应保持 md 表格数（降级不引入额外表）")

    def test_export_preset_hybrid_flow(self):
        """hybrid-flow：列表保持段落散排（不转表），表格数 = 基准；一二级标题带左色条。"""
        from docx.oxml.ns import qn as _qn
        tech = _mk_project(self.tmp, dark=False)
        code = export.cmd_tech_export(_A(self.tmp, override="preset=hybrid-flow"))
        self.assertEqual(code, 0)
        doc = Document(str(tech / "产出" / "技术标_DEMO项目.docx"))
        self.assertEqual(len(doc.tables), 2, "hybrid-flow 列表必须散排，不引入数据行表")
        hits = 0
        for p in doc.paragraphs:
            pPr = p._p.pPr
            if pPr is not None:
                bdr = pPr.find(_qn("w:pBdr"))
                if bdr is not None and bdr.find(_qn("w:left")) is not None:
                    hits += 1
        self.assertGreaterEqual(hits, 1, "hybrid-flow 标题应有左侧色条")

    def test_export_preset_minimal_clean(self):
        """minimal-clean：列表不转表且无项目符号，表格数 = 基准；表头无深色底纹。"""
        from docx.oxml.ns import qn as _qn
        tech = _mk_project(self.tmp, dark=False)
        code = export.cmd_tech_export(_A(self.tmp, override="preset=minimal-clean"))
        self.assertEqual(code, 0)
        doc = Document(str(tech / "产出" / "技术标_DEMO项目.docx"))
        self.assertEqual(len(doc.tables), 2, "minimal-clean 列表必须保持段落")
        # 表头单元格无底纹（w:shd 缺省）
        head = doc.tables[0].rows[0].cells[0]._tc
        shd = head.find(_qn("w:tcPr")).find(_qn("w:shd")) if head.find(_qn("w:tcPr")) is not None else None
        self.assertTrue(shd is None or shd.get(_qn("w:fill")) in (None, "FFFFFF", "auto"),
                        "minimal-clean 表头不应有深色底纹")


class TechLayout12DimTest(unittest.TestCase):
    """12 维全面落实回归：标题编号 / 表格样式 / 封面 / 图宽映射 / 目录页码 / 页眉 / 背景 / 暗标合规。"""

    SAMPLE_IMG = REPO / "共享资源" / "技术标风格" / "样张素材" / "样张_施工现场全景.jpg"

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="t10_dim12_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def _mk_with_img(self, base=None):
        """fixture 正文首章插入一张真实样张图（用共享素材，缺失则跳过图片断言）。"""
        tech = _mk_project(base or self.tmp, dark=False)
        body_p = tech / "章节" / "ch-01" / "正文.md"
        if self.SAMPLE_IMG.is_file():
            img_line = "\n![施工现场全景](%s)\n" % self.SAMPLE_IMG
            body_p.write_text(body_p.read_text(encoding="utf-8") + img_line, encoding="utf-8")
        return tech

    def _run(self, tech, override=""):
        return export.cmd_tech_export(_A(self.tmp, override=override))

    def test_dim12_chapter_caption(self):
        """分章题注：c2 → 表1-1；c1 → 表1（全文连续）。"""
        tech = self._mk_with_img()
        self.assertEqual(self._run(tech), 0)
        texts = [p.text for p in Document(str(tech / "产出" / "技术标_DEMO项目.docx")).paragraphs]
        cap = [t for t in texts if t.startswith(("表", "图"))]
        self.assertTrue(any(t.startswith("表1-1") for t in cap), "c2 分章表题应为 表1-1，实际 %s" % cap[:3])
        self.assertTrue(any(t.startswith("图1-1") for t in cap), "c2 分章图题应为 图1-1，实际 %s" % cap[:3])
        tech2 = _mk_project(self.tmp / "seq", dark=False)
        export.cmd_tech_export(_A(self.tmp / "seq", project="DEMO项目",
                                  override="captionSystem=c1-gbt-seq"))
        texts2 = [p.text for p in Document(str((self.tmp / "seq" / "测试企业" / "项目级" / "DEMO项目" / "技术标") /
                                              "产出" / "技术标_DEMO项目.docx")).paragraphs]
        cap2 = [t for t in texts2 if t.startswith(("表", "图"))]
        self.assertTrue(any(t.startswith("表1") and not t.startswith("表1-") for t in cap2),
                        "c1 全文连续表题应为 表1，实际 %s" % cap2[:3])

    def test_dim12_table_header_fill(self):
        """表格样式：tb4 表头底纹存在；暗标无底纹。"""
        from docx.oxml.ns import qn as _qn
        tech = self._mk_with_img()
        self.assertEqual(self._run(tech, override="tableStyle=tb4-header-fill"), 0)
        doc = Document(str(tech / "产出" / "技术标_DEMO项目.docx"))
        head = doc.tables[0].rows[0].cells[0]._tc
        tcPr = head.find(_qn("w:tcPr"))
        shd = tcPr.find(_qn("w:shd")) if tcPr is not None else None
        self.assertIsNotNone(shd, "tb4 表头必须有底纹")
        self.assertNotIn(shd.get(_qn("w:fill")), (None, "FFFFFF", "auto"), "tb4 表头底纹应有配色")
        tech2 = _mk_project(self.tmp / "an", dark=True)
        export.cmd_tech_export(_A(self.tmp / "an", project="DEMO项目", override="tableStyle=tb4-header-fill"))
        doc2 = Document(str((self.tmp / "an" / "测试企业" / "项目级" / "DEMO项目" / "技术标") / "产出" /
                            "技术标_DEMO项目.docx"))
        xml2 = doc2.element.xml
        self.assertNotIn("<w:shd", xml2, "暗标不得有任何底纹")

    def test_dim12_cover_gradient(self):
        """封面方案：gradient 至少两个不同色块段；暗标无封面。"""
        tech = self._mk_with_img()
        self.assertEqual(self._run(tech, override="cover=gradient"), 0)
        xml = Document(str(tech / "产出" / "技术标_DEMO项目.docx")).element.xml
        fills = set()
        import re as _re
        for m in _re.findall(r'<w:shd[^>]*w:fill="([0-9A-Fa-f]{6})"', xml):
            fills.add(m)
        self.assertGreaterEqual(len(fills), 2, "gradient 封面至少两段色块，实际 %s" % sorted(fills))
        tech2 = _mk_project(self.tmp / "an", dark=True)
        export.cmd_tech_export(_A(self.tmp / "an", project="DEMO项目", override="cover=gradient"))
        doc2 = Document(str((self.tmp / "an" / "测试企业" / "项目级" / "DEMO项目" / "技术标") / "产出" /
                            "技术标_DEMO项目.docx"))
        self.assertFalse(doc2.paragraphs[0].text.startswith("投标技术标"), "暗标首段不得为封面标题")

    def test_dim12_image_width_map(self):
        """图宽映射：high=12cm / low=5cm / mid=9cm（EMU→cm）。"""
        if not self.SAMPLE_IMG.is_file():
            self.skipTest("样张素材缺失")
        import re as _re
        for ratio, exp in (("high", 12.0), ("low", 5.0), ("mid", 9.0)):
            tech = self._mk_with_img(self.tmp / ratio)
            export.cmd_tech_export(_A(self.tmp / ratio, project="DEMO项目", override="imageRatio=%s" % ratio))
            doc = Document(str((self.tmp / ratio / "测试企业" / "项目级" / "DEMO项目" / "技术标") / "产出" /
                               "技术标_DEMO项目.docx"))
            widths = [int(v) / 360000.0 for v in _re.findall(r'<wp:extent[^>]*cx="(\d+)"', doc.element.xml)]
            self.assertTrue(widths, "应存在图片")
            self.assertTrue(all(abs(w - exp) < 0.01 for w in widths),
                            "%s 图宽应为 %.1fcm，实际 %s" % (ratio, exp, widths))

    def test_dim12_toc_nopage(self):
        """目录无页码：t3 → TOC 域含 \\z 隐藏页码；t10 → 大纲级别 1-2。"""
        tech = self._mk_with_img()
        self.assertEqual(self._run(tech, override="tocStyle=t3-qinghai-nopage"), 0)
        instr = "".join(m.text for m in Document(str(tech / "产出" / "技术标_DEMO项目.docx")).element.iter(
            "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}instrText"))
        self.assertIn(r"\z", instr, "无页码目录必须带 \\z 开关")
        tech2 = _mk_project(self.tmp / "t10", dark=False)
        export.cmd_tech_export(_A(self.tmp / "t10", project="DEMO项目", override="tocStyle=t10-minimal-2level"))
        instr2 = "".join(m.text for m in Document(str((self.tmp / "t10" / "测试企业" / "项目级" / "DEMO项目" /
                                                       "技术标") / "产出" / "技术标_DEMO项目.docx")).element.iter(
            "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}instrText"))
        self.assertIn(r'"1-2"', instr2, "两级目录大纲级别应为 1-2")

    def test_dim12_header_center_and_background(self):
        """页眉居中（hf2）+ 装饰 rich 页面背景。"""
        from docx.oxml.ns import qn as _qn
        tech = self._mk_with_img()
        self.assertEqual(self._run(tech, override="headerFooter=hf2-centered-solemn;decoration=rich"), 0)
        doc = Document(str(tech / "产出" / "技术标_DEMO项目.docx"))
        hdr = doc.sections[0].header.paragraphs[0]
        self.assertEqual(hdr.alignment, 1, "hf2 页眉应居中（WD_ALIGN_PARAGRAPH.CENTER=1）")
        bg = doc.element.body.find(_qn("w:background"))
        self.assertIsNotNone(bg, "decoration=rich 必须有 w:background")

    def test_dim12_dark_no_chart_no_bold(self):
        """暗标无图、无加粗、无页眉；hf10 带页码双态。"""
        if not self.SAMPLE_IMG.is_file():
            self.skipTest("样张素材缺失")
        tech = _mk_project(self.tmp, dark=True)
        body_p = tech / "章节" / "ch-01" / "正文.md"
        if self.SAMPLE_IMG.is_file():
            body_p.write_text(body_p.read_text(encoding="utf-8") + "\n![施工现场全景](%s)\n" % self.SAMPLE_IMG,
                              encoding="utf-8")
        export.cmd_tech_export(_A(self.tmp, project="DEMO项目", bid_mode="暗标",
                                  override="imageRatio=high;headerFooter=hf10-dark-page-only"))
        doc = Document(str(tech / "产出" / "技术标_DEMO项目.docx"))
        xml = doc.element.xml
        import re as _re
        self.assertEqual(len(_re.findall(r"<w:drawing>", xml)), 0, "暗标不得渲染图片")
        self.assertEqual(len(_re.findall(r"<w:b/>|<w:b w:val=\"1\"/>", xml)), 0, "暗标不得有加粗")
        footer_parts = [p for p in tech.glob("产出/*.docx")][0]
        import zipfile
        z = zipfile.ZipFile(str(footer_parts))
        footers = [z.read(p).decode("utf-8", "ignore") for p in z.namelist() if p.startswith("word/footer")]
        self.assertTrue(footers and any("PAGE" in f for f in footers), "hf10 暗标应带页码")


if __name__ == "__main__":
    unittest.main(verbosity=2)
