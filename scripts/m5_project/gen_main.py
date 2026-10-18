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
                         HAVE_DOCX, GenError, PARA_LABEL_RULES, Document,
                         skip_chapter_head)
from . import image_ph_rules as ipr
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

    L1（2026-10-17）：占位文案与素材路径全部来自 image_ph_rules 规则树
    （素材清单驱动），与填充引擎同一权威——模板预览与商务标实际填充所见一致。
    素材库不存在/解析失败 → 返回空映射（预览框退化为【待补素材】灰底标注，不阻断生成）。
    """
    rules = ipr.build_ph_rules(material)
    assets_map = {}
    for _r in rules.values():
        for r in _r:
            hit = ipr.resolve_ph(r["ph"], rules)
            if hit is None:
                continue
            _fname, _anchor, items, _group = hit
            if items:
                assets_map[r["ph"]] = items
    return assets_map


def generate(ent, project, contract_path=None, material_path=None, source_path=None,
             out_dir=None, base_dir="", format_config=None, register_baseline=True,
             skip_verify=False, extra_sources=None):
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
         **补充文件**（extra_sources={文件名: 样本docx路径}）：招标原文投标格式
         未列但用户确认需要的文件（如中小企业声明函），从企业自有样本 docx
         深拷贝文字 → 套用格式配置 → 占位化（不参与招标原文文字硬校验）；
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
        if m["kind"] in ("skip", "独立生成"):
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
    # L1：图片占位规则树（素材清单唯一数据源，gen/fill 共用）
    _ph_rules = ipr.build_ph_rules(material)

    # L2：独立生成文件（招标格式未列、投标人自附，如投标单位业绩材料和奖项）
    independent = [m for m in FILE_MAP if m.get("kind") == "独立生成"]

    for fname, items in merged.items():
        ids = [it["id"] for it in items]
        valid = [it for it in items if it.get("块范围")]
        # ---- 补充文件（extra_sources）：招标格式未列、用户确认需要的文件（如中小企业声明函）----
        # 内容契约无块范围（原文未列）时，若提供了企业自有样本 docx → 从样本深拷贝生成。
        extra_src = None
        if not valid and extra_sources:
            extra_src = Path(extra_sources.get(fname)) if extra_sources.get(fname) else None
            if extra_src and not extra_src.is_file():
                raise GenError("补充文件样本不存在：%s（%s）" % (extra_src, fname))
        if not valid and extra_src is None:
            skipped.append({"契约项": ",".join(ids), "原因": "契约未定位块范围（跳过生成）"})
            continue
        if valid:
            lo = min(it.get("块范围", [0])[0] for it in valid)
            hi = max(it.get("块范围", [0])[-1] for it in valid)
            # 章节标题段（「第X章 投标文件格式」）不拷贝（用户规则：仅章节标题不要）——
            # 与代码硬校验共用 gen_common.skip_chapter_head（单一权威）
            lo = skip_chapter_head(blocks, lo)
            src_blocks, src_doc = blocks, None
            src_range = (lo, hi)
        else:
            src_blocks, src_doc = _extract_blocks(extra_src)
            src_range = (0, len(src_blocks) - 1)   # span 闭区间 [s, e]，len 会越界
            lo, hi = src_range
        out_file = out / fname
        # ---- 图片占位（L1 2026-10-17）：素材清单驱动规则树（image_ph_rules，
        #      gen 生成什么占位、fill 就解析什么占位，同一权威）----
        #      旧静态 IMAGE_PH_AFTER_TABLE/PARA 与 v5 _dynamic_image_phs 废弃；
        #      占位文案/数量/位置锚点全部来自 build_ph_rules（清单没有的图不生成占位）。
        img_after_table, img_after_para = _rules_to_anchor_lists(_ph_rules, fname)
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
        # ---- 深拷贝（招标原文或补充样本）→ 格式配置应用 → 独占一面 ----
        info = build_docx(src_blocks, src_range, items, out_file, material,
                          font=FILE_FONT.get(fname), rules=rules,
                          assets_map=assets_map)          # tpl_doc=None / style=None：纯深拷贝模式
        if extra_src is not None:
            info["补充文件"] = str(extra_src)
        # L3 2026-10-18 修复：apply_format/ensure_own_page 须在同一 Document 实例上
        # 操作后保存（原 _resave 重开未修改原文件 → 格式修改全部丢失，
        # 旧模板"字体宋体应仿宋/独占一面false"根因）。
        doc_fmt = Document(str(out_file))
        fmt_stats = apply_format(doc_fmt, fname, cfg)
        n_own = ensure_own_page(doc_fmt, fname, cfg)
        # L4 修复（2026-10-18）：按人工标书标准做段落级对齐（章标题/封面落款/
        # 附注后置/附表10 列表说明文字）——apply_format 后、save 前，同一实例。
        align_stats = _apply_manual_alignment(doc_fmt, fname, material)
        info["人工对齐"] = align_stats
        info["格式应用"] = fmt_stats
        if n_own:
            info["独占一面分页符"] = n_own
        doc_fmt.save(out_file)
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
            "人工对齐": info.get("人工对齐", {}),
            "独占一面分页符": info.get("独占一面分页符", 0),
            "字体": info.get("统一字体", FILE_FONT.get(fname, "")),
            "去底纹": info.get("去底纹", 0),
        })

    # ---- 独立生成文件（L2 2026-10-17）：结构化生成，不走契约深拷贝 ----
    for m in independent:
        fname = m["file"]
        out_file = out / fname
        try:
            info = _gen_independent_award(out_file, material, fname)
            doc_fmt = Document(str(out_file))
            fmt_stats = apply_format(doc_fmt, fname, cfg)
            info["格式应用"] = fmt_stats
            n_own = ensure_own_page(doc_fmt, fname, cfg)
            if n_own:
                info["独占一面分页符"] = n_own
            doc_fmt.save(out_file)
            results.append({
                "文件": fname, "契约项": m["id"], "块范围": [],
                "格式配置": "scripts/m5_project/format_config.json",
                "占位符数": info.get("占位符数", 0),
                "图片占位": info.get("图片占位", 0),
                "图片占位框": info.get("图片占位框", 0),
                "格式应用": info.get("格式应用", {}),
                "独占一面分页符": info.get("独占一面分页符", 0),
                "字体": FILE_FONT.get(fname, "仿宋"),
            })
        except Exception as ex:
            skipped.append({"契约项": m["id"], "原因": "独立生成失败：%s" % ex})

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
            # 传格式配置路径（非 dict）：page_fit 内部按路径加载并在 _format_config_path 复用
            pages = page_fit.verify_and_fit(ent, project, out, format_config, results,
                                            register_baseline=register_baseline)
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


def _gen_independent_award(out_file, material, fname):
    """L2（2026-10-17）：结构化生成投标单位业绩材料和奖项（独立文件）。

    人工标书实证 P80-103：首页大标题 + 按素材清单动态章节（无素材章节跳过），
    每章：章节标题段 + 【图片：】占位段。章节标题与占位文案全部来自
    image_ph_rules 规则树（与填充引擎同一权威）；格式由 format_config 统一套用。
    """
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Pt

    doc = Document()
    # 首页：大标题（居中；独占一面由 format_config 独占一面清单控制）
    p0 = doc.add_paragraph()
    p0.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r0 = p0.add_run("投标单位业绩材料和奖项")
    r0.font.size = Pt(22)
    p1 = doc.add_paragraph()
    p1.add_run("（以下为投标单位业绩及荣誉奖项证明材料，按评分办法要求提供）")
    # 章节 + 占位段 + 预览框（规则顺序 = 章节顺序；无素材章节在规则树中已动态跳过）
    # L4 修复（2026-10-18）：每章【图片：】占位段后补素材预览框（对齐资格表形态，
    # 用户验收反馈业绩奖项文件只有文字占位看不到素材）。
    from .gen_images import _insert_ph_preview_after
    from .gen_tables import _make_page_break_para as _mbp
    n_img = 0
    n_prev = 0
    for r in ipr.iter_file_rules(ipr.build_ph_rules(material), fname):
        title = r["anchor"][1]
        h = doc.add_paragraph()
        # L4 修复（2026-10-18）：每章独占一面（对齐人工标书 P80-103 每章独立成页；
        # 第一章也分页——首页大标题+说明独占 P1，第一章自 P2 起）。
        h._p.addprevious(_mbp())
        h.add_run(title)
        ph = doc.add_paragraph()
        ph.add_run(r["ph"])
        n_img += 1
        if _insert_ph_preview_after(doc, ph, r["ph"], r["items"]):
            n_prev += 1
    doc.save(out_file)
    return {"占位符数": 1 + n_img, "图片占位": n_img, "图片占位框": n_prev}


def _rules_to_anchor_lists(ph_rules, fname):
    """L1：把 image_ph_rules 规则树转成 build_docx 锚点列表 [(锚点关键词, [占位文案,...])]。

    同一锚点（kind+keyword 相同）的多条规则合并为一组（如附表8备注段后的
    5 个人员组 + 社保组），保持规则顺序；kind=table → img_after_table，
    kind=para → img_after_para。
    """
    t_rules, p_rules = [], []
    for r in ipr.iter_file_rules(ph_rules, fname):
        kind, kw = r["anchor"]
        target = t_rules if kind == "table" else p_rules
        entry = next((e for e in target if e[0] == kw), None)
        if entry is None:
            target.append([kw, [r["ph"]]])
        else:
            entry[1].append(r["ph"])
    return t_rules, p_rules


def _apply_manual_alignment(doc, fname, material):
    """L4 修复（2026-10-18）：按人工标书标准做段落级对齐（apply_format 后、save 前）。

    校验报告差异项：
    - 投标函/法代/授权：删除「一、/二、/（一）/（二）」章标题层级，标题改写为
      人工版形态（人工版删除了章标题：投标函/法定代表人资格证明书/授权委托书）。
    - 法代/授权：落款（供应商/投标人 + 日期）移到「附：」之前
      （人工版顺序：正文→落款→附→身份证/联系方式）。
    - 封面：补「法定代表人或其委托代理人：（签字或盖章）」+ 日期 落款（人工版落款三件套）。
    - 资格表：附表10 列表说明表格内恢复材料清单文字（人工版形态；招标原文该表格为空），
      删除表格内【图片：】占位（图组占位在表格后已存在）。
    返回 {"删除段": n, "改写段": n, "插入段": n, "移动段": n, "列表说明行": n}。
    """
    import copy as _copy
    from docx.text.paragraph import Paragraph
    from docx.shared import Pt as _Pt
    from docx.enum.text import WD_LINE_SPACING as _WDLS
    from docx.oxml import OxmlElement as _OE
    from docx.oxml.ns import qn as _qn

    stats = {"删除段": 0, "改写段": 0, "插入段": 0, "移动段": 0, "列表说明行": 0}

    def _ptext(p):
        return "".join(r.text or "" for r in p.runs)

    def _set_text(p, text):
        if p.runs:
            p.runs[0].text = text
            for r in p.runs[1:]:
                r._r.getparent().remove(r._r)
        else:
            p.add_run(text)
        stats["改写段"] += 1

    def _del(p):
        el = p._p
        el.getparent().remove(el)
        stats["删除段"] += 1

    def _is_date_line(t):
        return ("年" in t and "月" in t and "日" in t) or t.startswith("【日期】")

    def _settle_before_attach(doc):
        """法代/授权：把落款段（供应商/投标人/法代/代理/日期）移到第一个「附：」段之前。"""
        attach_p = None
        settles = []
        for p in list(doc.paragraphs):
            t = _ptext(p).strip()
            if t.startswith("附：") or t.startswith("附:"):
                if attach_p is None:
                    attach_p = p
            elif (t.startswith("供应商：") or t.startswith("投标人：")
                    or t.startswith("投标人（盖单位公章）")
                    or t.startswith("法定代表人：") or t.startswith("法定代表人（")
                    or t.startswith("授权代理人：") or _is_date_line(t)):
                settles.append(p)
        if attach_p is not None:
            for p in settles:
                el = p._p
                el.getparent().remove(el)
                attach_p._p.addprevious(el)
                stats["移动段"] += 1

    # ---------- 投标函：删章标题层级，标题改写 ----------
    if fname == "投标函.docx":
        for p in list(doc.paragraphs):
            t = _ptext(p).strip()
            if t.startswith("一、投标函及投标函附录"):
                _del(p)
            elif t.startswith("（一）投 标 函") or t.startswith("（一）投标函"):
                _set_text(p, "投 标 函")

    # ---------- 法定代表人身份证明 ----------
    if fname == "法定代表人身份证明.docx":
        for p in list(doc.paragraphs):
            t = _ptext(p).strip()
            if t.startswith("二、法人代表资格证明") or t.startswith("二、法定代表人资格证明"):
                _del(p)
            elif t.startswith("（一）法定代表人资格证明书"):
                _set_text(p, "法定代表人资格证明书")
        _settle_before_attach(doc)

    # ---------- 授权委托书 ----------
    if fname == "授权委托书.docx":
        for p in list(doc.paragraphs):
            t = _ptext(p).strip()
            if t.startswith("（二）授权委托书"):
                _set_text(p, "授权委托书")
        _settle_before_attach(doc)

    # ---------- 封面：补法代签字 + 日期 落款 ----------
    if fname == "封面.docx":
        anchor = None
        for p in list(doc.paragraphs):
            t = _ptext(p).strip()
            if "供应商名称" in t and "盖章" in t:
                anchor = p
                break
        if anchor is not None:
            # L4 修复（2026-10-18）：addnext 每次插在 anchor 正后方会逆序，
            # 须跟踪 last 保证顺序：供应商名称 → 法代签字 → 日期（对齐人工版落款三件套）。
            last = anchor._p
            for txt in ("法定代表人或其委托代理人：（签字或盖章）", "日期：____"):
                new_el = _copy.deepcopy(anchor._p)
                last.addnext(new_el)
                np = Paragraph(new_el, anchor._parent)
                if np.runs:
                    np.runs[0].text = txt
                    for r in np.runs[1:]:
                        r._r.getparent().remove(r._r)
                else:
                    np.add_run(txt)
                stats["插入段"] += 1
                last = new_el

    # ---------- 资格表：附表10 列表说明表格内恢复清单文字 ----------
    if fname == "资格证明及辅助资料表.docx":
        list_tbl = None
        for t in doc.tables:
            if any("列表说明" in c.text for r in t.rows for c in r.cells):
                list_tbl = t
                break
        if list_tbl is not None:
            cell = list_tbl.rows[0].cells[0]
            for p in list(cell.paragraphs):
                for r in list(p.runs):
                    r._r.getparent().remove(r._r)
            lines = [
                "列表说明（附评标办法要求的相关资料）",
                "1、质量管理体系认证证书、环境管理体系认证证书、职业健康体系认证证书",
                "2、拟派项目总监工程师职称证书",
                "3、其他监理人员职称证书",
                "4、监理示范（优质）工程",
                "5、拟派项目总监荣誉",
            ]
            p0 = cell.paragraphs[0]
            p0.add_run(lines[0])
            for ln in lines[1:]:
                cell.add_paragraph().add_run(ln)
            # 新段格式：仿宋12 单倍行距（与表格单元格一致）
            for p in cell.paragraphs:
                pf = p.paragraph_format
                pf.line_spacing_rule = _WDLS.SINGLE
                pf.space_before = _Pt(0)
                pf.space_after = _Pt(0)
                for r in p.runs:
                    r.font.name = "仿宋"
                    r.font.size = _Pt(12)
                    rPr = r._r.get_or_add_rPr()
                    rFonts = rPr.find(_qn("w:rFonts"))
                    if rFonts is None:
                        rFonts = _OE("w:rFonts")
                        rPr.insert(0, rFonts)
                    rFonts.set(_qn("w:eastAsia"), "仿宋")
            stats["列表说明行"] = len(lines)

    return stats


def _dynamic_image_phs(material, fname):
    """⚠️ 已废弃（L1 2026-10-17）：占位生成已切换到 image_ph_rules 素材清单规则树。
    本函数保留仅作历史参考；缺陷（无素材时 max(1) 兜底生成占位、honors 字段名
    '名称' 与清单 'name' 不匹配导致先进证书误生成）已由规则树修复，勿再调用。"""


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
    """L1（2026-10-17）：对外导出该文件的图片占位锚点规则。

    占位文案/数量/位置锚点全部来自 image_ph_rules 素材清单规则树（与主流程、
    填充引擎同一权威）；旧静态 IMAGE_PH_AFTER_TABLE/PARA 与 _dynamic_image_phs
    已废弃（保留函数体仅作历史参考，不再被主流程调用）。
    """
    return _rules_to_anchor_lists(ipr.build_ph_rules(material), fname)


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
