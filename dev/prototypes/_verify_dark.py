# -*- coding: utf-8 -*-
"""暗标回归：无封面/无图/无编号色/无装饰；hf10 可带页码 vs hf9 无页码。"""
import re
import sys
import tempfile
import zipfile
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, r"E:\bidcraft_skill\scripts")
from m6_tech import export, layout  # noqa: E402


def run_dark(hf_id):
    tmp = tempfile.TemporaryDirectory()
    try:
        ent = layout._builtin_preview_fixture(tmp.name)
        out_dir = ent / "项目级" / "预览项目" / "技术标" / "产出"
        export.cmd_tech_export(SimpleNamespace(
            root=tmp.name, enterprise="预览企业", project="预览项目",
            override="preset=single-column;font=gov-gongwen;imageRatio=mid;imageRule=photo-only;headerFooter=%s" % hf_id,
            bid_mode="1", out=str(out_dir), force=True))
        docx = out_dir / "技术标_预览项目.docx"
        return zipfile.ZipFile(str(docx))
    finally:
        try:
            tmp.cleanup()
        except Exception:
            pass


def inspect(hf_id):
    z = run_dark(hf_id)
    xml = z.read("word/document.xml").decode("utf-8", "ignore")
    imgs = len(re.findall(r"<w:drawing>", xml))
    shd = len(re.findall(r'<w:shd[^>]*w:fill="', xml))
    bold = len(re.findall(r'<w:b/>|<w:b w:val="1"/>', xml))
    heads = [m for m in re.findall(r"<w:t[^>]*>([^<]*)</w:t>", xml)
             if any(k in m for k in ("工程概况", "监理工作范围", "表", "图"))]
    footer_parts = [p for p in z.namelist() if p.startswith("word/footer")]
    footer_page = False
    for p in footer_parts:
        fx = z.read(p).decode("utf-8", "ignore")
        if "PAGE" in fx:
            footer_page = True
    print("暗标[%s]: 图片=%d 底纹=%d 加粗run=%d 页脚部件=%d 页脚含PAGE域=%s"
          % (hf_id, imgs, shd, bold, len(footer_parts), footer_page))
    print("   文本样本:", heads[:8])


inspect("hf9-dark-none")
inspect("hf10-dark-page-only")
