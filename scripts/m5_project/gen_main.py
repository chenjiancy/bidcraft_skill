# -*- coding: utf-8 -*-
"""⑦ generator 拆包 · 主流程（generate / 占位符清单 / 扫描）。

V5（2026-10-10 用户定稿，企业模板废弃）：
  项目模板 = 招标原文投标文件格式**深拷贝**（一字不改、一个内容不丢）；
  格式 = 通用格式配置 format_config.json（format_applier 应用）；
  图片 = 图框占位（image_spec 尺寸 + 图片插入位置锚点 + 素材清单动态数量）；
  独占一面 = 格式配置「独占一面」清单（文件级/内容级）。
"""
import json
import re
from pathlib import Path

from _shared import core
from m_feedback import feedback as fb

from .gen_common import (DATE_PH_FILES, FILE_FONT, FILE_MAP, GEN_ID, GEN_VERSION,
                         HAVE_DOCX, GenError, IMAGE_PH_AFTER_PARA,
                         IMAGE_PH_AFTER_TABLE, PARA_LABEL_RULES, Document,
                         skip_chapter_head)
from .gen_blocks import build_docx, _extract_blocks
from .gen_paths import (_default_contract_path, _default_material_path,
                        _default_source_docx, _resolve_project_dir)
from .format_applier import apply_format, ensure_own_page, load_format_config

__all__ = ["generate", "check_gap_closed", "_write_ph_manifest",
           "_scan_placeholders", "_resolve_assets_map", "build_image_ph_rules"]


def check_gap_closed(proj_dir, project):
    """v2.6 素材缺口收口闸门：读 招标解析/素材缺口_<项目>.json，
    返回 (ok, pending, gap_json)。缺口清单不存在 → (True, [], None)（未启用缺口流程不拦截）；
    存在且有「待补充」项 → (False, [row...], json)。"""
    gap_json = Path(proj_dir) / "招标解析" / ("素材缺口_%s.json" % project)
    if not gap_json.is_file():
        return True, [], None
    doc = core.read_json(gap_json, None) or {}
    pending = [it for it in (doc.get("items") or [])
               if it.get("status") == "待补充"]
    return (not pending), pending, gap_json


def _resolve_assets_map(ent, proj_dir, material):
    """预览框 v2 素材映射：{图片占位文案: [(素材绝对路径, 口径key, 换页), ...]}。

    复用填充引擎同一套组合解析（fill_combo._build_combo + 白名单），保证
    模板预览与商务标实际填充所见一致。素材库不存在/解析失败 → 返回空映射
    （预览框退化为【待补素材】灰底标注，不阻断生成）。
    """
    from . import fill_combo as fc
    from .fill_images import FILL_IMG_MAP
    lib_root = Path(ent) / "企业级" / "素材库"
    if not lib_root.is_dir():
        return {}
    whitelist = fc._build_whitelist(material)
    phs = set()
    for fname in set(IMAGE_PH_AFTER_TABLE) | set(IMAGE_PH_AFTER_PARA):
        for _kw, plist in IMAGE_PH_AFTER_TABLE.get(fname, []) + IMAGE_PH_AFTER_PARA.get(fname, []):
            phs.update(plist)
    assets_map = {}
    for key in phs:
        mapped = FILL_IMG_MAP.get(key)
        if mapped and mapped[0]:                 # 单图占位（固定素材库路径，白名单外不受影响）
            full = lib_root / mapped[0]
            if full.is_file():
                assets_map[key] = [(str(full), mapped[1], True)]
            continue
        try:                                     # 组合占位：同填充引擎的素材清单白名单解析
            items, _miss, _out = fc._build_combo(key, lib_root, proj_dir, material, whitelist)
            if items:
                assets_map[key] = items
        except Exception:
            continue                       # 单项解析失败不阻断，预览框退化为待补标注
    return assets_map


def generate(ent, project, contract_path=None, material_path=None, source_path=None,
             out_dir=None, base_dir="", format_config=None, register_baseline=True,
             skip_verify=False):
    """
    主入口（v5，2026-10-10 用户定稿：格式配置 + 招标原文深拷贝）：
      1) 读内容契约 JSON / 素材清单 / 通用格式配置 format_config.json；
      2) 素材缺口收口闸门（同前）；
      3) 每个项目模板 docx：招标原文投标文件格式**深度拷贝**（文字表格一字不改、
         一个内容不丢，章节标题段由 skip_chapter_head 跳过）→ 套用格式配置
         （format_applier：仿宋体系/字号/行距固定28磅/首行缩进/对齐/表格/页面/
         独占一面）→ **图片占位**（【图片：xxx】占位段 + 灰底图框预览框：
         大小=image_spec 尺寸规定，位置=图片插入位置锚点，数量=素材清单动态）→
         只放占位无实际内容（商务标生成时填充）；
      4) 生成记录.json + 项目占位符清单.md + **代码硬校验**（verify_text 文字逐字比对）
         + 页数校验/独占面收敛（page_fit，按格式配置独占一面清单）；
      5) 登记产物基线（fb.register）。
    返回 {"目录", "文件": [...], "未生成": [...], "校验": {...}, "页数校验": {...}}。
    """
    if not HAVE_DOCX:
        raise GenError("生成器依赖 python-docx，当前环境未安装")
    ent = Path(ent)
    proj_dir = _resolve_project_dir(ent, project)
    if proj_dir is None:
        raise GenError("项目目录不存在：项目级/%s" % project)
    # ---- v2.6 素材缺口收口闸门：缺口清单存在且仍有「待补充」项 → 拒绝生成 ----
    ok_gap, pending_gap, gap_json = check_gap_closed(proj_dir, project)
    if not ok_gap:
        names = "、".join("%s(%s)" % (it.get("item", "?"), it.get("gap_id", "?"))
                          for it in pending_gap)
        raise GenError(
            "素材缺口尚未收口（%d 项待补充：%s）——文字性资料请在会话中提示用户直接输入，"
            "图片/文件请用户继续上传；用户确认无此素材或对投标无影响可豁免；"
            "全部处理完（tender-gap --verify 通过）后再执行 proj-gen。\n缺口清单：%s"
            % (len(pending_gap), names, gap_json))
    contract_path = Path(contract_path or _default_contract_path(proj_dir))
    material_path = Path(material_path or _default_material_path(proj_dir))
    source_path = Path(source_path or _default_source_docx(proj_dir))

    contract = core.read_json(contract_path, None)
    if not contract or "格式文件" not in contract:
        raise GenError("内容契约 JSON 无『格式文件』清单：%s" % contract_path)
    material = core.read_json(material_path, None)
    if not material:
        raise GenError("素材清单 JSON 为空：%s" % material_path)
    if not source_path.is_file():
        raise GenError("招标文件源 docx 不存在：%s（proj-gen 需要源文件做投标文件格式深拷贝）"
                       % source_path)

    # ---- v5：通用格式配置（格式唯一来源，企业模板废弃）----
    cfg = load_format_config(format_config)

    out = Path(out_dir) if out_dir else proj_dir / "项目模板"
    out.mkdir(parents=True, exist_ok=True)

    # 招标原文块（深拷贝/校验文字源）
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

    # 预览框 v2：素材清单白名单 → 每个图片占位解析真实素材路径（_build_combo 规则同填充引擎）
    assets_map = _resolve_assets_map(ent, proj_dir, material)

    for fname, items in merged.items():
        ids = [it["id"] for it in items]
        valid = [it for it in items if it.get("块范围")]
        if not valid:
            skipped.append({"契约项": ",".join(ids), "原因": "契约未定位块范围（跳过生成）"})
            continue
        lo = min(it.get("块范围", [0])[0] for it in valid)
        hi = max(it.get("块范围", [0])[-1] for it in valid)
        # 章节标题段（「第X章 投标文件格式」）不拷贝（用户规则：仅章节标题不要）——
        # 与代码硬校验共用 gen_common.skip_chapter_head（单一权威）
        lo = skip_chapter_head(blocks, lo)
        out_file = out / fname
        # ---- 图片占位：静态锚点（gen_common）+ v5 动态（配置图片插入位置 + 素材清单）----
        img_after_table = list(IMAGE_PH_AFTER_TABLE.get(fname, []))
        img_after_para = list(IMAGE_PH_AFTER_PARA.get(fname, []))
        dyn_t, dyn_p = _dynamic_image_phs(material, fname)
        img_after_table += dyn_t
        img_after_para += dyn_p
        rules = {
            "para_label": PARA_LABEL_RULES.get(fname, []),
            "date_ph": fname in DATE_PH_FILES,
            "img_after_table": img_after_table,
            "img_after_para": img_after_para,
            # 范本专属处理开关
            "cover_title": fname == "封面.docx",
            "split_authorize": fname == "授权委托书.docx",
            "sme_project": fname == "中小企业声明函.docx",
        }
        # ---- v5：招标原文深拷贝（文字表格保留，清无关格式）→ 格式配置应用 → 独占一面 ----
        info = build_docx(blocks, (lo, hi), items, out_file, material,
                          font=FILE_FONT.get(fname), rules=rules,
                          assets_map=assets_map)          # tpl_doc=None / style=None：纯深拷贝模式
        fmt_stats = apply_format(Document(str(out_file)), fname, cfg)
        n_own = ensure_own_page(Document(str(out_file)), fname, cfg)
        info["格式应用"] = fmt_stats
        if n_own:
            info["独占一面分页符"] = n_own
        # 保存格式应用后的文档（重新保存）
        _resave(out_file)
        rel = "项目级/%s/项目模板/%s" % (project, fname)
        if register_baseline:
            try:
                # 版本不显式传：首次登记 v1，重新生成自动 bump，保证可追溯
                fb.register(ent, rel, level="项目级", project=project, ptype="项目模板",
                            generator=GEN_ID, note="招标原文深拷贝+通用格式配置+素材清单动态图片占位（v5）")
            except Exception as ex:                    # 基线登记失败不阻断生成
                info["基线登记"] = "失败：%s" % ex
        results.append({
            "文件": fname, "契约项": ids, "块范围": [lo, hi],
            "格式配置": "scripts/m5_project/format_config.json",
            "占位符数": info.get("占位符数", 0),
            "图片占位": info.get("图片占位", 0),
            "图片占位框": info.get("图片占位框", 0),
            "格式应用": info.get("格式应用", {}),
            "独占一面分页符": info.get("独占一面分页符", 0),
            "字体": info.get("统一字体", FILE_FONT.get(fname, "")),
            "去底纹": info.get("去底纹", 0),
        })

    # ---- 代码硬校验（M5 v5：verify_text 文字逐字比对，无差异清单驱动）----
    verify = {"结论": "跳过", "文件": []}
    if not skip_verify:
        try:
            from . import verify_text
            verify = verify_text.verify_contract_text(ent, project, out, source_path,
                                                      contract, material=material,
                                                      gen_map={r["文件"]: r["契约项"]
                                                               for r in results})
        except Exception as ex:                       # 校验器异常不阻断生成，标注待人工/agent 复核
            verify = {"结论": "校验器异常：%s" % ex, "文件": []}

    # ---- 页数校验 + 独占面排版收敛（格式配置独占一面清单；严禁跨页）----
    pages = {"结论": "跳过", "文件": []}
    if not skip_verify and results:
        try:
            from . import page_fit
            pages = page_fit.verify_and_fit(ent, project, out, None,
                                            results, register_baseline=register_baseline,
                                            format_config=cfg)
        except Exception as ex:
            pages = {"结论": "校验器异常：%s" % ex, "文件": []}

    record = {
        "项目": project, "生成时间": core.now_iso(),
        "生成器": "%s %s" % (GEN_ID, GEN_VERSION),
        "模式": "招标原文投标文件格式深拷贝 + 通用格式配置（v5，企业模板废弃）",
        "输入": {"内容契约": str(contract_path), "素材清单": str(material_path),
                 "格式配置": str(_format_config_path(format_config)),
                 "招标原文源": str(source_path)},
        "代码硬校验": verify,
        "页数校验": pages,
        "文件": results, "未生成": skipped,
    }
    (out / "生成记录.json").write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_ph_manifest(out, results, material)

    # ---- 写后回读（fail fast）----
    for r in results:
        core.readback.verify_docx_nonempty(out / r["文件"], label="项目模板 docx")
    core.readback.verify_json(out / "生成记录.json", required_fields=("文件",), label="生成记录")
    core.readback.verify_file(out / "项目占位符清单.md", label="占位符清单")
    return {"目录": str(out), "文件": results, "未生成": skipped, "校验": verify,
            "页数校验": pages}


def _format_config_path(p):
    if p:
        return str(Path(p))
    return "scripts/m5_project/format_config.json"


def _resave(out_file):
    """格式应用后的文档重新保存（apply_format/ensure_own_page 在内存副本上操作）。"""
    doc = Document(str(out_file))
    doc.save(out_file)


# 图片素材类型 → 占位文案（按素材清单人员/业绩素材键与目录文件名推断）
_IMG_TYPE_BY_KEY = {
    "注册证书": "注册证书", "职称": "职称证书", "简历": "简历",
    "毕业证": "毕业证书", "岗位证书": "岗位证书",
}
_IMG_TYPE_BY_FNAME = [
    ("中标通知", "中标通知书"), ("竣工", "竣工验收报告"), ("验收", "竣工验收报告"),
    ("合同", "监理合同"), ("协议", "监理合同"), ("业绩", "业绩证明"),
    ("发票", "发票"), ("备案", "备案表"), ("其他", "其他"),
]


def _dynamic_image_phs(material, fname):
    """v5 按素材清单动态生成图片占位规则（图片插入位置锚点 + 动态数量）。

    返回 (img_after_table_rules, img_after_para_rules)，形如 [(锚点关键词, [占位文案,...]), ...]。
    图片数量与类型按素材清单动态：业绩图片数=该业绩图片素材数（有竣工报告要求→
    生成竣工报告占位，大小同合同）；人员图片数=该人员证书/职称/简历/毕业证/岗位证书素材数。
    只放【图片：xxx】占位 + 图框（ph_preview 灰底框，尺寸=image_spec），无实际内容。
    """
    if fname == "资格证明及辅助资料表.docx":
        return _dyn_qualification(material)
    if fname == "投标单位业绩材料和奖项.docx":
        return _dyn_perf_award(material)
    return [], []


def _dyn_qualification(material):
    """资格证明及辅助资料表：业绩表后（动态）、简历表后（动态）。"""
    from pathlib import Path as _P
    t_rules = []
    # 业绩（附表3 已完成工程情况表后）：按素材清单业绩目录内图片素材生成占位
    perf_phs = []
    perfs = material.get("performance") or []
    for pi, perf in enumerate(perfs, 1):
        base = _P(perf.get("path") or "") if perf.get("path") else None
        img_types = []
        if base and base.is_dir():
            for f in sorted(base.iterdir()):
                if f.suffix.lower() not in (".png", ".jpg", ".jpeg", ".bmp", ".gif"):
                    continue
                nm = f.stem
                hit = next((lab for kw, lab in _IMG_TYPE_BY_FNAME if kw in nm), None)
                img_types.append(hit or "业绩素材")
        else:
            img_types = ["业绩素材"]
        for t in img_types:
            perf_phs.append("【图片：业绩%d-%s】" % (pi, t))
    if perf_phs:
        t_rules.append(("已完成工程情况表", perf_phs))
    # 人员（附表8 监理人员简历表后）：每人素材键（注册证书/职称/简历/毕业证/岗位证书）非空 → 占位
    pers_phs = []
    for p in material.get("personnel") or []:
        name = p.get("name", "")
        for key, lab in _IMG_TYPE_BY_KEY.items():
            if p.get(key):
                pers_phs.append("【图片：%s-%s】" % (name, lab))
    if pers_phs:
        t_rules.append(("监理人员简历表", pers_phs))
    return t_rules, []


def _dyn_perf_award(material):
    """投标单位业绩材料和奖项：章节标题后证书图组 + 业绩名称后业绩图组（动态）+ 人员职称。
    依据真实标书：三体系→3图、业绩名称→图组、总监职称→1、人员姓名→职称、先进→4、示范→图。"""
    t_rules = []
    p_rules = []
    # 三体系认证证书标题后 → 证书图组（按素材清单 iso_certificates 数量动态，无素材时 1 张）
    iso = material.get("iso_certificates") or []
    iso_n = max(1, len(iso))
    p_rules.append(("三体系认证证书", ["【图片：三体系认证证书】"] * iso_n))
    # 先进（优秀）监理企业证书 → honors 中先进类数量（无则 1）
    honors = material.get("honors") or []
    adv_n = max(1, len([h for h in honors if "先进" in str(h.get("名称", ""))]))
    p_rules.append(("先进（优秀）监理企业证书", ["【图片：先进（优秀）监理企业证书】"] * adv_n))
    # 监理示范工程 → honors 中示范类数量（无则 1）
    demo_n = max(1, len([h for h in honors if "示范" in str(h.get("名称", ""))]))
    p_rules.append(("监理示范工程", ["【图片：监理示范工程】"] * demo_n))
    # 总监高级工程师职称证书标题后 → 1 张
    p_rules.append(("总监的高级工程师职称证书", ["【图片：总监高级工程师职称证书】"]))
    # 业绩名称段后 → 业绩图组（锚点=素材清单业绩名称前 8 字，去空格；数量=该业绩图片素材数）
    from pathlib import Path as _P
    perfs = material.get("performance") or []
    for pi, perf in enumerate(perfs, 1):
        name = str(perf.get("name", "") or "").replace(" ", "").replace("\u3000", "")
        if not name:
            continue
        base = _P(perf.get("path") or "") if perf.get("path") else None
        img_types = []
        if base and base.is_dir():
            for f in sorted(base.iterdir()):
                if f.suffix.lower() not in (".png", ".jpg", ".jpeg", ".bmp", ".gif"):
                    continue
                nm = f.stem
                hit = next((lab for kw, lab in _IMG_TYPE_BY_FNAME if kw in nm), None)
                img_types.append(hit or "业绩素材")
        else:
            img_types = ["业绩素材"]
        phs = ["【图片：业绩%d-%s】" % (pi, t) for t in img_types]
        p_rules.append((name[:8], phs))
    # 人员职称（四、拟派本项目监理人员的中级工程师职称 → （N）姓名段后 → 职称图）
    pers = material.get("personnel") or []
    for p in pers:
        name = str(p.get("name", "") or "").strip()
        if name and p.get("职称"):
            p_rules.append((name, ["【图片：%s-职称证书】" % name]))
    return t_rules, p_rules


def build_image_ph_rules(material, fname):
    """对外导出：静态 + 动态图片占位规则（测试/诊断用）。"""
    t = list(IMAGE_PH_AFTER_TABLE.get(fname, []))
    p = list(IMAGE_PH_AFTER_PARA.get(fname, []))
    dt, dp = _dynamic_image_phs(material, fname)
    return t + dt, p + dp


def _write_ph_manifest(out_dir, results, material):
    """扫描各生成 docx 的【】占位符，输出 项目占位符清单.md。"""
    lines = ["# 项目占位符清单", ""]
    lines.append("- 项目：%s ｜ 生成器：%s %s ｜ 生成时间：%s"
                 % (material.get("project", ""), GEN_ID, GEN_VERSION, core.now_iso()))
    lines.append("- 说明：占位符统一【xxx】；图片占位【图片：xxx】；")
    lines.append("  每个图片占位后附灰底图框（框内标注将插入内容+尺寸，见即可审）；人工审核可增删；")
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
