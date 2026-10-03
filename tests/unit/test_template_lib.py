# -*- coding: utf-8 -*-
"""L1 单元测试：M2 模板库存储层（台账读写 / docx 占位符扫描 / 导入校验）。"""
import json
import os
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "scripts"))
from _shared import core            # noqa: E402
from m2_template import template_lib as tl  # noqa: E402


def make_min_docx(path, text):
    """用 zipfile 构造最小 docx（含占位符文本），免第三方依赖。"""
    import xml.sax.saxutils as sx
    paras = "".join("<w:p><w:r><w:t>%s</w:t></w:r></w:p>" % sx.escape(p)
                    for p in text.split("\n"))
    doc = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        '<w:body>%s</w:body></w:document>' % paras
    )
    ct = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
          '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
          '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
          '<Default Extension="xml" ContentType="application/xml"/>'
          '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
          '</Types>')
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("[Content_Types].xml", ct)
        z.writestr("word/document.xml", doc)


class TemplateLibInit(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="bid_m2_unit_")
        self.ent = Path(self.tmp) / "测试监理有限公司"
        # 最小企业骨架（模板库目录）
        (self.ent / "企业级" / "模板库").mkdir(parents=True)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)


class TestScanDocx(TemplateLibInit):
    def test_placeholder_count(self):
        p = Path(self.tmp) / "t.docx"
        make_min_docx(p, "【项目名称】\n【图片：营业执照】\n投标函\n【投标人名称】")
        ph, img = tl.scan_docx_placeholders(p)
        self.assertEqual(ph, 3)
        self.assertEqual(img, 1)

    def test_placeholder_split_across_runs(self):
        """占位符被多个 <w:t> 拆开时也能统计（提取全部 w:t 后拼接）。"""
        p = Path(self.tmp) / "t2.docx"
        doc = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            '<w:body>'
            '<w:p><w:r><w:t>【图片：营</w:t></w:r><w:r><w:t>业执照】</w:t></w:r></w:p>'
            '</w:body></w:document>'
        )
        ct = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
              '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
              '<Default Extension="xml" ContentType="application/xml"/>'
              '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
              '</Types>')
        with zipfile.ZipFile(p, "w") as z:
            z.writestr("[Content_Types].xml", ct)
            z.writestr("word/document.xml", doc)
        ph, img = tl.scan_docx_placeholders(p)
        self.assertEqual((ph, img), (1, 1))

    def test_scan_unsupported_returns_none(self):
        self.assertIsNone(tl.scan_placeholders(Path(self.tmp) / "a.pdf"))


    def test_import_in_place(self):
        """登记库内已有文件（不复制）；重复登记报错。"""
        dst_dir = Path(self.ent) / "企业级" / "模板库" / "某代理" / "投标"
        dst_dir.mkdir(parents=True)
        existing = dst_dir / "承诺书.docx"
        make_min_docx(existing, "【项目名称】")
        row = tl.import_template(self.ent, "某代理", "投标", existing, in_place=True)
        self.assertEqual(row["占位符数"], "1")
        with self.assertRaises(core.LibraryError):
            tl.import_template(self.ent, "某代理", "投标", existing, in_place=True)
        # 非目标目录文件用 in_place 报错
        outside = Path(self.tmp) / "x.docx"
        make_min_docx(outside, "【项目名称】")
        with self.assertRaises(core.LibraryError):
            tl.import_template(self.ent, "某代理", "投标", outside, in_place=True)

    def test_sync_skips_registry_md(self):
        """登记清单文件本身不应被当作未登记新文件。"""
        dst_dir = Path(self.ent) / "企业级" / "模板库" / "某代理" / "投标"
        dst_dir.mkdir(parents=True)
        (dst_dir / tl.REGISTRY_MD).write_text("x", encoding="utf-8")
        res = tl.sync_templates(self.ent)
        self.assertEqual(res["new_files"], [])


class TestLedgerIO(TemplateLibInit):
    def test_save_load_roundtrip(self):
        ent = self.ent
        tl.save_ledger(ent, [tl.new_row("某代理", "投标", "开标一览表.docx",
                                        "企业级/模板库/某代理/投标/开标一览表.docx",
                                        ph=5, img_ph=1)])
        rows = tl.load_ledger(ent)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["代理机构"], "某代理")
        self.assertEqual(rows[0]["占位符数"], "5")
        # CSV 双写存在且可读回
        self.assertTrue((tl.template_root(ent) / tl.LEDGER_CSV).exists())
        rows2 = tl.load_ledger(ent)
        self.assertEqual(len(rows2), 1)
        self.assertEqual(rows2[0]["文件"], "开标一览表.docx")

    def test_init_ledger_idempotent(self):
        ent = self.ent
        existed, rows = tl.init_ledger(ent)
        self.assertFalse(existed)
        self.assertEqual(rows, [])
        existed, rows = tl.init_ledger(ent)
        self.assertTrue(existed)


class TestImportValidation(TemplateLibInit):
    def _src(self, name="t.docx", text="【项目名称】"):
        p = Path(self.tmp) / name
        make_min_docx(p, text)
        return p

    def test_import_ok(self):
        src = self._src()
        row = tl.import_template(self.ent, "大成工程咨询有限公司", "投标", src)
        self.assertEqual(row["代理机构"], "大成工程咨询有限公司")
        self.assertEqual(row["方式"], "投标")
        self.assertEqual(row["占位符数"], "1")
        dst = Path(self.ent) / "企业级" / "模板库" / "大成工程咨询有限公司" / "投标" / "t.docx"
        self.assertTrue(dst.exists())

    def test_import_bad_mode(self):
        with self.assertRaises(core.LibraryError):
            tl.import_template(self.ent, "某代理", "议标", self._src())

    def test_import_conflict(self):
        src = self._src()
        tl.import_template(self.ent, "某代理", "投标", src)
        with self.assertRaises(core.LibraryError):
            tl.import_template(self.ent, "某代理", "投标", src)

    def test_import_unsupported_requires_placeholders(self):
        src = Path(self.tmp) / "a.doc"
        src.write_bytes(b"fake old doc")
        with self.assertRaises(core.LibraryError):
            tl.import_template(self.ent, "某代理", "投标", src)
        row = tl.import_template(self.ent, "某代理", "投标", src,
                                 placeholders=7, img_placeholders=2)
        self.assertEqual(row["占位符数"], "7")
        self.assertEqual(row["图片占位符数"], "2")


class TestQuerySyncOverview(TemplateLibInit):
    def setUp(self):
        super().setUp()
        self.src1 = Path(self.tmp) / "开标一览表.docx"
        make_min_docx(self.src1, "【项目名称】\n【投标总价】")
        self.src2 = Path(self.tmp) / "投标函.docx"
        make_min_docx(self.src2, "【项目名称】")
        tl.import_template(self.ent, "A代理", "投标", self.src1, note="报价表")
        tl.import_template(self.ent, "A代理", "投标", self.src2)
        tl.import_template(self.ent, "B代理", "采购", self.src2)

    def test_list_filter(self):
        self.assertEqual(len(tl.list_templates(self.ent)), 3)
        self.assertEqual(len(tl.list_templates(self.ent, agency="A代理")), 2)
        self.assertEqual(len(tl.list_templates(self.ent, mode="采购")), 1)

    def test_query_keyword(self):
        rows = tl.query_templates(self.ent, keyword="开标一览表")
        self.assertEqual(len(rows), 1)
        rows = tl.query_templates(self.ent, agency="A代理", keyword="开标")
        self.assertEqual(len(rows), 1)

    def test_sync_detects_new_and_missing(self):
        # 直接放一个未登记文件
        (Path(self.ent) / "企业级" / "模板库" / "A代理" / "投标" / "承诺书.docx").write_bytes(b"x")
        res = tl.sync_templates(self.ent)
        self.assertEqual(len(res["new_files"]), 1)
        self.assertEqual(res["new_files"][0]["文件"], "承诺书.docx")
        # 删除一个已登记文件
        (Path(self.ent) / "企业级" / "模板库" / "B代理" / "采购" / "投标函.docx").unlink()
        res2 = tl.sync_templates(self.ent)
        self.assertEqual(len(res2["missing_rows"]), 1)
        self.assertIn("投标函.docx", res2["missing_rows"][0]["相对路径"])

    def test_overview(self):
        ov = tl.overview(self.ent)
        self.assertEqual(ov["ledger_total"], 3)
        self.assertEqual(ov["by_agency"]["A代理"]["投标"], 2)
        self.assertEqual(ov["by_agency"]["B代理"]["采购"], 1)

    def test_registry_read(self):
        reg_dir = Path(self.ent) / "企业级" / "模板库" / "A代理" / "投标"
        reg_dir.mkdir(parents=True, exist_ok=True)
        (reg_dir / tl.REGISTRY_MD).write_text(
            "## 开标一览表.docx\n|1|【项目名称】|项目名|\n## 投标函.docx\n|1|【项目名称】|项目名|",
            encoding="utf-8")
        r = tl.read_registry(self.ent, "A代理", "投标")
        self.assertTrue(r["exists"])
        self.assertIn("开标一览表", r["content"])
        r2 = tl.read_registry(self.ent, "A代理", "投标", file_filter="投标函")
        self.assertIn("投标函", r2["content"])
        self.assertNotIn("开标一览表", r2["content"])


if __name__ == "__main__":
    unittest.main()
