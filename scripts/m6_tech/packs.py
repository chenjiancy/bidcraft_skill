# -*- coding: utf-8 -*-
"""
bidcraft · M6 技术标制作 —— 专家包读取与注入（R-T3，契约 §3.3）

专家包 = 可切换的"配置集"（目录学 taxonomy + 版式组合 + 风格引用），
**不含提示词正文**——提示词一律归 styles.json 与 M6 提示词 P2/P3/P5。

落位：共享级 `<素材库根>/共享资源/技术标风格/专家包/<包id>/`（包.json + taxonomy.json），
共享资源在素材库根或其父目录下均可见（对齐 layout / ctxpack 风格库的解析规则）。

校验纪律（吸收链企 C5-2「静默兜底官方团」教训的反面）：
包 id / layoutCombo 十五组 id / taxonomy 类目——缺失即报错，不做任何静默兜底。
"""
import re

from _shared import core

from . import layout
from . import rules as m6rules
from . import sources

PACK_SCHEMA = "m6.expert-pack/v1"
TAX_SCHEMA = "m6.taxonomy/v1"
MANIFEST_FILE = "包.json"
TAXONOMY_FILE = "taxonomy.json"
COMBO_KEYS = ("preset", "palette", "cover", "decoration", "font",
              "imageRatio", "imageRule", "imageLayout",
              "pageSetup", "headingSystem", "tocStyle",
              "tableStyle", "captionSystem", "paragraphStyle", "headerFooter")


def find_pack_dir(args, pack_id):
    """包 id → 专家包目录路径；不存在返回 None。id 非法直接报错。"""
    pid = str(pack_id or "").strip()
    if not re.match(r"^[A-Za-z0-9][A-Za-z0-9_-]*$", pid):
        raise core.LibraryError("专家包 id 非法（须为字母数字开头，含 -/_）：%r" % (pack_id,))
    root = sources.lib_root(args)
    for base in (root / "共享资源" / "技术标风格" / "专家包",
                 root.parent / "共享资源" / "技术标风格" / "专家包"):
        p = base / pid
        if p.is_dir():
            return p
    return None


def load_pack(args, pack_id):
    """读包清单 + taxonomy → {"dir","manifest","taxonomy","notes"}。

    任何缺失/非法即抛 LibraryError（不静默兜底）：
      - 目录 / 包.json / taxonomy.json 不存在，schema 不符；
      - 包 id 与目录名不一致；classes 非数组或类目缺 name；
      - layoutCombo 十五组 id 缺失或不在排版预设清单（复用 F11 validate_layout）。
    styles.json（T6）未交付时 styleRef 不生效 → notes 披露，不报错。
    """
    pdir = find_pack_dir(args, pack_id)
    if pdir is None:
        raise core.LibraryError("专家包不存在：%s（共享级 共享资源/技术标风格/专家包/）" % pack_id)
    manifest = core.read_json(str(pdir / MANIFEST_FILE), None)
    if not isinstance(manifest, dict) or manifest.get("schema") != PACK_SCHEMA:
        raise core.LibraryError("专家包 %s：%s 缺失或 schema ≠ %s" % (pack_id, MANIFEST_FILE, PACK_SCHEMA))
    if str(manifest.get("id") or "").strip() != str(pack_id).strip():
        raise core.LibraryError("专家包 id 与目录名不一致：目录=%s 清单=%r" % (pack_id, manifest.get("id")))

    tax = core.read_json(str(pdir / TAXONOMY_FILE), None)
    if not isinstance(tax, dict) or tax.get("schema") != TAX_SCHEMA:
        raise core.LibraryError("专家包 %s：%s 缺失或 schema ≠ %s" % (pack_id, TAXONOMY_FILE, TAX_SCHEMA))
    classes = tax.get("classes")
    if not isinstance(classes, list) or not classes:
        raise core.LibraryError("专家包 %s：taxonomy.classes 必须是非空数组" % pack_id)
    for i, c in enumerate(classes):
        if not isinstance(c, dict) or not str(c.get("name") or "").strip():
            raise core.LibraryError("专家包 %s：taxonomy.classes[%d] 缺 name" % (pack_id, i))

    combo = manifest.get("layoutCombo")
    if not isinstance(combo, dict) or any(not str(combo.get(k) or "").strip() for k in COMBO_KEYS):
        raise core.LibraryError("专家包 %s：layoutCombo 必须含十五组 id（%s）" % (pack_id, "/".join(COMBO_KEYS)))
    ok, issues = m6rules.validate_layout(dict(combo), layout.load_presets(args), "明标")
    if not ok:
        raise core.LibraryError("专家包 %s 的 layoutCombo 非法：\n%s"
                                % (pack_id, "\n".join("[%s] %s" % (i["code"], i["message"])
                                                      for i in issues if i["level"] == "error")))

    notes = []
    if manifest.get("styleRef"):
        root = sources.lib_root(args)
        if not any((base / "styles.json").is_file() for base in
                   (root / "共享资源" / "技术标风格", root.parent / "共享资源" / "技术标风格")):
            notes.append("styleRef=%r 未生效：共享级 styles.json 未建（T6 风格库待交付）"
                         % manifest["styleRef"])
    return {"dir": pdir, "manifest": manifest, "taxonomy": tax, "notes": notes}


def tree_entry(manifest):
    """包清单 → 章节树.expertPack 字段（保持精简，溯源细节在包.json 内）。"""
    return {"id": manifest.get("id"), "name": manifest.get("name") or "",
            "docType": manifest.get("docType") or ""}


def _norm(text):
    return re.sub(r"\s+", "", str(text or ""))


def class_for(taxonomy, title):
    """章标题（去空白精确匹配）→ taxonomy 类目；未命中返回 None。"""
    t = _norm(title)
    if not t:
        return None
    for c in taxonomy.get("classes") or []:
        if _norm(c.get("name")) == t:
            return c
    return None


def attach_context(ctx_pack, manifest, taxonomy, ch):
    """章标题命中 taxonomy 类目 → ctx_pack 增 expertPack 字段；返回是否命中。

    未命中不报错（P2 允许按评分项自定义章名，taxonomy 仅兜底骨架来源），
    由 CLI 输出披露清单。
    """
    cls = class_for(taxonomy, (ch or {}).get("title"))
    if cls is None:
        return False
    ctx_pack["expertPack"] = {
        "id": manifest.get("id"), "name": manifest.get("name") or "",
        "classId": cls.get("id"), "className": cls.get("name"),
        "classDescription": cls.get("description") or "",
        "illustration": bool(cls.get("illustration")),
    }
    return True
