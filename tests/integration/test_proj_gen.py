# -*- coding: utf-8 -*-
"""L2 集成测试：M5 项目模板生成器（真实契约+素材清单+招标文件 → 项目模板）。

说明：
- 输出到临时目录（不覆盖真实项目模板目录），register_baseline=False（不污染真实基线）；
- 依赖 python-docx（真实环境已装；缺依赖时整组 skip）。
"""
import json
import os
import shutil
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "scripts"))
from m5_project import generator as gen           # noqa: E402

# 真实数据路径：默认示例名（公网安全）；本地真实回归通过环境变量注入（同 test_m5_filler）。
REAL_ENT = os.environ.get("BIDCRAFT_TEST_ENT", r"E:\监理标书制作\示例建设工程监理有限公司")
REAL_PROJECT = os.environ.get("BIDCRAFT_TEST_PROJ", "示例化工园尾水水质提升工程（EPC总承包）监理")


def _have_docx():
    try:
        import docx  # noqa: F401
        return True
    except Exception:
        return False


@unittest.skipUnless(_have_docx(), "依赖 python-docx，未安装则跳过")
class TestProjGenReal(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="bid_m5_int_")
        # ⑫ 数据前置细化：generate 需要招标解析（格式契约+素材清单+招标文件）作为输入，
        # 仅检查企业根目录不够——数据被清除/未生成时应跳过而非在生成器里报错。
        proj = Path(REAL_ENT) / "项目级" / REAL_PROJECT
        contract = proj / "招标解析" / "格式契约" / "格式契约_第五章_投标文件格式.json"
        if not (contract.is_file() and (proj / "招标解析" / "素材清单.json").is_file()):
            raise unittest.SkipTest("真实项目数据不存在（格式契约/素材清单缺失），跳过真实数据生成测试")
        cls.res = gen.generate(
            Path(REAL_ENT), REAL_PROJECT,
            out_dir=Path(cls.tmp) / "项目模板", register_baseline=False,
        )

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_output_dir_and_records(self):
        d = Path(self.res["目录"])
        self.assertTrue(d.is_dir())
        self.assertTrue((d / "生成记录.json").is_file())
        self.assertTrue((d / "项目占位符清单.md").is_file())

    def test_expected_files(self):
        names = {f["文件"] for f in self.res["文件"]}
        for want in ["封面.docx", "开标一览表.docx", "投标函.docx", "投标函附录.docx",
                     "法定代表人身份证明.docx", "授权委托书.docx",
                     "资格证明及辅助资料表.docx", "承诺函_项目总监到岗.docx",
                     "基本账户开户许可证承诺函.docx", "中小企业声明函.docx"]:
            self.assertIn(want, names, "缺少生成文件：%s" % want)
        self.assertNotIn("投标保证金材料.docx", names, "范本 v1.1：投标保证金材料不再生成")

    def test_skipped_technical_bid(self):
        reasons = {s["契约项"]: s["原因"] for s in self.res["未生成"]}
        self.assertIn("F05", reasons)
        self.assertIn("技术标", reasons["F05"])

    def test_each_docx_opens(self):
        from docx import Document
        for f in self.res["文件"]:
            p = Path(self.res["目录"]) / f["文件"]
            self.assertTrue(p.is_file(), f["文件"])
            with zipfile.ZipFile(p) as z:
                self.assertIn("word/document.xml", z.namelist())
            Document(str(p))                      # python-docx 可打开

    def test_body_sectpr_last(self):
        """规范化：w:sectPr 必须是 body 最后一个子元素（否则 Word 报「文件可能已经损坏」）。"""
        from docx import Document
        from docx.oxml.ns import qn
        for f in self.res["文件"]:
            p = Path(self.res["目录"]) / f["文件"]
            doc = Document(str(p))
            kids = list(doc.element.body)
            self.assertEqual(kids[-1].tag, qn("w:sectPr"),
                             "%s body 末尾应为 sectPr（实际 %s）" % (f["文件"], kids[-1].tag))

    def test_no_dangling_rel_refs(self):
        """清理跨包引用：模板内所有 r:embed/r:id/r:link 必须能在 rels 中解析，
        且不得残留 footerReference/headerReference（悬空引用 → Word 报文件损坏）。
        原文示例图（w:drawing/w:object/w:pict）已被移除，预览框图（docPr@descr=IMG_PH:*）合法保留。"""
        import re as _re
        from docx import Document
        RNS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
        for f in self.res["文件"]:
            p = Path(self.res["目录"]) / f["文件"]
            with zipfile.ZipFile(p) as z:
                rels_xml = z.read("word/_rels/document.xml.rels").decode("utf-8")
                xml = z.read("word/document.xml").decode("utf-8")
            valid = set(_re.findall(r'Id="(rId\d+)"', rels_xml))
            # 文档内引用的所有关系 id
            used = set(_re.findall(r'r:(?:embed|id|link)="(rId\d+)"', xml))
            self.assertLessEqual(used, valid, "%s 存在悬空关系引用 %s" % (f["文件"], used - valid))
            self.assertNotIn("footerReference", xml, "%s 残留页脚引用" % f["文件"])
            self.assertNotIn("headerReference", xml, "%s 残留页眉引用" % f["文件"])
            # 深拷贝的原文示例图应被移除；带 IMG_PH 标记的预览框图合法保留
            doc = Document(str(p))
            for el in doc.element.body.iter():
                tag = el.tag.split("}")[-1]
                if tag in ("drawing", "object", "pict"):
                    is_preview = any(
                        d.get("descr", "").startswith("IMG_PH:")
                        for d in el.iter()
                        if d.tag.split("}")[-1] == "docPr")
                    self.assertTrue(is_preview,
                                    "%s 残留非预览原文示例图 %s" % (f["文件"], tag))
            for el in doc.element.body.iter():
                for attr in (RNS + "embed", RNS + "id", RNS + "link"):
                    rid = el.attrib.get(attr)
                    if rid:
                        self.assertIn(rid, valid, "%s 悬空 %s=%s" % (f["文件"], attr, rid))

    def test_contract_text_faithful(self):
        """文字以契约为准：开标一览表报价行被占位（原文其余部分保留）。"""
        from docx import Document
        p = Path(self.res["目录"]) / "开标一览表.docx"
        doc = Document(str(p))
        texts = [c.text for t in doc.tables for r in t.rows for c in r.cells]
        self.assertTrue(any("本项目的监理费用投标报价为【投标总价（元）】元" in t for t in texts),
                        "开标一览表报价行未正确占位")
        # 总监行姓名/专业占位
        self.assertTrue(any("姓名【总监姓名】" in t and "专业【总监专业】" in t for t in texts),
                        "开标一览表总监行未正确占位")
        # 投标文件附录 预付款行（范本 v1.1：不再占位，恢复原文「合同价款的  /   %」）
        p3 = Path(self.res["目录"]) / "投标函附录.docx"
        doc3 = Document(str(p3))
        t3 = [c.text for t in doc3.tables for r in t.rows for c in r.cells]
        self.assertTrue(any("合同价款的" in x and "/" in x for x in t3),
                        "投标文件附录预付款行应保留原文「合同价款的  /   %」")
        self.assertFalse(any("【预付款比例（%）】" in x for x in t3),
                         "范本 v1.1：投标函附录预付款行不占位")
        # 投标函含项目名称占位
        p2 = Path(self.res["目录"]) / "投标函.docx"
        doc2 = Document(str(p2))
        full = "\n".join(p.text for p in doc2.paragraphs)
        self.assertIn("【项目名称】", full)

    def test_placeholder_keys_aligned_with_tpl_lib(self):
        """占位键名/日期/图片占位参照模板库登记清单。"""
        from docx import Document
        d = Path(self.res["目录"])
        # 投标函：招标人/保证金大写/落款地址邮编等（模板库同款键）
        doc = Document(str(d / "投标函.docx"))
        full = "\n".join(p.text for p in doc.paragraphs)
        for want in ["【招标人】", "【投标保证金金额（大写）】", "【投标人名称】",
                     "【签字或盖章】", "【企业地址】", "【邮编】", "【联系电话】",
                     "【传真】", "【开户银行】", "【开户账号】", "【日期】"]:
            self.assertIn(want, full, "投标函缺模板库键 %s" % want)
        # 封面（范本 v1.1：标题两行【项目名称】+【项目编号】；落款不填投标人名称/签字或盖章）
        doc = Document(str(d / "封面.docx"))
        full = "\n".join(p.text for p in doc.paragraphs)
        for want in ["【项目名称】", "【项目编号】", "【日期】"]:
            self.assertIn(want, full, "封面缺模板库键 %s" % want)
        self.assertNotIn("【投标人名称】", full, "范本 v1.1：封面落款不填【投标人名称】")
        self.assertNotIn("【签字或盖章】", full, "范本 v1.1：封面落款不填【签字或盖章】")
        # 法代：法定代表人姓名/单位性质/成立时间（范本 v1.1：成立时间行只留【成立时间】，无「年 月 日」）
        doc = Document(str(d / "法定代表人身份证明.docx"))
        full = "\n".join(p.text for p in doc.paragraphs)
        self.assertIn("【法定代表人姓名】", full)
        self.assertIn("【单位性质】", full)
        self.assertIn("成立时间：【成立时间】", full)
        # 授权委托书（范本 v1.1：授权代理人信息拆 4 行；落款【授权代理人姓名】不填）
        doc = Document(str(d / "授权委托书.docx"))
        full = "\n".join(p.text for p in doc.paragraphs)
        self.assertIn("授权代理人：【授权代理人姓名】", full)
        self.assertIn("性别：【性别】", full)
        self.assertIn("年龄：【年龄】", full)
        self.assertIn("职务：【职务】", full)
        self.assertIn("【图片：委托代理人身份证正、反面扫描件】", full)
        self.assertNotIn("【授权代理人姓名】（签字或盖章）", full,
                         "范本 v1.1：授权委托书落款不填授权代理人姓名")
        # 图片占位：资格证明（范本 v1.1：附表10 后 5 张；附表8 后 1 张；不再含总监注册证/中级职称等）
        doc = Document(str(d / "资格证明及辅助资料表.docx"))
        full = "\n".join(p.text for p in doc.paragraphs) + "\n" + \
            "\n".join(c.text for t in doc.tables for r in t.rows for c in r.cells)
        for want in ["【图片：组织机构框图（含结构、领导成员、主要技术人员、管理人员及数量）】",
                     "【图片：三体系认证证书】",
                     "【图片：总监高级工程师职称证书】",
                     "【图片：其他监理人员职称证书】",
                     "【图片：先进（优秀）监理企业证书】",
                     "【图片：监理示范（优质）工程】",
                     "【图片：拟派监理人员注册证书、岗位证书、职称、身份证等证明材料】",
                     "【图片：拟投入监理人员社保证明】"]:
            self.assertIn(want, full, "资格证明缺图片占位 %s" % want)
        self.assertNotIn("【图片：总监理工程师注册执业证书扫描件】", full,
                         "范本 v1.1：资格证明不再含总监注册证图片占位")
        self.assertNotIn("【图片：项目总监到岗承诺相关材料】", full,
                         "范本 v1.1：资格证明不再含到岗承诺图片占位")
        # 承诺函/开户承诺函图片占位（范本 v1.1：承诺函不再含到岗材料图片占位）
        doc = Document(str(d / "承诺函_项目总监到岗.docx"))
        full = "\n".join(p.text for p in doc.paragraphs)
        self.assertNotIn("【图片：项目总监到岗承诺相关材料】", full,
                         "范本 v1.1：承诺函不再生成到岗材料图片占位")
        self.assertIn("3、若投标人在响应文件中承诺项目总监能够从其他项目变更", full,
                      "范本 v1.1：承诺函序号 2→3（纠正招标文件重复序号）")
        doc = Document(str(d / "基本账户开户许可证承诺函.docx"))
        full = "\n".join(p.text for p in doc.paragraphs)
        self.assertIn("【图片：基本账户开户许可证（或基本账户存款信息）扫描件】", full)
        # 中小企业声明函（范本 v1.1：项目名称/项目编号占位 + 默认示例值）
        doc = Document(str(d / "中小企业声明函.docx"))
        full = "\n".join(p.text for p in doc.paragraphs)
        for want in ["【项目名称】", "【项目编号】", "从业人员 62 人",
                     "营业收入为 493.43 万元", "资产总额为 134.59 万元", "属于小型企业"]:
            self.assertIn(want, full, "中小企业声明函缺范本内容 %s" % want)

    def test_image_placeholder_preview_boxes(self):
        """方案A v1.0：图片占位段后附灰底预览框（IMG_PH 标记，尺寸=image_spec 口径）。"""
        from docx import Document
        from docx.oxml.ns import qn
        from m5_project import ph_preview as phprev
        d = Path(self.res["目录"]) / "资格证明及辅助资料表.docx"
        doc = Document(str(d))

        def _markers(doc):
            m = {}
            for p in doc.paragraphs:
                for el in p._p.iter():
                    if el.tag.endswith("}docPr"):
                        descr = el.get("descr") or ""
                        if descr.startswith(phprev.PH_PREVIEW_PREFIX):
                            ext = el.getparent().find(qn("wp:extent"))
                            m[descr] = (int(ext.get("cx")) / 360000.0,
                                        int(ext.get("cy")) / 360000.0)
            return m

        markers = _markers(doc)
        self.assertGreaterEqual(len(markers), 6,
                                "资格证明应含≥6 个预览框，实际 %d" % len(markers))
        # 单图占位：三体系 16 宽 × 23 高 cm（与 image_spec 口径一致）
        key = phprev.PH_PREVIEW_PREFIX + "【图片：三体系认证证书】"
        self.assertIn(key, markers, "资格证明缺三体系预览框")
        w, h = markers[key]
        self.assertAlmostEqual(w, 16.0, delta=0.1)
        self.assertAlmostEqual(h, 23.0, delta=0.1)
        # 组合占位代表框：资质证书组 16 宽 × 12 高 cm
        key2 = phprev.PH_PREVIEW_PREFIX + "【图片：企业资质证书扫描件】"
        if key2 in markers:
            self.assertAlmostEqual(markers[key2][1], 12.0, delta=0.1)
        # 授权委托书：身份证预览框 8 宽 × 5 高 cm
        doc2 = Document(str(Path(self.res["目录"]) / "授权委托书.docx"))
        m2 = _markers(doc2)
        self.assertTrue(any("委托代理人身份证" in k for k in m2),
                        "授权委托书应含委托代理人身份证预览框")
        for k, (w2, h2) in m2.items():
            if "委托代理人身份证" in k:
                self.assertAlmostEqual(w2, 8.0, delta=0.1)
                self.assertAlmostEqual(h2, 5.0, delta=0.1)

    def test_dynamic_form_count(self):
        """动态语义②：附表8 简历表 6 份（素材 6 人）→ 识别：首行含『出生年月』的 11 列表。"""
        from docx import Document
        p = Path(self.res["目录"]) / "资格证明及辅助资料表.docx"
        doc = Document(str(p))
        n_resume = sum(1 for t in doc.tables
                       if "出生年月" in "".join(c.text for c in t.rows[0].cells)
                       and len(t.rows) >= 11)
        self.assertGreaterEqual(n_resume, 6, "简历表份数应≥素材人数6，实际 %d" % n_resume)

    def test_equip_table_from_tpl_lib(self):
        """范本 v1.2：附表9 仪器设备数据行从模板库带入（企业固定设备，直接写入模板）。"""
        from docx import Document
        p = Path(self.res["目录"]) / "资格证明及辅助资料表.docx"
        doc = Document(str(p))
        for t in doc.tables:
            first = "".join(c.text for c in t.rows[0].cells)
            if "仪器名称" in first:
                cells = [c.text for r in t.rows for c in r.cells]
                self.assertTrue(any("砼回弹仪" in x for x in cells),
                                "附表9 应含模板库设备数据（砼回弹仪）")
                self.assertTrue(any("水" in x and "准" in x for x in cells),
                                "附表9 应含水准仪")
                self.assertGreaterEqual(len(t.rows), 20,
                                        "附表9 应有 ≥20 行设备数据，实际 %d" % len(t.rows))
                break
        else:
            self.fail("未找到附表9 仪器设备表")

    def test_placeholder_manifest_nonempty(self):
        md = (Path(self.res["目录"]) / "项目占位符清单.md").read_text(encoding="utf-8")
        self.assertIn("开标一览表", md)
        self.assertIn("【项目名称】", md)

    def test_no_shading_and_font_aligned(self):
        """后处理：pPr/rPr 无文字底纹/高亮（图片占位框 pPr 的 F2F2F2 底纹除外）；
        run 字体 = FILE_FONT 映射（与模板库一致）。"""
        import re as _re
        for f in self.res["文件"]:
            p = Path(self.res["目录"]) / f["文件"]
            with zipfile.ZipFile(p) as z:
                xml = z.read("word/document.xml").decode("utf-8", errors="replace")
            # 段落/run 级无 shd/highlight；仅允许图片占位框样式 shd fill=F2F2F2
            pr_blocks = _re.findall(r"<w:pPr>.*?</w:pPr>|<w:rPr>.*?</w:rPr>", xml, flags=_re.S)
            for b in pr_blocks:
                if "<w:highlight" in b:
                    self.fail("%s 含文字高亮" % f["文件"])
                for m in _re.finditer(r"<w:shd[^/]*/>", b):
                    fill = _re.search(r'w:fill="([^"]*)"', m.group(0))
                    if not fill or fill.group(1).upper() != "F2F2F2":
                        self.fail("%s 含非图片占位框底纹：%s" % (f["文件"], m.group(0)))
            # run 字体统一为 FILE_FONT 映射
            font = gen.FILE_FONT.get(f["文件"])
            if not font:
                continue
            for rf in _re.findall(r"<w:rFonts[^/]*/>", xml):
                ea = _re.search(r'w:eastAsia="([^"]*)"', rf)
                self.assertEqual(ea.group(1) if ea else None, font,
                                 "%s 字体未对齐 %s" % (f["文件"], font))

    def test_gen_record_schema(self):
        rec = json.loads((Path(self.res["目录"]) / "生成记录.json").read_text(encoding="utf-8"))
        self.assertEqual(rec["项目"], REAL_PROJECT)
        self.assertIn("文件", rec)
        self.assertIn("未生成", rec)
        for f in rec["文件"]:
            self.assertIn("占位符数", f)


class TestGapGate(unittest.TestCase):
    """v2.6：proj-gen 素材缺口收口闸门（纯函数，临时目录，不依赖真实项目）。"""

    def _make_project(self, with_gap=False, statuses=("待补充",)):
        tmp = tempfile.mkdtemp(prefix="bid_m5_gap_")
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        proj = Path(tmp) / "项目级" / "缺口闸门测试项目"
        tdir = proj / "招标解析"
        tdir.mkdir(parents=True)
        if with_gap:
            items = [{"gap_id": "G%02d" % (i + 1), "item": "资料%d" % (i + 1),
                      "type": "text", "source": "投标要点", "status": st}
                     for i, st in enumerate(statuses)]
            (tdir / "素材缺口_缺口闸门测试项目.json").write_text(
                json.dumps({"project": "缺口闸门测试项目", "items": items},
                           ensure_ascii=False), encoding="utf-8")
        return proj

    def test_no_gap_file_passes(self):
        proj = self._make_project()
        ok, pending, gap_json = gen.check_gap_closed(proj, "缺口闸门测试项目")
        self.assertTrue(ok)
        self.assertEqual(pending, [])
        self.assertIsNone(gap_json)

    def test_all_resolved_passes(self):
        proj = self._make_project(with_gap=True, statuses=("已补充", "豁免"))
        ok, pending, _ = gen.check_gap_closed(proj, "缺口闸门测试项目")
        self.assertTrue(ok)
        self.assertEqual(pending, [])

    def test_pending_blocks(self):
        proj = self._make_project(with_gap=True, statuses=("已补充", "待补充", "豁免"))
        ok, pending, gap_json = gen.check_gap_closed(proj, "缺口闸门测试项目")
        self.assertFalse(ok)
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["gap_id"], "G02")
        self.assertIsNotNone(gap_json)

    def test_generate_raises_when_pending(self):
        """generate() 遇未收口缺口 → GenError（缺口清单存在且有待补充项）。"""
        proj = self._make_project(with_gap=True, statuses=("待补充",))
        from m5_project.gen_common import GenError
        with self.assertRaises(GenError) as ctx:
            gen.generate(proj.parent.parent, "缺口闸门测试项目")
        self.assertIn("素材缺口尚未收口", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
