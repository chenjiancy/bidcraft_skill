# -*- coding: utf-8 -*-
"""
bidcraft · M6 模板部件库（P2）—— docx 母版拆解回流（tpl-part 命令）

把一本 docx 标书（商务标母版 / 技术标旧稿 / 历史成稿）"拆零件"：
识别封面段、目录段、正文样式、结尾段，把企业名/项目名/日期等**内容**参数化为
{{ enterprise_name }} / {{ project_name }} / {{ bid_date }} 占位，只保留**版式**，
输出部件 JSON（schema m6.part/v1）落盘 `共享资源/技术标风格/部件库/`。

之后 M6 模板 JSON 的 structure 项可用 `partRef: "部件名"` 引用，导出引擎按部件渲染
（版式来自母版、内容由 --fill/项目数据填充）—— 商务标、技术标成稿均可作为拆解来源。

铁律（不变）：
  - 只拆版式、不拆内容（D25 内容校验铁律：招标原文一字不改；拆解只提取格式）；
  - 来源必须是用户自己的、经人工确认的（D26：脱敏 → 参数化 → 试生成闸门）。
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _shared import core                     # noqa: E402
from . import sources                        # noqa: E402

PART_SCHEMA = "m6.part/v1"
PART_LIB_REL = Path("共享资源") / "技术标风格" / "部件库"

RE_DATE = re.compile(r"\d{4}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日")

# 结构识别关键词
TOC_MARK = "目　录"
CLOSING_MARKS = ("以下无正文", "本页无正文", "（以下无正文）")


def part_lib_dir(args):
    """→ 部件库目录；素材库根/其父级/本仓库共享资源均可见（specimen 内置样例等任意根可用）。"""
    root = sources.lib_root(args)
    repo = Path(__file__).resolve().parents[2] / "共享资源" / "技术标风格" / "部件库"
    for base in (root / "共享资源" / "技术标风格",
                 root.parent / "共享资源" / "技术标风格",
                 Path(__file__).resolve().parents[2] / "共享资源" / "技术标风格"):
        d = base / "部件库"
        if d.is_dir():
            return d
    return repo if repo.is_dir() else None


def find_parts(args):
    """→ 部件清单 [{name, file, parts 摘要}]；目录缺失返回 []。"""
    d = part_lib_dir(args)
    if d is None:
        return []
    out = []
    for p in sorted(d.glob("*.json")):
        try:
            doc = json.loads(p.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            doc = {}
        out.append({"name": p.stem, "file": p.name,
                    "parts": sorted((doc.get("parts") or {}).keys())})
    return out


def find_part_files(args):
    """→ {name: Path} 部件库全部文件（供 partRef 校验）。"""
    d = part_lib_dir(args)
    if d is None:
        return {}
    return {p.stem: p for p in sorted(d.glob("*.json"))}


def load_part(args, name):
    """按部件名读取 → dict；缺失抛 LibraryError。"""
    files = find_part_files(args)
    key = name[:-5] if name.endswith(".json") else name
    p = files.get(key)
    if p is None:
        raise core.LibraryError("部件不存在：%s（tpl-part --list 查看部件库）" % name)
    doc = core.read_json(str(p), None)
    if not isinstance(doc, dict):
        raise core.LibraryError("部件无法解析：%s" % p)
    return doc


# ---------------------------------------------------------------------------
# 拆解器：docx 母版 → 部件描述
# ---------------------------------------------------------------------------
def _para_info(p):
    """提取段落文本 + 样式特征（字体/字号/加粗/对齐/段前段后）。"""
    text = p.text or ""
    east = None
    size = None
    bold = None
    for r in p.runs:
        try:
            ea = r.font.element.rPr.rFonts.get("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}eastAsia") if r.font.element.rPr is not None and r.font.element.rPr.rFonts is not None else None
        except Exception:  # noqa: BLE001
            ea = None
        if ea:
            east = ea
        if r.font.size is not None:
            size = r.font.size.pt
        if bold is None and r.bold is not None:
            bold = r.bold
    align = None
    try:
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        a = p.alignment
        if a == WD_ALIGN_PARAGRAPH.CENTER:
            align = "center"
        elif a == WD_ALIGN_PARAGRAPH.RIGHT:
            align = "right"
        elif a == WD_ALIGN_PARAGRAPH.LEFT:
            align = "left"
    except Exception:  # noqa: BLE001
        pass
    return {"text": text, "east": east, "size": size, "bold": bold, "align": align}


def _param_text(text, enterprise, project):
    """内容参数化：企业名/项目名/日期 → 占位符（只挖内容，版式不动）。"""
    t = text
    if enterprise and enterprise in t:
        t = t.replace(enterprise, "{{ enterprise_name }}")
    if project and project in t:
        t = t.replace(project, "{{ project_name }}")
    t = RE_DATE.sub("{{ bid_date }}", t)
    return t


def _stats(paras):
    """正文样式统计：字号/字体众数。"""
    sizes = [p["size"] for p in paras if p.get("size")]
    fonts = [p["east"] for p in paras if p.get("east")]
    size = max(set(sizes), key=sizes.count) if sizes else 12
    font = max(set(fonts), key=fonts.count) if fonts else "仿宋"
    return {"size": size, "east": font}


def scan_master(docx_path, enterprise="", project=""):
    """拆解 docx 母版 → 部件描述 dict（不落盘）。

    结构识别（启发式，P2）：
      - toc：含「目　录」的段落；
      - closing：含"以下无正文"的段落（倒序查找）；
      - cover：toc 之前全部段落（封面通常集中在开头）；
      - body：排除 cover/toc/closing 区域后统计正文样式；
      - colophon：暂不自动切分（人工补充），置 null。
    段落文本做内容参数化（占位符替换）。"""
    from docx import Document

    doc = Document(str(docx_path))
    infos = [_para_info(p) for p in doc.paragraphs]
    non_empty = [i for i in infos if i["text"].strip()]
    if not non_empty:
        raise core.LibraryError("docx 无文本段落，无法拆解：%s" % docx_path)

    # 定位 toc / closing
    toc_idx = None
    for i, info in enumerate(infos):
        if info["text"].strip() == TOC_MARK or info["text"].strip().startswith(TOC_MARK):
            toc_idx = i
            break
    closing_idx = None
    for i in range(len(infos) - 1, -1, -1):
        if any(m in infos[i]["text"] for m in CLOSING_MARKS):
            closing_idx = i
            break
    # cover：toc 之前段落（若 toc 缺失，取开头 1/3 作为封面区）
    cover_end = toc_idx if toc_idx is not None else max(1, len(non_empty) // 3)
    cover_paras = [i for i in infos[:cover_end] if i["text"].strip()]
    # body 区：cover 之后 ~ closing 之前
    body_lo = cover_end
    body_hi = closing_idx if closing_idx is not None else len(infos)
    body_paras = [i for i in infos[body_lo:body_hi] if i["text"].strip()]

    def _paras_out(paras):
        out = []
        for i in paras:
            out.append({
                "text": _param_text(i["text"], enterprise, project),
                "style": {
                    "east": i["east"] or "仿宋",
                    "size": int(i["size"]) if i["size"] else 12,
                    "bold": bool(i["bold"]),
                    "align": i["align"] or "left",
                },
            })
        return out

    closing_paras = []
    if closing_idx is not None:
        closing_paras = _paras_out([i for i in infos[closing_idx:closing_idx + 2] if i["text"].strip()])

    body_style = _stats(body_paras) if body_paras else {"size": 12, "east": "仿宋"}
    return {
        "schema": PART_SCHEMA,
        "source": Path(docx_path).name,
        "name": Path(docx_path).stem,
        "scannedAt": "",
        "parts": {
            "cover": {"paragraphs": _paras_out(cover_paras),
                      "pageBreak": True} if cover_paras else None,
            "colophon": None,          # P2：人工补充（拆解器不自动切分）
            "toc": {"title": TOC_MARK,
                    "style": {"east": "黑体", "size": 16, "bold": True, "align": "center"},
                    "pageBreak": True} if toc_idx is not None else None,
            "body": {"font": body_style, "headingSizes": {}},   # 正文样式基线
            "closing": {"paragraphs": closing_paras} if closing_paras else None,
        },
    }


def _write_part(d, doc):
    """落盘部件（防覆盖；同名存在时报错）。"""
    if d is None:
        raise core.LibraryError("部件库目录缺失：%s（首次使用时创建）" % PART_LIB_REL)
    target = d / ("%s.json" % doc["name"])
    if target.exists():
        raise core.LibraryError("部件已存在，防覆盖：%s（换源文件名或人工处理）" % target)
    target.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


# ---------------------------------------------------------------------------
# tpl-part 命令
# ---------------------------------------------------------------------------
def cmd_tpl_part(args):
    if getattr(args, "show", ""):
        return _cmd_show(args)
    if getattr(args, "scan", ""):
        return _cmd_scan(args)
    return _cmd_list(args)


def _cmd_list(args):
    jflag = getattr(args, "json", False)
    parts = find_parts(args)
    d = part_lib_dir(args)
    if jflag:
        print(json.dumps({"ok": True, "dir": str(d) if d else "",
                          "parts": parts}, ensure_ascii=False, indent=2))
        return 0
    print("模板部件库 · %s" % (d if d else "未找到 %s（首次 --scan --confirm 时创建）" % PART_LIB_REL))
    if not parts:
        print("（空——用 tpl-part --scan <母版.docx> --confirm 拆解回流第一本）")
        return 0
    print("部件清单（%d 个）：" % len(parts))
    for p in parts:
        print("  %-24s 部件：%s" % (p["name"], "、".join(p["parts"]) or "—"))
    return 0


def _cmd_show(args):
    try:
        doc = load_part(args, args.show)
    except core.LibraryError as e:
        print(str(e))
        return 1
    print("部件：%s（来源 %s）" % (doc.get("name", ""), doc.get("source", "—")))
    for part, spec in (doc.get("parts") or {}).items():
        if spec is None:
            continue
        if part == "body":
            print("  · 正文样式基线：%s" % spec.get("font"))
            continue
        if part == "toc":
            print("  · 目录：%s（%s）" % (spec.get("title"), spec.get("style")))
            continue
        n = len(spec.get("paragraphs") or [])
        print("  · %s：%d 段%s" % (part, n, "（分页）" if spec.get("pageBreak") else ""))
        for para in (spec.get("paragraphs") or [])[:3]:
            print("      「%s」 %s" % (para.get("text", ""), para.get("style")))
    return 0


def _cmd_scan(args, jflag=None):
    jflag = getattr(args, "json", False)
    docx = Path(args.scan)
    if not docx.is_file():
        print("母版 docx 不存在：%s" % docx)
        return 1
    enterprise = getattr(args, "enterprise", "") or ""
    project = getattr(args, "project", "") or ""
    try:
        doc = scan_master(str(docx), enterprise, project)
    except Exception as e:  # noqa: BLE001
        print("拆解失败：%s" % e)
        return 1
    if not getattr(args, "confirm", False):
        if jflag:
            print(json.dumps(doc, ensure_ascii=False, indent=2))
        else:
            print("拆解预览（dry-run，未写盘）：")
            print("  来源：%s  名称：%s" % (doc["source"], doc["name"]))
            for part, spec in (doc.get("parts") or {}).items():
                if spec is None:
                    print("  · %-8s —（未识别，人工补充）" % part)
                elif part == "body":
                    print("  · %-8s 正文样式基线 %s" % (part, spec.get("font")))
                elif part == "toc":
                    print("  · %-8s 目录标题「%s」（%s）" % (part, spec.get("title"), spec.get("style")))
                else:
                    n = len(spec.get("paragraphs") or [])
                    print("  · %-8s %d 段%s" % (part, n, "（分页）" if spec.get("pageBreak") else ""))
                    for para in (spec.get("paragraphs") or [])[:2]:
                        print("      「%s」" % para.get("text", ""))
        print("确认落盘请加 --confirm（防覆盖）")
        return 0
    # 落盘目录固定为素材库根的部件库（读时才有仓库兜底；写不越界）
    root = sources.lib_root(args)
    d = root / "共享资源" / "技术标风格" / "部件库"
    d.mkdir(parents=True, exist_ok=True)
    target = _write_part(d, doc)
    # 写后回读
    back = core.read_json(str(target), None)
    if not isinstance(back, dict) or back.get("schema") != PART_SCHEMA:
        raise core.LibraryError("写后回读校验失败：%s" % target)
    if jflag:
        print(json.dumps({"ok": True, "path": str(target), "name": doc["name"]},
                         ensure_ascii=False, indent=2))
    else:
        print("部件落盘：%s（回读校验通过）" % target)
    return 0
