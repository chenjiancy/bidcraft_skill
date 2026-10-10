# -*- coding: utf-8 -*-
"""⑦ generator · 企业模板入库（M5 前置③，2026-10-10）。

从「格式契约 JSON + 源 docx」把招标文件格式章节的空白格式提炼为
企业级空白模板，落盘 企业级/模板库/<代理机构>/投标/模板_<名称>.docx，
供后续同代理项目 proj-gen 直接引用（「企业模板内置·直接引用」机制化）。

模板粒度映射（对齐大成模板库命名）：
  F01         → 模板_封面.docx
  F02         → 模板_开标一览表.docx
  F03a/F03b   → 模板_投标函.docx / 模板_投标函附录.docx
  F04a/F04b   → 模板_法定代表人身份证明.docx / 模板_授权委托书.docx
  F05         → 模板_监理大纲.docx
  F06a..F06k  → 模板_资格证明及辅助资料表.docx（附表1-10 合并单文件，同大成粒度）
  F07         → 模板_承诺函_项目总监到岗.docx

空白模板语义：只做原文块深拷贝 + 跨包引用净化 + sectPr 归位，
不做任何占位符/素材填充——格式章节本身即空白格式（含下划线占位）。
"""
from pathlib import Path

from .gen_common import GenError, HAVE_DOCX, Document, qn
from .gen_blocks import _extract_blocks, _sanitize_copy
from .gen_text import _para_text

__all__ = ["import_templates", "TPL_NAME_MAP", "TPL_TARGET_DIR"]

TPL_TARGET_DIR = "投标"          # 模板库/<代理>/投标/

# 契约 id 列表 → 模板文件名（F06 系列合并；未列出的契约项跳过）
TPL_NAME_MAP = [
    (["F01"], "模板_封面.docx"),
    (["F02"], "模板_开标一览表.docx"),
    (["F03a"], "模板_投标函.docx"),
    (["F03b"], "模板_投标函附录.docx"),
    (["F04a"], "模板_法定代表人身份证明.docx"),
    (["F04b"], "模板_授权委托书.docx"),
    (["F05"], "模板_监理大纲.docx"),
    (["F06a", "F06b", "F06c", "F06d", "F06e", "F06f",
      "F06g", "F06h", "F06i", "F06j", "F06k"], "模板_资格证明及辅助资料表.docx"),
    (["F07"], "模板_承诺函_项目总监到岗.docx"),
]


def _build_blank_docx(blocks, span, out_path):
    """纯净提取：深拷贝块 [s,e] → 空白 docx（不填占位符）。"""
    doc = Document()
    s, e = span
    for i in range(s, e + 1):
        blk = blocks[i]
        if blk["type"] == "para":
            doc.element.body.append(_sanitize_copy(blk["node"]))
        else:
            doc.element.body.append(_sanitize_copy(blk["node"]))
    body_el = doc.element.body
    sp_el = body_el.find(qn("w:sectPr"))
    if sp_el is not None:
        body_el.remove(sp_el)
        body_el.append(sp_el)
    doc.save(out_path)


def import_templates(ent, project, agent, source=None, out_dir=None):
    """把项目格式契约对应空白格式入库为企业级模板。

    返回 {"模板目录": ..., "文件": [{"模板", "契约项", "块范围", "段落数"}], "跳过": [...]}
    """
    if not HAVE_DOCX:
        raise GenError("生成器依赖 python-docx，当前环境未安装")
    import json
    from _shared import core

    proj_dir = Path(ent) / "项目级" / project
    if not proj_dir.is_dir():
        raise GenError("项目目录不存在：项目级/%s" % project)
    contract_path = proj_dir / "招标解析" / "格式契约" / "格式契约.json"
    if not contract_path.is_file():
        raise GenError("找不到格式契约：%s（先运行 proj-contract）" % contract_path)
    contract = core.read_json(contract_path)
    if not source:
        from .gen_paths import _default_source_docx
        source = _default_source_docx(proj_dir)
    src = Path(source)
    if not src.is_file():
        raise GenError("源文件不存在：%s" % src)

    blocks, _ = _extract_blocks(src)
    by_id = {it["id"]: it for it in contract.get("格式文件", [])}
    out = Path(out_dir) if out_dir else \
        Path(ent) / "企业级" / "模板库" / agent / TPL_TARGET_DIR
    out.mkdir(parents=True, exist_ok=True)

    files, skipped = [], []
    for ids, fname in TPL_NAME_MAP:
        spans = [by_id[c]["块范围"] for c in ids if c in by_id and by_id[c]["块范围"]]
        if not spans:
            skipped.append({"模板": fname, "契约项": ",".join(ids), "原因": "契约未定位"})
            continue
        lo = min(s[0] for s in spans)
        hi = max(s[1] for s in spans)
        target = out / fname
        _build_blank_docx(blocks, (lo, hi), target)
        files.append({
            "模板": fname, "契约项": ",".join(ids),
            "块范围": [lo, hi], "段落数": sum(1 for i in range(lo, hi + 1)
                                          if blocks[i]["type"] == "para"),
        })
    return {"模板目录": str(out), "文件": files, "跳过": skipped}
