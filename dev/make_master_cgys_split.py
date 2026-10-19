# -*- coding: utf-8 -*-
"""大成·采购式骨架母版拆件脚本 v2（zip 级：拆件+资源裁剪一步完成）。

背景：v1 用 python-docx save 重打包 37MB 大文件时 zip 损坏（Truncated file
header）。v2 改为直接操作 zip：读整本 zip → 修改 word/document.xml（按 body
子元素锚定章节区间，删除区间外 w:p/w:tbl）→ 按 document.xml 实际引用关系
裁剪 media/embeddings → 写新 zip。产物仅含本件章节内容与必要资源。

基准：和县垃圾资源化利用综合建设项目-和县建筑垃圾资源化利用中心建设项目
      \投标文件（无章版）.docx（2992 段/17 表/57 图）
以已完标书章节为准拆分 6 件（监理大纲技术标不制作）：
  封面 / 开标一览表 / 投标函 / 法定代表人身份证明 / 授权委托书 /
  资格证明及辅助资料表
"""
import re
import zipfile
from pathlib import Path
from lxml import etree

SRC = Path(r"E:\监理标书制作\和县建设工程监理有限公司\企业级\已完标书\和县垃圾资源化利用综合建设项目-和县建筑垃圾资源化利用中心建设项目\投标文件（无章版）.docx")
OUT_DIR = Path(r"E:\监理标书制作\和县建设工程监理有限公司\企业级\模板库\大成工程咨询有限公司\商务标母版-采购式")

NS_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS_R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
W_P = f"{{{NS_W}}}p"
W_TBL = f"{{{NS_W}}}tbl"
W_T = f"{{{NS_W}}}t"

PIECES = [
    ("封面.docx",                None,                              "开标一览表"),
    ("开标一览表.docx",          "开标一览表",                      "一、投标函及投标函附录"),
    ("投标函.docx",              "一、投标函及投标函附录",          "二、法人代表资格证明（格式）"),
    ("法定代表人身份证明.docx",  "二、法人代表资格证明（格式）",    "（二）授权委托书"),
    ("授权委托书.docx",          "（二）授权委托书",                "三、监理管理文件（监理大纲）"),
    ("资格证明及辅助资料表.docx", "四、资格证明及辅助资料表",         None),
]

ALWAYS_KEEP = {
    "[Content_Types].xml", "_rels/.rels",
    "word/document.xml", "word/styles.xml", "word/settings.xml",
    "word/fontTable.xml", "word/webSettings.xml",
    "docProps/core.xml", "docProps/app.xml", "word/theme/theme1.xml",
}


def para_text(el):
    return "".join(t.text or "" for t in el.iter(W_T)).strip()


def find_anchor(children, anchor):
    for idx, el in enumerate(children):
        if el.tag == W_P and para_text(el).startswith(anchor):
            return idx
    return None


def collect_r_ids(xml_bytes):
    root = etree.fromstring(xml_bytes)
    ids = set()
    for el in root.iter():
        for attr, val in el.attrib.items():
            if not val:
                continue
            # lxml 属性名为 Clark 格式 {ns}local，按 local 判定关系型属性
            local = attr.split("}")[-1] if attr.startswith("{") else attr
            if local in ("embed", "link", "id", "relid"):
                ids.add(val)
        if el.tag.endswith("Reference") or el.tag.endswith("hyperlink"):
            rid = el.get(f"{{{NS_R}}}id")
            if rid:
                ids.add(rid)
    return ids


def split_piece(zin, name, lo_anchor, hi_anchor):
    doc_xml = zin.read("word/document.xml")
    root = etree.fromstring(doc_xml)
    body = root.find(f"{{{NS_W}}}body")
    children = list(body)
    lo = find_anchor(children, lo_anchor) if lo_anchor else 0
    hi = find_anchor(children, hi_anchor) if hi_anchor else len(children)
    assert lo is not None and hi is not None and lo < hi, name
    removed = 0
    for idx, el in enumerate(children):
        if el.tag in (W_P, W_TBL) and not (lo <= idx < hi):
            body.remove(el)
            removed += 1
    new_doc_xml = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)

    # 引用裁剪
    used_ids = collect_r_ids(new_doc_xml)
    story_parts = [n for n in zin.namelist()
                   if re.match(r"word/(header|footer|footnotes|endnotes|comments)\d*\.xml", n)]
    for sp in story_parts:
        used_ids |= collect_r_ids(zin.read(sp))
    rels_name = "word/_rels/document.xml.rels"
    rels_root = etree.fromstring(zin.read(rels_name))
    rels_targets = {rel.get("Id"): rel.get("Target") for rel in rels_root}
    for rel in list(rels_root):
        if rel.get("Id") not in used_ids:
            rels_root.remove(rel)
    new_rels = etree.tostring(rels_root, xml_declaration=True, encoding="UTF-8", standalone=True)
    used_targets = {t for rid, t in rels_targets.items() if rid in used_ids}
    keep = set(ALWAYS_KEEP)
    for t in used_targets:
        if t.startswith("media/") or t.startswith("embeddings/") or t.startswith("charts/"):
            keep.add("word/" + t)
        elif t.startswith("/"):
            keep.add(t.lstrip("/"))
        else:
            keep.add("word/" + t)
    keep.add(rels_name)
    for sp in story_parts:
        keep.add(sp)
        rn = f"word/_rels/{sp.split('/')[-1]}.rels"
        if rn in zin.namelist():
            keep.add(rn)

    out_path = OUT_DIR / name
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zout:
        for n in zin.namelist():
            if n == "word/document.xml":
                zout.writestr(n, new_doc_xml)
            elif n == rels_name:
                zout.writestr(n, new_rels)
            elif n in keep:
                zout.writestr(n, zin.read(n))
    return removed, len(keep)


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    zin = zipfile.ZipFile(SRC, "r")
    for name, lo_anchor, hi_anchor in PIECES:
        removed, kept = split_piece(zin, name, lo_anchor, hi_anchor)
        size = (OUT_DIR / name).stat().st_size / 1024 / 1024
        print(f"{name}: 删除元素 {removed}，保留部件 {kept}，{size:.1f} MB")
    zin.close()
    print("拆件完成 ->", OUT_DIR)


if __name__ == "__main__":
    main()
