# -*- coding: utf-8 -*-
"""⑦ filler 拆包 · 简历表 OCR（rapidocr 优先；tesseract fallback）。"""
import os
import re
import shutil
import subprocess  # noqa: F401 (tesseract fallback 使用)
import sys  # noqa: F401
from pathlib import Path

__all__ = [
    "_find_tesseract", "TESS", "RESUME_TAG_MAP", "_RESUME_LABELS", "_get_rapid",
    "_ocr_boxes", "_parse_cert", "_LOOSE_LABELS", "_cluster_rows", "_clean_val",
    "_extract_row_fields", "_extract_experience", "ocr_resume_fields",
    "_find_resume_scan",
]


# Tesseract OCR fallback（⑧：路径参数化——优先环境变量 TESSERACT_CMD，其次 PATH 内
# tesseract，最后回退本机实测路径；新增机器或换环境无需改代码）
def _find_tesseract():
    env = os.environ.get("TESSERACT_CMD", "").strip()
    if env and Path(env).is_file():
        return env
    w = shutil.which("tesseract")
    if w:
        return w
    return r"C:\Users\hxjlcj\AppData\Local\Programs\Tesseract-OCR\tesseract.exe"


TESS = _find_tesseract()

RESUME_TAG_MAP = {
    "姓名": "人员姓名", "性别": "性别", "出生年月": "出生年月",
    "最终学历": "学历", "毕业院校专业及时间": "毕业院校专业及时间",
    "政治面貌": "政治面貌", "现任职务": "现任职务", "技术职称": "技术职称",
    "聘任时间": "聘任时间", "从事设计工作年限": "从事设计工作年限",
    "从事造价工作年限": None,                      # 模板无此字段，忽略
    "从事监理工作年限": "从事监理工作年限（年）",
    "居民身份证号码": "身份证号", "相关专业经历": "相关专业经历",
    "主要经历": "主要经历",
}
# 长标签优先匹配（避免子串误切）
_RESUME_LABELS = sorted([t for t in RESUME_TAG_MAP if RESUME_TAG_MAP[t]],
                        key=len, reverse=True)

_rapid_engine = None


def _get_rapid():
    global _rapid_engine
    if _rapid_engine is None:
        from rapidocr_onnxruntime import RapidOCR
        _rapid_engine = RapidOCR()
    return _rapid_engine


def _ocr_boxes(img_path):
    """rapidocr → [(text, x, y)]；失败则 tesseract TSV fallback。"""
    try:
        eng = _get_rapid()
        result, _ = eng(str(img_path))
        out = []
        for box, text, _s in (result or []):
            out.append((text, int(box[0][0]), int(box[0][1])))
        if out:
            return out
    except Exception:
        pass
    return _ocr_tsv(img_path)


def _ocr_tsv(img_path):
    """tesseract TSV 兜底：与 rapidocr 相同输出 [(text, x, y)]。"""
    p = str(img_path)
    try:
        out = subprocess.run(
            [TESS, p, "stdout", "--psm", "6", "-l", "chi_sim+eng", "tsv"],
            capture_output=True, timeout=60, check=True)
    except Exception:
        return []
    cells = []
    for line in out.stdout.decode("utf-8", errors="replace").splitlines()[1:]:
        parts = line.split("\t")
        if len(parts) >= 12 and parts[11].strip() and float(parts[10]) > 30:
            cells.append((parts[11].strip(), int(float(parts[6])), int(float(parts[7]))))
    return cells


def _parse_cert(cert_str):
    """从素材清单 personnel.cert 解析证书名称/编号：
    '省监理工程师岗位证书皖监师2020000823'→('省监理工程师岗位证书','2020000823')"""
    s = cert_str or ""
    s = re.sub(r"（[^）]*）", "", s)
    n = re.search(r"(\d{6,})", s)
    names = re.findall(r"[\u4e00-\u9fff]{2,12}?(?:注册证|岗位证书|师证书|证书|师证|证)", s)
    name = max(names, key=len) if names else ""
    return name, (n.group(1) if n else "")


# 宽松标签（rapidocr 可能拆段/漏字）：(标签, 简历表占位键, 值清洗)
# 注：从事设计/从事造价年限扫描件通常为空且易与「从事施工」错位 → 不提取，保留占位待补
_LOOSE_LABELS = [
    ("主要经历", "主要经历", None),
    ("相关专业", "相关专业经历", None),
    ("居民身份证", "身份证号", "去号码前缀"),
    ("从事监理", "从事监理工作年限（年）", "去尾部工作年限"),
    ("聘任时间", "聘任时间", None),
    ("技术职称", "技术职称", None),
    ("现任职务", "现任职务", None),
    ("政治面貌", "政治面貌", None),
    ("毕业院校", "毕业院校专业及时间", "去专业及时间前缀|毕业院校重排"),
    ("最终学历", "学历", None),
    ("出生年月", "出生年月", None),
    ("性别", "性别", None),
    ("姓名", "人员姓名", None),
]


def _cluster_rows(cells, tol=30):
    """rapidocr 文本按 y 聚类成表格行（同一行 y 浮动容忍 30px）；行内按 x 排序、
    x 差 <10 的拆段合并；输出 [{y0, s(紧凑无空格)}] 按 y 升序。"""
    rows = []
    for text, x, y in sorted(cells, key=lambda c: (c[2], c[1])):
        for r in rows:
            if abs(y - r["y0"]) <= tol:
                r["items"].append((text, x))
                break
        else:
            rows.append({"y0": y, "items": [(text, x)]})
    out = []
    for r in rows:
        items = sorted(r["items"], key=lambda t: t[1])
        merged = []
        for text, x in items:
            if merged and x - merged[-1][1] < 10:
                merged[-1] = (merged[-1][0] + text, merged[-1][1])
            else:
                merged.append((text, x))
        out.append({"y0": r["y0"], "s": "".join(t for t, _ in merged).replace(" ", "")})
    return sorted(out, key=lambda r: r["y0"])


def _clean_val(val, mode):
    if not mode:
        return val
    for m in mode.split("|"):
        if m == "去尾部工作年限":
            val = re.split(r"工作年限", val)[0]
        elif m == "去号码前缀":
            val = re.sub(r"^(号码?|码)", "", val)
        elif m == "去专业及时间前缀":
            val = re.sub(r"^专业及时间", "", val)
        elif m == "毕业院校重排":
            mm = re.match(r"^(管理/\S+)(建筑施工与.*)$", val)
            if mm:
                val = mm.group(2) + mm.group(1)
    return val


def _extract_row_fields(rows):
    fields = {}
    for r in rows:
        s = r["s"]
        if len(s) <= 20 and "简历" in s:      # 标题行（拟投入监理人员简历表）
            continue
        for lab, ph, clean in _LOOSE_LABELS:
            if ph is None or ph in fields:
                continue
            pos = s.find(lab)
            if pos < 0:
                continue
            after = s[pos + len(lab):]
            nxt = len(after)
            for lab2, _ph2, _c2 in _LOOSE_LABELS:
                p2 = after.find(lab2)
                if 0 <= p2 < nxt:
                    nxt = p2
            val = _clean_val(after[:nxt].strip(), clean)
            if val:
                fields[ph] = val
    return fields


def _extract_experience(rows, fields):
    """相关专业经历/主要经历跨行提取（经历文本在证书表之后多行）。"""
    if not rows:
        return
    start_i = end_i = None
    for i, r in enumerate(rows):
        if "相关专业" in r["s"]:
            start_i = i
            break
    if start_i is not None:
        for i in range(start_i + 1, len(rows)):
            if "主要经历" in rows[i]["s"] or "要经历" in rows[i]["s"]:
                end_i = i
                break
        seg = rows[start_i]["s"]
        seg = seg[seg.find("相关专业") + len("相关专业"):]
        for j in range(start_i + 1, end_i if end_i is not None else len(rows)):
            seg += rows[j]["s"]
        if end_i is not None:
            s2 = rows[end_i]["s"]
            if "主要经历" in s2:
                seg += s2[s2.find("主要经历") + len("主要经历"):]
            else:
                seg += s2[s2.find("要经历") + len("要经历"):]
        seg = re.sub(r"^经历", "", seg.strip())
        seg = re.sub(r"经历(?=\d)", "；", seg)     # 标签拆段残渣 → 分号分隔
        if seg:
            fields["相关专业经历"] = seg
    if "主要经历" not in fields:
        for i in range(len(rows) - 1, -1, -1):
            s = rows[i]["s"]
            pos = s.find("主要经历")
            tag = "主要经历"
            if pos < 0:
                pos = s.find("要经历")
                tag = "要经历"
            if pos >= 0:
                v = s[pos + len(tag):]
                for j in range(i + 1, len(rows)):
                    v += rows[j]["s"]
                v = v.strip()
                if v:
                    fields["主要经历"] = v
                break


def ocr_resume_fields(png_path, cert_str=None):
    """OCR 简历扫描件 → {简历表占位符: 值}（rapidocr，行聚类+宽松标签+跨行经历）。"""
    cells = _ocr_boxes(png_path)
    if not cells:
        return {}
    rows = _cluster_rows(cells)
    fields = _extract_row_fields(rows)
    _extract_experience(rows, fields)
    # 性别 fallback：OCR 漏识别「男/女」时按身份证号第 17 位奇偶推断（奇=男 偶=女）
    if not fields.get("性别"):
        idno = fields.get("身份证号", "")
        if len(idno) >= 17 and idno[16].isdigit():
            fields["性别"] = "男" if int(idno[16]) % 2 else "女"
    # 证书名称/编号：优先素材清单 cert 解析（结构化可靠）
    if cert_str:
        cname, cno = _parse_cert(cert_str)
        if cno and "证书编号" not in fields:
            fields["证书编号"] = cno
        if cname and "证书名称" not in fields:
            fields["证书名称"] = cname
    return fields


def _find_resume_scan(lib_root, name):
    """人员简历扫描件：人员/<姓名>/简历/*.png（取 P0 或首个）。"""
    d = Path(lib_root) / "人员" / name / "简历"
    if not d.is_dir():
        return None
    files = sorted(d.glob("*.png")) + sorted(d.glob("*.jpg")) + sorted(d.glob("*.jpeg"))
    if not files:
        return None
    p0 = [f for f in files if "P0" in f.name]
    return str((p0 or files)[0])
