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

REAL_ENT = r"E:\监理标书制作\和县建设工程监理有限公司"
REAL_PROJECT = "马鞍山和县化工园尾水水质提升工程（EPC总承包）监理"


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
        if not Path(REAL_ENT).is_dir():
            raise unittest.SkipTest("真实企业目录不存在")
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
                     "投标保证金材料.docx", "基本账户开户许可证承诺函.docx",
                     "中小企业声明函.docx"]:
            self.assertIn(want, names, "缺少生成文件：%s" % want)

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
        # 投标文件附录 预付款行（列表型表：序号|项目|内容）
        p3 = Path(self.res["目录"]) / "投标函附录.docx"
        doc3 = Document(str(p3))
        t3 = [c.text for t in doc3.tables for r in t.rows for c in r.cells]
        self.assertTrue(any("合同价款的【预付款比例（%）】" in x for x in t3),
                        "投标文件附录预付款行未按模板库键【预付款比例（%）】占位")
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
        # 封面：投标人名称/签字或盖章/日期
        doc = Document(str(d / "封面.docx"))
        full = "\n".join(p.text for p in doc.paragraphs)
        for want in ["【投标人名称】", "【签字或盖章】", "【日期】"]:
            self.assertIn(want, full, "封面缺模板库键 %s" % want)
        # 法代：法定代表人姓名/单位性质/成立时间（模板库把 年 月 日 替换为键）
        doc = Document(str(d / "法定代表人身份证明.docx"))
        full = "\n".join(p.text for p in doc.paragraphs)
        self.assertIn("【法定代表人姓名】", full)
        self.assertIn("【单位性质】", full)
        self.assertIn("【成立时间】", full)
        # 授权委托书：授权代理人姓名/身份证号/图片占位
        doc = Document(str(d / "授权委托书.docx"))
        full = "\n".join(p.text for p in doc.paragraphs)
        self.assertIn("【授权代理人姓名】", full)
        self.assertIn("【图片：委托代理人身份证正、反面扫描件】", full)
        # 图片占位：资格证明含【图片：xxx】（模板库同款键）
        doc = Document(str(d / "资格证明及辅助资料表.docx"))
        full = "\n".join(p.text for p in doc.paragraphs) + "\n" + \
            "\n".join(c.text for t in doc.tables for r in t.rows for c in r.cells)
        for want in ["【图片：组织机构框图（含结构、领导成员、主要技术人员、管理人员及数量）】",
                     "【图片：总监理工程师注册执业证书扫描件】",
                     "【图片：三体系认证证书】",
                     "【图片：先进（优秀）监理企业证书】"]:
            self.assertIn(want, full, "资格证明缺图片占位 %s" % want)
        # 承诺函/开户承诺函图片占位
        doc = Document(str(d / "承诺函_项目总监到岗.docx"))
        full = "\n".join(p.text for p in doc.paragraphs)
        self.assertIn("【图片：项目总监到岗承诺相关材料】", full)
        doc = Document(str(d / "基本账户开户许可证承诺函.docx"))
        full = "\n".join(p.text for p in doc.paragraphs)
        self.assertIn("【图片：基本账户开户许可证（或基本账户存款信息）扫描件】", full)

    def test_dynamic_form_count(self):
        """动态语义②：附表8 简历表 6 份（素材 6 人）→ 识别：首行含『出生年月』的 11 列表。"""
        from docx import Document
        p = Path(self.res["目录"]) / "资格证明及辅助资料表.docx"
        doc = Document(str(p))
        n_resume = sum(1 for t in doc.tables
                       if "出生年月" in "".join(c.text for c in t.rows[0].cells)
                       and len(t.rows) >= 11)
        self.assertGreaterEqual(n_resume, 6, "简历表份数应≥素材人数6，实际 %d" % n_resume)

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


if __name__ == "__main__":
    unittest.main()
