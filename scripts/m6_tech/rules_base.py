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
GATES = ("outline", "write", "final", "diff")

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
    "preset": ["single-column", "tabular", "two-column", "card", "image-left", "divider", "data-row",
               "image-right", "hybrid-flow", "minimal-clean"],
    "palette": ["deep-indigo", "warm-bronze", "pine-green", "brick-red", "steel-cyan", "charcoal",
                "deep-blue-gold", "ink-green-orange", "mono-red", "gradient-blue-cyan"],
    "cover": ["full-block", "line-white", "image-underlay", "gradient",
              "frame-corners", "top-banner", "split-diagonal", "minimal-type",
              "emblem-center", "ribbon-bottom"],
    "decoration": ["minimal", "standard", "rich", "none", "heading-rule",
                   "sidebar-tab", "corner-dots", "section-band", "icon-accent", "table-fill"],
    "font": ["gov-gongwen", "engineering", "modern-business", "elegant-classic", "dark-safe",
             "gb2312-classic", "hei-song-simplified", "kai-literary", "fangsong-official", "mixed-safe"],
    "imageRatio": ["none", "low", "mid", "high", "ultra-low", "low-mid",
                   "mid-high", "very-high", "full", "appendix-only"],
    "imageRule": ["upload-first", "search-supplement", "ai-render", "hybrid", "dark-safe-img",
                  "plan-only", "photo-only", "chart-only", "search-verify", "no-source"],
    "imageLayout": ["split-h", "split-v", "inline", "grid", "appendix",
                    "side-note", "banner", "timeline", "card-mix", "none"],
    "pageSetup": ["p1-standard-a4", "p2-haikou-25", "p3-jianyu-商务", "p4-tongliao-317",
                  "p5-nanyang-32", "p6-guangxi-215", "p7-hb-25-20", "p8-nenu-学位",
                  "p9-gbt-学位", "p10-symmetric-紧凑"],
    "headingSystem": ["h1-gbt-arabic", "h2-tender-arabic", "h3-qinghai-hybrid",
                      "h4-nanyang-7level", "h5-jianyu-bold", "h6-sci-report",
                      "h7-pku-template", "h8-nenu-academic", "h9-cas-academic",
                      "h10-tongliao-tender"],
    "tocStyle": ["t1-jianyu-auto", "t2-zol-standard", "t3-qinghai-nopage",
                 "t4-guangxi-pointline", "t5-nenu-indent", "t6-cas-rightalign",
                 "t7-xinong-compact", "t8-dual-index", "t9-wps-tabstop", "t10-minimal-2level"],
    "tableStyle": ["tb1-three-line", "tb2-full-line", "tb3-saving-line", "tb4-header-fill",
                   "tb5-grid-fine", "tb6-no-line", "tb7-dark-0.5", "tb8-center-vh",
                   "tb9-kpi-row", "tb10-split-continue"],
    "captionSystem": ["c1-gbt-seq", "c2-cy-chapter", "c3-jianyu-neighbor", "c4-nenu-pos",
                      "c5-xinong-chapter", "c6-appendix-letter", "c7-cas-chapter",
                      "c8-dual-index", "c9-dark-appendix", "c10-note-pos"],
    "paragraphStyle": ["pa1-qinghai-26", "pa2-haikou-25", "pa3-hebei-30", "pa4-guangxi-15",
                       "pa5-tongliao-30", "pa6-ximeng-28", "pa7-jianyu-15", "pa8-xinong-20",
                       "pa9-degree-15", "pa10-compact-115"],
    "headerFooter": ["hf1-classic-enterprise", "hf2-centered-solemn", "hf3-project-oriented",
                     "hf4-consulting-page", "hf5-minimal-clean", "hf6-chapter-nav",
                     "hf7-dual-footer", "hf8-full-info-3col", "hf9-dark-none", "hf10-dark-page-only"],
}
LAYOUT_ALIAS_KEYS = {
    "preset": ("preset", "presets", "layouts"),
    "palette": ("palette", "palettes", "colors"),
    "cover": ("cover", "covers"),
    "decoration": ("decoration", "decorations"),
    "font": ("font", "fonts", "fontSchemes", "fontScheme"),
    "imageRatio": ("imageRatio", "imageRatios", "imageRatioScheme"),
    "imageRule": ("imageRule", "imageRules", "imageSourceRule"),
    "imageLayout": ("imageLayout", "imageLayouts", "imagePlacement"),
    "pageSetup": ("pageSetup", "pageSetups", "pageMargins"),
    "headingSystem": ("headingSystem", "headingSystems", "headings"),
    "tocStyle": ("tocStyle", "tocStyles", "toc"),
    "tableStyle": ("tableStyle", "tableStyles", "tables"),
    "captionSystem": ("captionSystem", "captionSystems", "captions"),
    "paragraphStyle": ("paragraphStyle", "paragraphStyles", "paragraphs"),
    "headerFooter": ("headerFooter", "headerFooters", "footer", "footers"),
}
PRESET_ALIASES = {
    "单栏流式": "single-column", "表格化布局": "tabular", "双栏分栏": "two-column",
    "卡片式布局": "card", "左图右文": "image-left", "章节分隔页": "divider",
    "数据行布局": "data-row", "右图左文": "image-right", "混合流式": "hybrid-flow", "极简留白": "minimal-clean",
}
PALETTE_ALIASES = {
    "深靛蓝": "deep-indigo", "暖棕金": "warm-bronze", "松绿": "pine-green",
    "砖红": "brick-red", "钢青": "steel-cyan", "炭灰极简": "charcoal",
    "深海蓝金": "deep-blue-gold", "墨绿暖橙": "ink-green-orange",
    "黑白灰一点红": "mono-red", "渐变蓝青": "gradient-blue-cyan",
}
COVER_ALIASES = {
    "满版色块": "full-block", "留白线条": "line-white", "图底压字": "image-underlay", "渐变": "gradient",
    "四角框线": "frame-corners", "顶部通栏色带": "top-banner", "对角分割": "split-diagonal",
    "纯文字极简": "minimal-type", "徽标居中": "emblem-center", "底部色带": "ribbon-bottom",
}
DECORATION_ALIASES = {
    "克制": "minimal", "标准": "standard", "丰富": "rich", "无装饰": "none",
    "仅标题线": "heading-rule", "侧边页签": "sidebar-tab", "四角圆点": "corner-dots",
    "章首色带": "section-band", "图标点缀": "icon-accent", "仅表头底纹": "table-fill",
}
FONT_ALIASES = {
    "政务公文风": "gov-gongwen", "工程务实风": "engineering",
    "现代商务风": "modern-business", "典雅书卷风": "elegant-classic",
    "暗标安全风": "dark-safe", "仿宋GB2312风": "gb2312-classic", "黑宋简约风": "hei-song-simplified",
    "楷体书卷风": "kai-literary", "全仿宋公文风": "fangsong-official", "混排安全风": "mixed-safe",
}
IMAGE_RATIO_ALIASES = {
    "无图": "none", "低图比": "low", "中图比": "mid", "高图比": "high",
    "极低图比": "ultra-low", "偏低图比": "low-mid", "偏高图比": "mid-high",
    "高强图比": "very-high", "整页图版": "full", "仅附表": "appendix-only",
}
IMAGE_RULE_ALIASES = {
    "上传优先": "upload-first", "搜索补图": "search-supplement",
    "AI 生图": "ai-render", "ai生图": "ai-render",
    "混合策略": "hybrid", "暗标安全": "dark-safe-img", "暗标安全图": "dark-safe-img",
    "仅平面图": "plan-only", "仅现场照片": "photo-only", "仅图表": "chart-only",
    "搜索核验": "search-verify", "搜索人工核验": "search-verify", "无图源": "no-source",
}
IMAGE_LAYOUT_ALIASES = {
    "左右分栏": "split-h", "上下分栏": "split-v", "图文混排": "inline",
    "图组并排": "grid", "并排": "grid", "附图专页": "appendix",
    "侧注式": "side-note", "通栏横幅": "banner", "时间轴图": "timeline",
    "卡片混排": "card-mix", "无排版": "none",
}
HEADER_FOOTER_ALIASES = {
    "经典企业版": "hf1-classic-enterprise", "居中庄重": "hf2-centered-solemn",
    "项目导向": "hf3-project-oriented", "咨询商务": "hf4-consulting-page",
    "极简留白页眉页脚": "hf5-minimal-clean", "章节导航": "hf6-chapter-nav",
    "双栏页脚": "hf7-dual-footer", "全信息三栏": "hf8-full-info-3col",
    "暗标无页眉页脚": "hf9-dark-none", "暗标仅页码": "hf10-dark-page-only",
}
MICRO_LAYOUT_ALIASES = {
    "标准公文": "p1-standard-a4", "海南盲评": "p2-haikou-25", "剑鱼商务": "p3-jianyu-商务",
    "通辽": "p4-tongliao-317", "南阳": "p5-nanyang-32", "广西": "p6-guangxi-215",
    "河北": "p7-hb-25-20", "东师学位": "p8-nenu-学位", "国标学位": "p9-gbt-学位", "对称紧凑": "p10-symmetric-紧凑",
    "GB阿拉伯": "h1-gbt-arabic", "招标全阿拉伯": "h2-tender-arabic", "青海混排": "h3-qinghai-hybrid",
    "南阳七级": "h4-nanyang-7level", "剑鱼加粗": "h5-jianyu-bold", "科技报告": "h6-sci-report",
    "北大模板": "h7-pku-template", "东师学术": "h8-nenu-academic", "中科院学术": "h9-cas-academic",
    "通辽暗标": "h10-tongliao-tender",
    "剑鱼目录": "t1-jianyu-auto", "ZOL目录": "t2-zol-standard", "青海无页码目录": "t3-qinghai-nopage",
    "广西点线目录": "t4-guangxi-pointline", "东师缩进目录": "t5-nenu-indent", "中科院右对齐目录": "t6-cas-rightalign",
    "西农紧凑目录": "t7-xinong-compact", "图文双目录": "t8-dual-index", "WPS制表位目录": "t9-wps-tabstop",
    "两级目录": "t10-minimal-2level",
    "三线表": "tb1-three-line", "全线表": "tb2-full-line", "省线表": "tb3-saving-line",
    "表头底纹表": "tb4-header-fill", "网格细线表": "tb5-grid-fine", "无线表": "tb6-no-line",
    "暗标细线表": "tb7-dark-0.5", "居中表": "tb8-center-vh", "KPI行": "tb9-kpi-row", "续表": "tb10-split-continue",
    "全文依序编号": "c1-gbt-seq", "分章编号": "c2-cy-chapter", "就近编号": "c3-jianyu-neighbor",
    "东师位置": "c4-nenu-pos", "西农分章": "c5-xinong-chapter", "附录字母编号": "c6-appendix-letter",
    "中科院分章": "c7-cas-chapter", "图文双目录联动": "c8-dual-index", "暗标附图专页编号": "c9-dark-appendix",
    "图注表注": "c10-note-pos",
    "青海26磅": "pa1-qinghai-26", "海南25磅": "pa2-haikou-25", "河北30磅": "pa3-hebei-30",
    "广西1.5倍": "pa4-guangxi-15", "通辽30磅": "pa5-tongliao-30", "锡盟28磅": "pa6-ximeng-28",
    "剑鱼1.5倍": "pa7-jianyu-15", "西农20磅": "pa8-xinong-20", "学位1.5倍": "pa9-degree-15",
    "紧凑1.15倍": "pa10-compact-115",
}

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
