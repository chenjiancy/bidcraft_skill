# -*- coding: utf-8 -*-
"""
bidcraft · M6 技术标制作 —— 纯逻辑层公共常量 / 工具（无 I/O）

拆分原因：`规则对齐-M6-20261021.md` S4 单文件约 500 行红线。业务实现按域拆为：
  rules_chapters.py  F1/F2/F3/F11（章节树 / 覆盖 / 排版预设）
  rules_check.py     F4–F10（篇幅 / 敏感词 / 一致性 / 占位 / 状态机 / 自述块 / 双通道）
  rules.py           门面，统一导出（T4/T5 只依赖门面）
"""
import re

# ---------------------------------------------------------------------------
# 契约常量（可增行表；增删项不改分支）
# ---------------------------------------------------------------------------
SCHEMA_ID = "m6.chapters/v1"
BID_MODES = ("明标", "暗标")
STATUSES = ("PENDING", "CONTEXT_READY", "WRITING", "WRITTEN", "CHECKED", "CONFIRMED", "FAILED")
GATES = ("outline", "write", "final")

# 状态迁移表（契约 §8）：PENDING→CONTEXT_READY→WRITING→WRITTEN→CHECKED→CONFIRMED/FAILED
STATUS_FLOW = [
    ("PENDING", "CONTEXT_READY"),
    ("PENDING", "FAILED"),
    ("CONTEXT_READY", "WRITING"),
    ("CONTEXT_READY", "PENDING"),
    ("CONTEXT_READY", "FAILED"),
    ("WRITING", "WRITTEN"),
    ("WRITING", "FAILED"),
    ("WRITTEN", "CHECKED"),
    ("WRITTEN", "WRITING"),
    ("WRITTEN", "FAILED"),
    ("CHECKED", "CONFIRMED"),
    ("CHECKED", "WRITING"),
    ("CHECKED", "FAILED"),
    ("CONFIRMED", "WRITING"),
    ("CONFIRMED", "FAILED"),
    ("FAILED", "PENDING"),
    ("FAILED", "CONTEXT_READY"),
    ("FAILED", "WRITING"),
]

# P2 允许的素材依赖枚举（提示词 R7）
DEPENDS_ENUM = ("project_overview", "personnel", "performance", "enterprise_profile", "regulation")

# 章节编号 / id / 层级
NO_PATTERN = re.compile(r"^\d+(?:\.\d+){0,2}$")
ID_PATTERN = re.compile(r"^ch-\d{2,4}$")
MAX_LEVEL = 3
KEYPOINT_MIN, KEYPOINT_MAX = 3, 6
CHAPTER_WORD_SPLIT = 5000  # P4 B4：超过即拆小节

CJK_RE = re.compile(r"[\u4e00-\u9fff]")
WORD_RE = re.compile(r"[A-Za-z]+")
TABLE_LINE_RE = re.compile(r"^\s*\|.*\|\s*$")
TABLE_SEP_RE = re.compile(r"^\s*\|[\s:|-]+\|\s*$")
COVER_RATIO = 0.5  # Q2：keyPoints 与 item 汉字交集 ≥ 0.5 才算实覆盖

# ---------------------------------------------------------------------------
# 排版预设（D8）：内置兜底 + 中文别名，真实色值/清单由 T13 layout-presets.json 提供
# ---------------------------------------------------------------------------
DEFAULT_LAYOUT = {
    "preset": ["single-column", "tabular", "two-column", "card", "image-left", "divider", "data-row"],
    "palette": ["deep-indigo", "warm-bronze", "pine-green", "brick-red", "steel-cyan", "charcoal",
                "deep-blue-gold", "ink-green-orange", "eggplant-silver", "mono-red", "gradient-blue-cyan"],
    "cover": ["full-block", "line-white", "image-underlay", "gradient"],
    "decoration": ["minimal", "standard", "rich"],
}
LAYOUT_ALIAS_KEYS = {
    "preset": ("preset", "presets", "layouts"),
    "palette": ("palette", "palettes", "colors"),
    "cover": ("cover", "covers"),
    "decoration": ("decoration", "decorations"),
}
DECORATION_ALIASES = {"克制": "minimal", "标准": "standard", "丰富": "rich"}

# 暗标敏感表（Q3 完整内置表；企业名/地址/人名由 vocab 注入）
SENSITIVE_BUILTIN = [
    ("自称", re.compile(r"我公司|本公司|我司|我单位")),
    ("标识词", re.compile(r"(?i:logo)|商标")),
    ("手机号", re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")),
    ("固定电话", re.compile(r"(?<!\d)0\d{2,3}[-— ]?\d{7,8}(?!\d)")),
    ("邮箱", re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")),
    ("网址", re.compile(r"(?i:https?://)[^\s]+|(?i:www\.)[^\s]+")),
]

# 术语同义词表（Q4 内置）
SYNONYM_GROUPS = [
    ("招标人", ("甲方", "业主", "采购人", "建设单位")),
    ("监理单位", ("我司", "我公司", "本公司", "我单位")),
    ("投标人", ("供应商",)),
]
KNOWN_POSTS = ("总监理工程师代表", "总监理工程师", "专业监理工程师", "安全监理工程师",
               "造价工程师", "监理员", "总监代表")

# 占位 / 垃圾残留（A6）
PLACEHOLDER_PATTERNS = [
    ("待填", re.compile(r"\{\{待填[^{}\n]*\}\}")),
    ("模板占位", re.compile(r"\{\{[^{}\n]{1,40}\}\}")),
    ("TODO", re.compile(r"\b(?:TODO|FIXME|TBD)\b", re.I)),
    ("XXX", re.compile(r"\bXXX+\b")),
]
BLANK_LINE_RE = re.compile(r"^[ \t\u3000]+$", re.M)
SELFCHECK_RE = re.compile(r"<!--\s*(M6-COVERAGE|M6-REVISE)\s*(.*?)-->", re.S)


# ---------------------------------------------------------------------------
# 通用小工具
# ---------------------------------------------------------------------------
def _err(code, message):
    return {"level": "error", "code": code, "message": message}


def _warn(code, message):
    return {"level": "warn", "code": code, "message": message}


def _has_error(issues):
    return any(i.get("level") == "error" for i in issues)


def _is_int(v):
    return isinstance(v, int) and not isinstance(v, bool)


def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _locate(text, start, end):
    """字符偏移 → (行号, 列号, 片段)，均从 1 开始。"""
    line = text.count("\n", 0, start) + 1
    col = start - text.rfind("\n", 0, start)
    snippet = text[max(0, start - 10):min(len(text), end + 10)].replace("\n", " ")
    return line, col, snippet


def _cjk_set(text):
    return set(CJK_RE.findall(text or ""))


def _norm_idx(v):
    """idx 统一成 int；非法返回 None（字符串数字可接受）。"""
    if _is_int(v):
        return v
    if isinstance(v, str) and v.strip().isdigit():
        return int(v.strip())
    return None
