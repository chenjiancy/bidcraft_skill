# -*- coding: utf-8 -*-
"""一次性脚本：layout-presets.json v1.3 → v1.4 —— 所有设计元素统一为 10 套（15 组全 10）。
仅修改数据文件，校验后回写。"""
import json

P = r"E:\bidcraft_skill\共享资源\技术标风格\layout-presets.json"
doc = json.load(open(P, encoding="utf-8"))

# ---- palette 11→10：裁 eggplant-silver（无 recommendedFor、最不工程，需找回时增行即可）
doc["palettes"] = [r for r in doc["palettes"] if r["id"] != "eggplant-silver"]

# ---- presets 7→10
doc["presets"] += [
    {"id": "image-right", "name": "右图左文", "docx": "两列表格：右图占位 + 左文（image-left 镜像）",
     "degrade": "图缺失时降级 single-column 并披露"},
    {"id": "hybrid-flow", "name": "混合流式", "docx": "段落+表格+图片按内容自由混排，标题层级贯穿",
     "degrade": "图片/表格过宽时降级单栏居中"},
    {"id": "minimal-clean", "name": "极简留白", "docx": "宽页边距、轻网格、无装饰，正文信息密度低",
     "degrade": ""},
]

# ---- covers 4→10
doc["covers"] += [
    {"id": "frame-corners", "name": "四角框线", "docx": "白底 + 四角细线框 + 中部标题/单位/日期", "darkOk": True},
    {"id": "top-banner", "name": "顶部通栏色带", "docx": "页首通栏色块 + 下方留白标题区", "darkOk": True},
    {"id": "split-diagonal", "name": "对角分割", "docx": "斜向两色块分割 + 文字置于浅色区", "darkOk": True},
    {"id": "minimal-type", "name": "纯文字极简", "docx": "无图形元素，仅标题/单位/日期三行文字", "darkOk": True,
     "note": "无任何图形/图片，暗标最稳"},
    {"id": "emblem-center", "name": "徽标居中", "docx": "企业 LOGO 居中 + 下方标题/单位（明标）", "darkOk": False,
     "note": "含企业标识，暗标禁用"},
    {"id": "ribbon-bottom", "name": "底部色带", "docx": "白底 + 底部色带 + 右上竖排标题", "darkOk": True},
]

# ---- decorations 3→10
doc["decorations"] += [
    {"id": "none", "name": "无装饰", "docx": "无任何装饰元素，纯文本+表格", "darkOk": True,
     "note": "零装饰，暗标安全"},
    {"id": "heading-rule", "name": "仅标题线", "docx": "各级标题下方细横线，正文无装饰"},
    {"id": "sidebar-tab", "name": "侧边页签", "docx": "页面外侧色块页签导航（章号）"},
    {"id": "corner-dots", "name": "四角圆点", "docx": "页四角小圆点/圆角符号点缀"},
    {"id": "section-band", "name": "章首色带", "docx": "仅章节首页顶部装饰带，内页无装饰"},
    {"id": "icon-accent", "name": "图标点缀", "docx": "章节标题前小图标，无底纹无色带"},
    {"id": "table-fill", "name": "仅表头底纹", "docx": "只对表格表头使用配色底纹，其余零装饰", "darkOk": False,
     "note": "表头底纹带色，暗标禁用（暗标表头无底纹）"},
]

# ---- fontSchemes 5→10
doc["fontSchemes"] += [
    {"id": "gb2312-classic", "name": "仿宋GB2312风", "heading": "仿宋_GB2312", "body": "仿宋_GB2312",
     "western": "Times New Roman",
     "sizes": {"chapter": "18pt 小四 常规", "section": "18pt 小四 常规", "item": "18pt 小四 常规", "body": "18pt 小四 常规", "table": "10.5pt 五号", "caption": "9pt 小五"},
     "lineSpacing": 1.5, "system": "Win10/11 无 GB2312 版本，缺失回退仿宋",
     "darkOk": False,
     "note": "招标点名仿宋_GB2312 小四时按条款切换（南通监理条款）；以 overrides 覆盖"},
    {"id": "hei-song-simplified", "name": "黑宋简约风", "heading": "黑体", "body": "宋体",
     "western": "Times New Roman",
     "sizes": {"chapter": "16pt 三号 居中", "section": "14pt 四号", "item": "12pt 小四", "body": "12pt 小四", "table": "10.5pt 五号", "caption": "9pt 小五"},
     "lineSpacing": 1.5, "system": "系统自带", "darkOk": False,
     "note": "黑体标题+宋体正文，评标识别度最高"},
    {"id": "kai-literary", "name": "楷体书卷风", "heading": "黑体", "body": "楷体",
     "western": "Times New Roman",
     "sizes": {"chapter": "16pt 三号 居中", "section": "14pt 四号", "item": "12pt 小四", "body": "12pt 小四", "table": "10.5pt 五号", "caption": "9pt 小五"},
     "lineSpacing": 1.5, "system": "系统自带", "darkOk": False,
     "note": "正文楷体，适用于文字性章节/前言；篇幅约+5%"},
    {"id": "fangsong-official", "name": "全仿宋公文风", "heading": "仿宋", "body": "仿宋",
     "western": "Times New Roman",
     "sizes": {"chapter": "22pt 二号 居中", "section": "16pt 三号", "item": "16pt 三号", "body": "16pt 三号", "table": "12pt 四号", "caption": "10.5pt 五号"},
     "lineSpacing": 1.5, "system": "系统自带", "darkOk": False,
     "note": "对标 GB/T 9704-2012 党政机关公文：全仿宋、章二号居中"},
    {"id": "mixed-safe", "name": "混排安全风", "heading": "黑体", "body": "宋体",
     "western": "Times New Roman",
     "sizes": {"chapter": "16pt 三号 居中", "section": "14pt 四号", "item": "12pt 小四", "body": "12pt 小四", "table": "10.5pt 五号", "caption": "9pt 小五"},
     "lineSpacing": 1.5, "system": "系统自带", "darkOk": False,
     "note": "无加色/无装饰字，明标低风险；与 dark-safe 区别：标题保留黑体不加粗"},
]

# ---- imageRatios 4→10
doc["imageRatios"] += [
    {"id": "ultra-low", "name": "极低图比", "ratio": "1:19", "imageShare": 0.05, "darkOk": True,
     "note": "图占版心约5%；仅关键证据位（业绩/资质/荣誉证书）"},
    {"id": "low-mid", "name": "偏低图比", "ratio": "2:8", "imageShare": 0.2, "darkOk": True,
     "note": "图占版心约20%；理论密集型章节适度配图"},
    {"id": "mid-high", "name": "偏高图比", "ratio": "4:6", "imageShare": 0.4, "darkOk": False,
     "note": "图占版心约40%；过程照片+文字混合章节"},
    {"id": "very-high", "name": "高强图比", "ratio": "6:4", "imageShare": 0.6, "darkOk": False,
     "note": "图占版心约60%；图证型章节（平面布置/安全文明/样板引路）"},
    {"id": "full", "name": "整页图版", "ratio": "7:3", "imageShare": 0.7, "darkOk": False,
     "note": "图占版心约70%；现场鸟瞰/总平面图专页"},
    {"id": "appendix-only", "name": "仅附表", "ratio": "0:10(正文)", "imageShare": 0, "darkOk": True,
     "note": "正文零图，图表全部集中附末（明标版暗标式）；对应 imageLayout=appendix"},
]

# ---- imageRules 5→10
doc["imageRules"] += [
    {"id": "plan-only", "name": "仅平面图", "source": "CAD 图纸转图片", "darkOk": True,
     "note": "施工总平面/进度计划/工艺流程图（CAD→JPG 等比缩放不超页边距，剑鱼指南）；图表文字五号宋体黑字"},
    {"id": "photo-only", "name": "仅现场照片", "source": "现场/搜索实景照", "darkOk": False,
     "note": "真实场景照片为主；须人工核验真实性与版权，避免人脸/品牌"},
    {"id": "chart-only", "name": "仅图表", "source": "流程图/曲线/表格化图", "darkOk": True,
     "note": "无实景图；组织结构/网络计划/检测曲线（图表内五号宋体黑字常规可暗标）"},
    {"id": "search-verify", "name": "搜索+人工核验", "source": "联网搜索后人工确认", "darkOk": False,
     "note": "搜索结果必须人工确认真实性/版权/清晰度后方可使用（国家版权局 2020 通知口径）"},
    {"id": "no-source", "name": "无图源", "source": "不配图", "darkOk": True,
     "note": "与 imageRatio=none 联动：不生成/不插入任何图表"},
]

# ---- imageLayouts 5→10
doc["imageLayouts"] += [
    {"id": "side-note", "name": "侧注式", "darkOk": True,
     "note": "窄图+右侧注文（图注规范）；图小、可灰度，暗标可用"},
    {"id": "banner", "name": "通栏横幅", "darkOk": False,
     "note": "整页宽图置于章首/节首（视野图）；图占版心宽 100%"},
    {"id": "timeline", "name": "时间轴图", "darkOk": False,
     "note": "进度/里程碑图沿时间轴排布（横道图/网络计划）"},
    {"id": "card-mix", "name": "卡片混排", "darkOk": False,
     "note": "图卡+文字卡混排（数据行布局配套）；docx 无圆角以直角呈现"},
    {"id": "none", "name": "无排版", "darkOk": True,
     "note": "不排图（与 imageRatio=none 联动）；tech-export 跳过图片阶段"},
]

# ---- headerFooters 10（新增组：补齐页眉页脚设计；hf9/hf10 暗标）
doc["headerFooters"] = [
    {"id": "hf1-classic-enterprise", "name": "经典企业版", "header": "左 LOGO+企业名，右章节名，0.5pt 分隔线", "footer": "页脚居中 -N-", "pageMode": "with-page", "darkOk": False,
     "note": "默认；小五号宋体/仿宋，palette.heading 色；LOGO 缺失降级仅文字"},
    {"id": "hf2-centered-solemn", "name": "居中庄重", "header": "页眉居中企业名（小五）", "footer": "页脚居中页码", "pageMode": "with-page", "darkOk": False,
     "note": "对称居中，庄重正式"},
    {"id": "hf3-project-oriented", "name": "项目导向", "header": "左企业名，右项目名", "footer": "页脚居中 -N-", "pageMode": "with-page", "darkOk": False,
     "note": "突出项目归属"},
    {"id": "hf4-consulting-page", "name": "咨询商务", "header": "页眉右页码，下细线", "footer": "页脚第 N 页 共 M 页", "pageMode": "with-page", "darkOk": False,
     "note": "咨询/设计院惯用"},
    {"id": "hf5-minimal-clean", "name": "极简留白", "header": "无页眉", "footer": "页脚居中 -N-", "pageMode": "with-page", "darkOk": False,
     "note": "无企业信息，弱品牌"},
    {"id": "hf6-chapter-nav", "name": "章节导航", "header": "左 LOGO+企业名，右完整章名", "footer": "页脚居中 -N-", "pageMode": "with-page", "darkOk": False,
     "note": "右侧随章动态更新，导航性强"},
    {"id": "hf7-dual-footer", "name": "双栏页脚", "header": "页眉企业名+项目名", "footer": "页脚左项目简称，右页码", "pageMode": "with-page", "darkOk": False,
     "note": "信息分布均衡"},
    {"id": "hf8-full-info-3col", "name": "全信息三栏", "header": "LOGO+企业名｜项目名｜章节名", "footer": "页脚居中 -N-", "pageMode": "with-page", "darkOk": False,
     "note": "须确认招标文件不禁页眉企业信息"},
    {"id": "hf9-dark-none", "name": "暗标无页眉页脚", "header": "无页眉", "footer": "无页码无页脚", "pageMode": "none", "darkOk": True,
     "note": "青海/海南/贵州/济南主流：不编页码、不设页眉页脚"},
    {"id": "hf10-dark-page-only", "name": "暗标仅页码", "header": "页眉必须空", "footer": "页脚纯页码，全文连续", "pageMode": "page-only", "darkOk": True,
     "note": "通辽 -N- 底端居中；雄县 Times New Roman 小五居中；实际格式按招标原文"},
]

# ---- default 增 headerFooter
doc["default"]["headerFooter"] = "hf1-classic-enterprise"

# ---- version/note
doc["version"] = "1.4"
doc["updated"] = "2026-10-22"
doc["note"] = ("共享级排版预设（十五组均为数组，可增行表，全部统一为 10 种方案）。"
               "色值经 T13 色卡预览确认（2026-10-21，11 色）；2026-10-22 v1.4 统一十方案："
               "preset 7→10、palette 11→10（裁 eggplant-silver，如需找回增行即可）、cover 4→10、decoration 3→10、"
               "font 5→10、imageRatio 4→10、imageRule 5→10、imageLayout 5→10，新增 headerFooters 10 套（含暗标双态）；"
               "微观排版六组（pageSetups/headingSystems/tocStyles/tableStyles/captionSystems/paragraphStyles）各 10 套。"
               "暗标：font 强制 dark-safe、图片二选一（none 或 dark-safe-img+appendix）、headerFooter 二选一（hf9/hf10），"
               "微观六组按招标条款自动注入不开放选择。预设只影响 tech-export，不改变正文 md 内容。")

json.dump(doc, open(P, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print("WRITTEN v1.4")

# ---- 校验
doc2 = json.load(open(P, encoding="utf-8"))
groups = ["presets", "palettes", "covers", "decorations", "fontSchemes", "imageRatios",
          "imageRules", "imageLayouts", "pageSetups", "headingSystems", "tocStyles",
          "tableStyles", "captionSystems", "paragraphStyles", "headerFooters"]
for g in groups:
    rows = doc2[g]
    ids = [r["id"] for r in rows]
    assert len(rows) == 10, (g, len(rows))
    assert len(ids) == len(set(ids)), (g, "dup")
    assert all(r.get("name") for r in rows), (g, "name")
    print("%-18s 10 OK (%s)" % (g, " ".join(ids)))
print("default fields:", len(doc2["default"]), list(doc2["default"].keys()))
print("ALL OK")
