# -*- coding: utf-8 -*-
"""⑦ generator 拆包 · 主流程（generate / 占位符清单 / 扫描）。"""
import json
import re
from pathlib import Path

from _shared import core
from m_feedback import feedback as fb

from .gen_common import (DATE_PH_FILES, FILE_FONT, FILE_MAP, GEN_ID, GEN_VERSION,
                         HAVE_DOCX, GenError, IMAGE_PH_AFTER_PARA,
                         IMAGE_PH_AFTER_TABLE, PARA_LABEL_RULES)
from .gen_blocks import build_docx, _extract_blocks
from .gen_paths import (_default_contract_path, _default_material_path,
                        _default_source_docx, _resolve_project_dir)
from .gen_tables import _extract_tpl_equip_rows

__all__ = ["generate", "_write_ph_manifest", "_scan_placeholders"]


def generate(ent, project, contract_path=None, material_path=None, source_path=None,
             out_dir=None, base_dir="", register_baseline=True):
    """
    主入口：
      1) 读契约 JSON / 素材清单 / 招标文件 docx；
      2) 按 FILE_MAP 生成各项目模板 docx（F06 合并为资格证明及辅助资料表.docx）；
      3) 生成记录.json + 项目占位符清单.md；
      4) 登记产物基线（fb.register）。
    返回 {"目录": ..., "文件": [...], "未生成": [...]}。
    """
    if not HAVE_DOCX:
        raise GenError("生成器依赖 python-docx，当前环境未安装")
    ent = Path(ent)
    proj_dir = _resolve_project_dir(ent, project)
    if proj_dir is None:
        raise GenError("项目目录不存在：项目级/%s" % project)
    contract_path = Path(contract_path or _default_contract_path(proj_dir))
    material_path = Path(material_path or _default_material_path(proj_dir))
    source_path = Path(source_path or _default_source_docx(proj_dir))

    contract = core.read_json(contract_path, None)
    if not contract or "格式文件" not in contract:
        raise GenError("格式契约 JSON 无『格式文件』清单：%s" % contract_path)
    material = core.read_json(material_path, None)
    if not material:
        raise GenError("素材清单 JSON 为空：%s" % material_path)

    out = Path(out_dir) if out_dir else proj_dir / "项目模板"
    out.mkdir(parents=True, exist_ok=True)

    # 范本 v1.2：从模板库提取附表9 仪器设备数据行（企业固定设备，直接写入项目模板）
    tpl_equip_rows = []
    agency = material.get("招标代理机构", "")
    mode = material.get("采购方式", "投标") or "投标"
    if agency:
        tpl_q = Path(ent) / "企业级" / "模板库" / agency / mode / "资格证明及辅助资料表.docx"
        if tpl_q.is_file():
            tpl_equip_rows = _extract_tpl_equip_rows(tpl_q)

    blocks, _ = _extract_blocks(source_path)
    by_id = {it.get("id"): it for it in contract["格式文件"]}

    results = []
    skipped = []
    merged = {}
    for m in FILE_MAP:
        if m["kind"] == "skip":
            skipped.append({"契约项": m["id"], "原因": m.get("skip_reason", "")})
            continue
        it = by_id.get(m["id"])
        if not it:
            skipped.append({"契约项": m["id"], "原因": "契约中无此项"})
            continue
        merged.setdefault(m["file"], []).append(it)

    for fname, items in merged.items():
        ids = [it["id"] for it in items]
        lo = min(it.get("块范围", [0])[0] for it in items if it.get("块范围"))
        hi = max(it.get("块范围", [0])[-1] for it in items if it.get("块范围"))
        out_file = out / fname
        rules = {
            "para_label": PARA_LABEL_RULES.get(fname, []),
            "date_ph": fname in DATE_PH_FILES,
            "img_after_table": IMAGE_PH_AFTER_TABLE.get(fname, []),
            "img_after_para": IMAGE_PH_AFTER_PARA.get(fname, []),
            # 范本 v1.1 专属处理开关
            "cover_title": fname == "封面.docx",
            "split_authorize": fname == "授权委托书.docx",
            "sme_project": fname == "中小企业声明函.docx",
            # 范本 v1.2：附表9 仪器设备数据行从模板库带入
            "equip_tpl": fname == "资格证明及辅助资料表.docx",
        }
        info = build_docx(blocks, (lo, hi), items, out_file, material,
                          font=FILE_FONT.get(fname), rules=rules,
                          equip_rows=tpl_equip_rows)
        rel = "项目级/%s/项目模板/%s" % (project, fname)
        if register_baseline:
            try:
                # 版本不显式传：首次登记 v1，重新生成自动 bump，保证可追溯
                fb.register(ent, rel, level="项目级", project=project, ptype="项目模板",
                            generator=GEN_ID, note="由格式契约+素材清单动态生成")
            except Exception as ex:                    # 基线登记失败不阻断生成
                info["基线登记"] = "失败：%s" % ex
        results.append({
            "文件": fname, "契约项": ids, "块范围": [lo, hi],
            "占位符数": info.get("占位符数", 0),
            "图片占位": info.get("图片占位", 0),
            "图片占位框": info.get("图片占位框", 0),
            "字体": info.get("统一字体", FILE_FONT.get(fname, "")),
            "去底纹": info.get("去底纹", 0),
        })

    record = {
        "项目": project, "生成时间": core.now_iso(),
        "生成器": "%s %s" % (GEN_ID, GEN_VERSION),
        "输入": {"契约": str(contract_path), "素材清单": str(material_path),
                 "招标文件": str(source_path), "基础模板目录": base_dir or "-"},
        "文件": results, "未生成": skipped,
    }
    (out / "生成记录.json").write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_ph_manifest(out, results, material)
    return {"目录": str(out), "文件": results, "未生成": skipped}


def _write_ph_manifest(out_dir, results, material):
    """扫描各生成 docx 的【】占位符，输出 项目占位符清单.md。"""
    lines = ["# 项目占位符清单", ""]
    lines.append("- 项目：%s ｜ 生成器：%s %s ｜ 生成时间：%s"
                 % (material.get("project", ""), GEN_ID, GEN_VERSION, core.now_iso()))
    lines.append("- 说明：占位符统一【xxx】；图片占位【图片：xxx】；")
    lines.append("  每个图片占位后附灰底预览框（框内标注将插入内容+尺寸，见即可审）；人工审核可增删；")
    lines.append("  审核通过后冻结（只读+版本号），商务标只认冻结版。")
    lines.append("")
    total = 0
    for r in results:
        fname = r["文件"]
        p = out_dir / fname
        phs = _scan_placeholders(p) if p.is_file() else []
        total += len(phs)
        lines.append("## %s（%d 个）" % (fname, len(phs)))
        for ph in sorted(phs):
            lines.append("- %s" % ph)
        lines.append("")
    lines.append("---")
    lines.append("合计占位符：%d 个（按生成器统计；人工增删后以登记清单为准）" % total)
    (out_dir / "项目占位符清单.md").write_text("\n".join(lines), encoding="utf-8")


def _scan_placeholders(docx_path):
    """提取 docx 中的【】占位符（跨 run 拼接后正则）。"""
    import zipfile
    try:
        with zipfile.ZipFile(docx_path) as z:
            xml = z.read("word/document.xml").decode("utf-8", errors="replace")
    except Exception:
        return []
    texts = []
    for m in re.finditer(r"<w:p[ >].*?</w:p>|<w:p/>", xml, flags=re.S):
        parts = re.findall(r"<w:t[^>]*>(.*?)</w:t>", m.group(0), flags=re.S)
        if parts:
            texts.append("".join(parts))
    full = "\n".join(texts)
    return sorted(set(re.findall(r"【[^】]+】", full)))
