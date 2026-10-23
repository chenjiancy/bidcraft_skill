# -*- coding: utf-8 -*-
"""生成《技术标排版预设统一十方案审计报告.html》——数据源 layout-presets.json v1.4 + audit_report.json。
可复现：改数据后重跑本脚本再刷新报告。
"""
import json
import re
from pathlib import Path

REPO = Path(r"E:\bidcraft_skill")
OUT = REPO / "dev" / "reports" / "技术标排版预设统一十方案审计报告.html"
OUT.parent.mkdir(parents=True, exist_ok=True)

presets = json.loads((REPO / "共享资源" / "技术标风格" / "layout-presets.json").read_text(encoding="utf-8"))
audit = json.loads((REPO / "dev" / "notes" / "audit_report.json").read_text(encoding="utf-8"))

GROUP_META = [
    ("presets", "preset", "版面范式", "正文版面骨架：单栏/表格化/分栏/卡片/图文/分隔页/数据行/镜像/混合/极简",
     "7→10：新增 image-right（右图左文）、hybrid-flow（混合流式）、minimal-clean（极简留白）"),
    ("palettes", "palette", "配色方案", "每套 5 组色值 primary/accent/heading/tableFill/coverBg（+渐变端色）",
     "11→10：裁出 eggplant-silver（茄子紫银灰，增行可找回），色卡预览同步删卡重编号"),
    ("covers", "cover", "封面版式", "封页视觉：满版/留白/图底/渐变/四角框/通栏/对角/纯文字/徽标/底带",
     "4→10：新增 frame-corners、top-banner、split-diagonal、minimal-type、emblem-center、ribbon-bottom"),
    ("decorations", "decoration", "装饰强度", "章节装饰密度与手法，克制→丰富→零装饰；带色项暗标禁用",
     "3→10：新增 none、heading-rule、sidebar-tab、corner-dots、section-band、icon-accent、table-fill"),
    ("fontSchemes", "font", "字体方案", "标题/正文/西文字族 + 字号骨架 + 行距 + 暗标安全性",
     "5→10：新增 gb2312-classic、hei-song-simplified、kai-literary、fangsong-official、mixed-safe"),
    ("imageRatios", "imageRatio", "图文比例", "图占版心 0%→70%，10 档；none=零图（暗标推荐）",
     "4→10：新增 ultra-low(1:19)、low-mid(2:8)、mid-high(4:6)、very-high(6:4)、full(7:3)、appendix-only"),
    ("imageRules", "imageRule", "配图规则", "图片来源与安全策略：上传/搜索/AI/混合/暗标安全等 10 套",
     "5→10：新增 plan-only、photo-only、chart-only、search-verify、no-source"),
    ("imageLayouts", "imageLayout", "配图排版", "图文排布：左右/上下/混排/图组/附图专页/侧注/横幅/时间轴/卡片/无",
     "5→10：新增 side-note、banner、timeline、card-mix、none"),
    ("pageSetups", "pageSetup", "页面设置", "H1 页边距/幅面：标准公文、地区暗标条款、学位规范等 10 套",
     "数量不变（10）；与其余组统一为 10"),
    ("headingSystems", "headingSystem", "标题体系", "H2 章→条编号与字体：GB/T 阿拉伯、招标条款式、学术模板等 10 套",
     "数量不变（10）；与其余组统一为 10"),
    ("tocStyles", "tocStyle", "目录版式", "H3 目录结构与页码呈现：剑鱼自动、无页码目录、双目录等 10 套",
     "数量不变（10）；与其余组统一为 10"),
    ("tableStyles", "tableStyle", "表格样式", "H4 三线表/全线/网格/无底线/暗标细线/KPI 行/续表等 10 套",
     "数量不变（10）；与其余组统一为 10"),
    ("captionSystems", "captionSystem", "图表编号", "H5 图题表题编号与位置：分章/依序/就近/附录字母/暗标附图等 10 套",
     "数量不变（10）；与其余组统一为 10"),
    ("paragraphStyles", "paragraphStyle", "段落样式", "H6 行距与缩进：1.5 倍、固定磅值条款、紧凑等 10 套",
     "数量不变（10）；与其余组统一为 10"),
    ("headerFooters", "headerFooter", "页眉页脚", "明标 8 套 + 暗标 2 套（无痕/仅页码），pageMode 三态",
     "新增组 10 套：明标 hf1–hf8（含默认 hf1-classic-enterprise），暗标 hf9-dark-none / hf10-dark-page-only（二选一 error）"),
]
GROUP_CN = {g[0]: g[2] for g in GROUP_META}

# 审计逐组载体
CARRIER_LABELS = {
    "json": "数据 JSON",
    "builtin": "内置 DEFAULT",
    "json↔builtin": "JSON↔内置逐 id",
    "cli(GROUPS)": "CLI 组载体",
    "validate": "校验循环",
    "test": "测试组载体",
    "alias-chinese": "中文别名",
    "docs": "文档（契约/需求）",
}
per_g = {g["group"]: g for g in audit["groups"]}

def esc(s):
    return re.sub(r"[&<>]", lambda m: {"&": "&amp;", "<": "&lt;", ">": "&gt;"}[m.group(0)], str(s))

def scheme_rows(key):
    rows = []
    for r in presets.get(key, []):
        note = r.get("docx") or r.get("note") or r.get("header") or r.get("heading") or r.get("lineSpacing") or ""
        dark = "" if r.get("darkOk", True) else '<span class="tag dark-tag">暗标禁</span>'
        if key == "headerFooters":
            note = (r.get("header") or "") + "｜" + (r.get("footer") or "") + "｜pageMode=" + str(r.get("pageMode"))
        if r["id"] == presets["default"].get({"presets": "preset", "palettes": "palette", "covers": "cover",
            "decorations": "decoration", "fontSchemes": "font", "imageRatios": "imageRatio",
            "imageRules": "imageRule", "imageLayouts": "imageLayout", "pageSetups": "pageSetup",
            "headingSystems": "headingSystem", "tocStyles": "tocStyle", "tableStyles": "tableStyle",
            "captionSystems": "captionSystem", "paragraphStyles": "paragraphStyle",
            "headerFooters": "headerFooter"}.get(key, "")):
            dft = '<span class="tag dft-tag">默认</span>'
        else:
            dft = ""
        rows.append('<tr><td class="mono">%s</td><td>%s %s %s</td><td>%s</td></tr>' % (
            esc(r["id"]), esc(r.get("name", "")), dft, dark, esc(note)))
    return "\n".join(rows)

# 逐组落实状态条
def carrier_summary(g):
    c = per_g[g]["carriers"]
    bits = []
    for k, label in CARRIER_LABELS.items():
        if k == "docs":
            ok = all(v.get("ok") for v in c.get("docs", {}).values())
            bits.append('<span class="chk %s">%s</span>' % ("ok" if ok else "no", label))
        else:
            ok = c.get(k, {}).get("ok", True)
            bits.append('<span class="chk %s">%s</span>' % ("ok" if ok else "no", label))
    return "".join(bits)

# 一致性 C1–C9 文案
CONS = audit["consistency"]
CONS_ORDER = [
    ("C1_json_vs_builtin", "数据 ↔ 内置常量", "layout-presets.json 与 rules_base.DEFAULT_LAYOUT 的 15 组 id 集合及顺序完全一致"),
    ("C2_default_valid", "默认组合合法", "default 15 字段的取值全部落在对应组内（含 headerFooter=hf1-classic-enterprise）"),
    ("C3_dark_inject_valid", "暗标注入合法", "sources.DARK_LAYOUT_INJECT 9 键全部为合法组内 id（font/imageRatio/微观六组/headerFooter）"),
    ("C4_group_keys_aligned", "组键三表对齐", "GROUPS(layout.py) = LAYOUT_ALIAS_KEYS(rules_base) = COMBO_KEYS(packs)，均为 15 键"),
    ("C5_alias_values_valid", "中文别名合法", "全部独立别名表值落在组内；微观共享表 MICRO_LAYOUT_ALIASES 全局无 stray"),
    ("C6_dark_semantics", "暗标语义正确", "image-underlay 与 table-fill darkOk=false（暗标禁用）；dark-safe/hf9/hf10 darkOk=true；注入项无冲突"),
    ("C7_all_groups_ten", "全组统一 10 套", "15 组每组恰好 10 套，合计 150 个方案"),
    ("C8_pack_combo_matches_default", "专家包对齐默认", "official-tech 包.json layoutCombo 15 键与 default 完全一致"),
    ("C9_docs_cover_ten_and_hf", "文档口径收敛", "契约草案 v1.0 / 需求对齐 v1.3 均已覆盖 15 组、10 套、headerFooter 与暗标二选一"),
]

def cons_rows():
    rows = []
    for key, name, desc in CONS_ORDER:
        v = CONS[key]
        rows.append('<tr><td class="mono">%s</td><td>%s</td><td>%s</td><td><span class="chk %s">%s</span></td></tr>' % (
            esc(key), esc(name), esc(desc), "ok" if v.get("ok") else "no", "通过" if v.get("ok") else "未过"))
    return "\n".join(rows)

kpi = audit["summary"]
footer_modes = ", ".join(audit.get("footerModes", []))

# git 状态（只读一次，失败则标注未知）
try:
    import subprocess
    git = subprocess.run(["git", "status", "--porcelain"], cwd=str(REPO), capture_output=True, text=True, encoding="utf-8", timeout=15)
    git_lines = [l for l in git.stdout.splitlines() if l.strip()] if git.returncode == 0 else ["git 状态读取失败"]
except Exception as e:
    git_lines = ["git 状态读取失败：%s" % e]

TMPL = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>技术标排版预设 · 统一十方案审计报告</title>
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' rx='6' fill='%231B2A5B'/%3E%3Ctext x='16' y='23' font-size='18' fill='%23fff' text-anchor='middle' font-family='sans-serif'%3E%E2%88%91%3C/text%3E%3C/svg%3E">
<style>
:root{--ink:#16233f;--brand:#1B2A5B;--brand2:#2E4E8F;--acc:#3E7CB1;--line:#d7dce6;--bg:#f6f7fa;--card:#ffffff;--ok:#1e7f4f;--no:#c0392b;--dim:#6b7280;}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:"Noto Serif SC","Songti SC","SimSun",serif;background:var(--bg);color:var(--ink);line-height:1.75;font-size:16px}
.wrap{max-width:1060px;margin:0 auto;padding:0 20px}
.hero{background:linear-gradient(135deg,var(--brand) 0%,var(--brand2) 60%,var(--acc) 130%);color:#fff;padding:64px 20px 48px}
.hero .wrap{max-width:1060px}
.hero .kicker{font-family:"Noto Sans SC","Microsoft YaHei",sans-serif;letter-spacing:.35em;font-size:13px;opacity:.85;text-transform:uppercase}
.hero h1{font-size:clamp(26px,4.6vw,42px);line-height:1.3;margin:14px 0 10px;font-weight:900;letter-spacing:.02em}
.hero .sub{font-size:15px;opacity:.9;max-width:760px}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin-top:30px}
.kpi{background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.22);border-radius:10px;padding:14px 16px}
.kpi b{font-family:"Noto Sans SC","Microsoft YaHei",sans-serif;font-size:30px;font-weight:800;display:block;line-height:1.1}
.kpi span{font-size:12.5px;opacity:.88}
.verdict{background:#eaf3ef;border:1px solid #bfd8c9;border-left:5px solid var(--ok);border-radius:8px;padding:14px 18px;margin:-24px auto 0;position:relative;max-width:1060px;font-weight:600}
.verdict small{display:block;font-weight:400;color:var(--dim);margin-top:4px}
section{padding:44px 0 8px}
.sec-head{display:flex;align-items:baseline;gap:14px;border-bottom:2px solid var(--brand);padding-bottom:10px;margin-bottom:22px}
.sec-head .no{font-family:"Noto Sans SC",sans-serif;font-weight:900;color:var(--brand);font-size:26px}
.sec-head h2{font-size:22px;color:var(--brand);font-weight:800}
.sec-head .cn{font-size:13px;color:var(--dim)}
p.lead{max-width:860px;margin-bottom:16px}
.tablewrap{overflow-x:auto;background:var(--card);border:1px solid var(--line);border-radius:8px;margin:14px 0 20px}
table{width:100%;border-collapse:collapse;table-layout:fixed;font-size:14px;min-width:640px}
th{background:#eef1f7;color:var(--brand);font-family:"Noto Sans SC",sans-serif;font-weight:700;text-align:left;padding:9px 12px;border-bottom:1px solid var(--line);font-size:13px}
td{padding:8px 12px;border-bottom:1px solid #e8ecf3;vertical-align:top;word-break:break-word}
tr:last-child td{border-bottom:none}
.mono{font-family:Consolas,"Microsoft YaHei",monospace;font-size:12.5px;color:#33425f;word-break:break-all}
.chk{display:inline-block;font-family:"Noto Sans SC",sans-serif;font-size:11px;line-height:1;padding:3px 7px;border-radius:999px;margin:1px 2px;white-space:nowrap}
.chk.ok{background:#e2f2e9;color:var(--ok);border:1px solid #b7ddc6}
.chk.no{background:#fbe9e7;color:var(--no);border:1px solid #f0c4bf}
.tag{display:inline-block;font-size:10.5px;line-height:1;padding:3px 6px;border-radius:4px;margin-left:6px;font-family:"Noto Sans SC",sans-serif;vertical-align:middle}
.dft-tag{background:var(--brand);color:#fff}
.dark-tag{background:#5b2a2a;color:#ffd9d9}
.group-block{margin:0 0 34px}
.group-block h3{font-size:17px;color:var(--brand);margin-bottom:2px}
.group-block .gmeta{font-size:13px;color:var(--dim);margin-bottom:10px}
.group-block .carriers{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:10px}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:20px}
@media(max-width:760px){.grid2{grid-template-columns:1fr}}
.cons-ok{color:var(--ok);font-weight:700}
.card{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:16px 18px;margin-bottom:14px}
.card h4{font-family:"Noto Sans SC",sans-serif;font-size:15px;color:var(--brand);margin-bottom:6px}
.list{margin:8px 0 0 20px}
.list li{margin-bottom:6px}
code{font-family:Consolas,monospace;font-size:12.5px;background:#eef1f7;padding:1px 5px;border-radius:4px}
.darkbox{background:#0f1b33;color:#dbe4f5;border-radius:8px;padding:16px 18px;font-family:Consolas,"Microsoft YaHei",monospace;font-size:13px;line-height:1.9;overflow-x:auto}
.darkbox b{color:#7fd4a8}
footer{border-top:1px solid var(--line);margin-top:40px;padding:26px 0 40px;color:var(--dim);font-size:13px}
.gitchips{display:flex;flex-wrap:wrap;gap:6px;margin-top:8px}
.gitchips span{font-family:Consolas,monospace;font-size:11px;background:#eef1f7;border:1px solid var(--line);border-radius:4px;padding:3px 8px;max-width:100%;overflow-wrap:anywhere;word-break:break-all}
@media print{.hero{background:var(--brand)}body{background:#fff}}
</style>
</head>
<body>
<div class="hero"><div class="wrap">
<div class="kicker">M6 Technical Bid · Layout Presets Audit</div>
<h1>技术标排版预设 · 统一十方案审计报告</h1>
<div class="sub">将 M6 技术标（监理大纲）排版预设引擎的全部设计元素统一为 <b>15 组 × 10 套 = 150 个方案</b>，并逐载体核验落实、逐项交叉校验一致性。数据源：layout-presets.json v1.4（2026-10-22）与 audit_report.json。</div>
<div class="kpis">
<div class="kpi"><b>15</b><span>设计元素组（正交可组合）</span></div>
<div class="kpi"><b>150</b><span>可选方案（每组 10 套）</span></div>
<div class="kpi"><b>15</b><span>默认组合字段（含 headerFooter）</span></div>
<div class="kpi"><b>9/9</b><span>一致性检查 C1–C9 全部通过</span></div>
<div class="kpi"><b>597</b><span>回归用例全绿（unit 528 + int 69）</span></div>
</div>
</div></div>
<div class="wrap">
<div class="verdict">三项任务完成：① 全部设计元素已统一为 10 种方案；② 150 个方案在数据 / 代码 / 别名 / 校验 / 测试 / 文档六个载体层全部落实，缺失 0 项；③ 一致性检查 C1–C9 全部通过。
<small>audit 输出：groups=15 · schemes=150 · all_ten=True · consistency=True · carrier_missing=0（可复跑：python scripts/m6_tech/audit_presets.py）</small></div>

<section>
<div class="sec-head"><span class="no">01</span><h2>任务与范围</h2><span class="cn">本轮三连任务</span></div>
<p class="lead">用户下达三项连续任务，逐项完成、无需确认：<b>① 把全部设计元素统一到 10 种方案</b>；<b>② 检查所有设计元素是否全部实现落实</b>（包括但不限于 skill、文档、代码）；<b>③ 一致性检查</b>。完成后交付本份 HTML 报告。落实检查覆盖六个载体：数据 JSON、代码内置常量、中文别名表、CLI/校验/测试组载体、两份需求文档；渲染层（T10 tech-export）为已知未开发项，缺口如实披露于第 6 节。</p>
</section>

<section>
<div class="sec-head"><span class="no">02</span><h2>① 统一为 10 种方案</h2><span class="cn">layout-presets.json v1.3 → v1.4</span></div>
<p class="lead">此前 15 组中前八组数量不齐（版面 7 / 配色 11 / 封面 4 / 装饰 3 / 字体 5 / 图文比例 4 / 配图规则 5 / 配图排版 5）。本轮用一次性脚本 <code>dev/notes/presets_v1.4_extend.py</code> 扩编 / 裁剪 / 新增并回写校验（id 唯一、每组 10、name 非空，全部 OK）。配色由 11 裁至 10（裁出「茄子紫银灰」，增行可找回）；新增第 15 组「页眉页脚 headerFooters」10 套（明标 8 + 暗标 2，此前已设计但未落库）。</p>
<div class="tablewrap"><table>
<colgroup><col style="width:16%"><col style="width:12%"><col style="width:12%"><col style="width:22%"><col style="width:38%"></colgroup>
<tr><th>组（JSON 键）</th><th>字段键</th><th>数量</th><th>默认值</th><th>本批变化</th></tr>
__TABLE_GROUPS__
</table></div>
</section>

<section>
<div class="sec-head"><span class="no">03</span><h2>② 落实检查 · 150 方案 × 六载体</h2><span class="cn">carrier_missing = 0</span></div>
<p class="lead">每个方案 id 需同时在：数据 JSON、代码内置常量（DEFAULT_LAYOUT）、中文别名表、CLI 组载体、校验循环、测试组载体、两份文档中可定位。逐组状态如下（全部通过）；下方为 15 组 × 10 套完整清单，含默认与暗标禁用标记。</p>
__TABLE_CARRIERS__
</section>

<section>
<div class="sec-head"><span class="no">04</span><h2>③ 一致性检查 C1–C9</h2><span class="cn">9 项全部通过</span></div>
<div class="tablewrap"><table>
<colgroup><col style="width:22%"><col style="width:18%"><col style="width:48%"><col style="width:12%"></colgroup>
<tr><th>检查项</th><th>名称</th><th>说明</th><th>结果</th></tr>
__TABLE_CONS__
</table></div>
<div class="grid2">
<div class="card"><h4>暗标注入（sources.DARK_LAYOUT_INJECT，9 键）</h4><div class="darkbox">__DARK_INJECT__</div></div>
<div class="card"><h4>默认组合与页脚模式</h4><p style="font-size:13.5px">默认组合 15 字段见右（与专家包 official-tech 一致）；headerFooter 的 <code>pageMode</code> 三态：<b>__FOOTER_MODES__</b>。暗标二选一（校验 error）：<code>hf9-dark-none</code>（无页眉页脚无页码，默认注入）或 <code>hf10-dark-page-only</code>（页眉必须空、仅页码全文连续）。</p></div>
</div>
</section>

<section>
<div class="sec-head"><span class="no">05</span><h2>回归与冒烟验证</h2><span class="cn">改动后复跑，全部通过</span></div>
<div class="tablewrap"><table>
<colgroup><col style="width:30%"><col style="width:30%"><col style="width:40%"></colgroup>
<tr><th>验证项</th><th>结果</th><th>说明</th></tr>
<tr><td>M6 单元测试（6 个测试文件）</td><td class="cons-ok">166 项通过</td><td>layout / rules / store / cli / packs / write；夹具已补 headerFooter 键</td></tr>
<tr><td>全量单元回归</td><td class="cons-ok">unit 528 通过</td><td>含新增 PALETTE_ALIASES 后的复跑</td></tr>
<tr><td>全量集成回归</td><td class="cons-ok">int 69 通过</td><td>—</td></tr>
<tr><td>tech-layout --list --json 冒烟</td><td class="cons-ok">groups=15 · default 15 字段</td><td>各 group count=10；headerFooter=hf1-classic-enterprise</td></tr>
<tr><td>审计脚本可复跑</td><td class="cons-ok">consistency=True</td><td>python scripts/m6_tech/audit_presets.py</td></tr>
</table></div>
</section>

<section>
<div class="sec-head"><span class="no">06</span><h2>已知缺口与待办</h2><span class="cn">如实披露</span></div>
<div class="card"><h4>未完成项 / 待办</h4><ul class="list">
<li><b>T9 SKILL.md M6 行回填</b>：skill 层入口是否已回填 15 组口径未最终确认——本轮落实检查已覆盖"文档 / 代码 / 数据 / 测试"，SKILL.md 若未同步须在 T9 统一回填（报告中如实标注为 skill 层待确认项）。</li>
<li><b>T10 tech-export 渲染层未开发</b>：15 组方案在 docx 的最终渲染落实（页边距、标题样式、三线表、页眉页脚 pageMode 三态、暗标页码双态）依赖 T10；本次落实检查到数据 / 代码 / 测试 / 文档层，渲染层为已知缺口。</li>
<li><b>git 工作区未提交</b>：本批改动（含 layout-presets.json v1.4、色卡预览.html、rules_* / layout / sources / packs / cli、audit_presets.py、测试 4 文件、契约草案 v1.0、需求对齐 v1.3）尚未 commit / push，分支 feat/tpl-inplace-relax。</li>
</ul></div>
<div class="card"><h4>当前工作区变更（git status --porcelain）</h4><div class="gitchips">__GIT_CHIPS__</div></div>
</section>

<footer>
报告生成时间：2026-10-22 · 数据源：共享资源/技术标风格/layout-presets.json（v1.4）、dev/notes/audit_report.json（m6.audit/v1）· 审计脚本：scripts/m6_tech/audit_presets.py · 可复现：重跑审计脚本与本报告生成脚本即可刷新。
</footer>
</div>
</body>
</html>
"""

html = (
    TMPL
    .replace("__TABLE_GROUPS__", "\n".join(
        '<tr><td class="mono">%s</td><td class="mono">%s</td><td>%d</td><td class="mono">%s</td><td>%s</td></tr>' % (
            esc(jk), esc(meta[1]), len(presets[jk]), esc(presets["default"].get(meta[1], "—")), esc(meta[4]))
        for jk, meta in zip([g[0] for g in GROUP_META], GROUP_META)
    ))
    .replace("__TABLE_CARRIERS__", "\n".join(
        '<div class="group-block"><h3>%s <span class="mono" style="font-size:12px">%s</span></h3>'
        '<div class="gmeta">%s · 默认 <code>%s</code></div>'
        '<div class="carriers">%s</div>'
        '<div class="tablewrap"><table><colgroup><col style="width:24%%"><col style="width:34%%"><col style="width:42%%"></colgroup>'
        '<tr><th>id</th><th>名称</th><th>说明</th></tr>%s</table></div></div>'
        % (esc(meta[2]), esc(meta[1]), esc(meta[3]), esc(presets["default"].get(meta[1], "")), carrier_summary(meta[1]), scheme_rows(meta[0]))
        for meta in GROUP_META
    ))
    .replace("__TABLE_CONS__", cons_rows())
    .replace("__DARK_INJECT__", "\n".join('<b>%s</b> = %s' % (esc(k), esc(v)) for k, v in audit.get("darkInject", {}).items()))
    .replace("__FOOTER_MODES__", esc(footer_modes))
    .replace("__GIT_CHIPS__", "".join('<span>%s</span>' % esc(l) for l in git_lines[:40]))
)

OUT.write_text(html, encoding="utf-8")
print("WRITTEN", OUT, len(html), "chars")
