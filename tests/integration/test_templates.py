# -*- coding: utf-8 -*-
"""L2 集成测试：M2 模板库（真实企业骨架 + 存储层全链路：init→import→list→query→sync→overview→registry）。"""
import json
import os
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "scripts"))
from _shared import core                        # noqa: E402
from m2_template import template_lib as tl      # noqa: E402


def make_min_docx(path, text):
    import xml.sax.saxutils as sx
    paras = "".join("<w:p><w:r><w:t>%s</w:t></w:r></w:p>" % sx.escape(p)
                    for p in text.split("\n"))
    doc = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
           '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
           '<w:body>%s</w:body></w:document>' % paras)
    ct = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
          '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
          '<Default Extension="xml" ContentType="application/xml"/>'
          '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
          '</Types>')
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("[Content_Types].xml", ct)
        z.writestr("word/document.xml", doc)


ENT = "集成测试监理有限公司"


class TestTemplateLibFlow(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="bid_m2_int_")
        self.root = Path(self.tmp)
        self.ent = self.root / ENT
        lib = core.Library(self.root)
        lib.init_enterprise(ENT)          # 三层结构：企业级/素材库+模板库、项目级
        tl.init_ledger(self.ent)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_full_flow(self):
        # import 2 个模板（含图片占位）
        s1 = self.root / "开标一览表.docx"
        make_min_docx(s1, "【项目名称】\n【项目编号】\n【图片：营业执照】")
        s2 = self.root / "投标函.docx"
        make_min_docx(s2, "【项目名称】\n致招标人")
        r1 = tl.import_template(self.ent, "大成工程咨询有限公司", "投标", s1, note="报价表")
        r2 = tl.import_template(self.ent, "大成工程咨询有限公司", "投标", s2)
        self.assertEqual(r1["占位符数"], "3")
        self.assertEqual(r1["图片占位符数"], "1")

        # 台账 JSON/CSV 双份一致
        j = json.loads((tl.template_root(self.ent) / tl.LEDGER_JSON).read_text(encoding="utf-8"))
        self.assertEqual(len(j), 2)
        self.assertTrue((tl.template_root(self.ent) / tl.LEDGER_CSV).exists())

        # list / query / overview
        self.assertEqual(len(tl.list_templates(self.ent, agency="大成工程咨询有限公司")), 2)
        self.assertEqual(len(tl.query_templates(self.ent, keyword="开标一览表")), 1)
        ov = tl.overview(self.ent)
        self.assertEqual(ov["by_agency"]["大成工程咨询有限公司"]["投标"], 2)

        # registry 缺省文件：不存在时返回 exists=False
        r = tl.read_registry(self.ent, "大成工程咨询有限公司", "投标")
        self.assertFalse(r["exists"])

        # 写登记清单后按文件过滤读取
        reg_dir = Path(self.ent) / "企业级" / "模板库" / "大成工程咨询有限公司" / "投标"
        (reg_dir / tl.REGISTRY_MD).write_text(
            "## 开标一览表.docx\n|1|【项目名称】|项目名|\n|2|【项目编号】|项目编号|\n"
            "## 投标函.docx\n|1|【项目名称】|项目名|\n", encoding="utf-8")
        r2 = tl.read_registry(self.ent, "大成工程咨询有限公司", "投标", file_filter="投标函")
        self.assertIn("投标函", r2["content"])
        self.assertNotIn("开标一览表", r2["content"])

        # sync：新增未登记文件 + 移除已登记文件
        (reg_dir / "承诺书.docx").write_bytes(b"x")
        (reg_dir / "投标函.docx").unlink()
        res = tl.sync_templates(self.ent)
        self.assertTrue(any(f["文件"] == "承诺书.docx" for f in res["new_files"]))
        self.assertTrue(any("投标函.docx" in r.get("相对路径", "") for r in res["missing_rows"]))

    def test_bad_mode_exit(self):
        with self.assertRaises(core.LibraryError):
            tl.import_template(self.ent, "某代理", "议标", self.root / "x.docx")


if __name__ == "__main__":
    unittest.main()
