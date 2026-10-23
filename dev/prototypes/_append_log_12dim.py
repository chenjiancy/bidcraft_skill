# -*- coding: utf-8 -*-
"""向 development-log.md 追加 12 维落实轮条目（UTF-8 安全）。"""
from pathlib import Path

log = Path(r"E:\bidcraft_skill\dev\notes\development-log.md")
entry = """

## 2026-10-23 12 维版面维度全面落实（任务18，渲染层 export.py）
- 背景：维度盘点轮查出 12 个缺口（部分实现/仅数据/缺失），用户指示"逐一全面落实"。范围=scripts/m6_tech/export.py 渲染层 + fixture 预设复制 + 测试/日志。
- 实现（批次1-4）：
  - 批次1 数据接入+微观层：_parse_gutter/_font_of_level_text/_parse_heading_system/_parse_numbering/_heading_prefix/_parse_table_style/_parse_caption/_parse_toc 解析辅助；_Renderer 构造扩展 font/heading/toc/table/caption/decoration/imageLayout/imageShare/imageRule；_heading 支持 4 种编号风格（arabic/chinese-first/seven/tongliao-arabic，文本自带编号跳过）+ levels 字号字体优先 + 装饰（heading-rule/standard 底线、sidebar-tab 左色条、rich 底纹、section-band 章首主色底白字、icon-accent ■）；_body 对齐+行距；_table 线型（three-line/full/none/saving）+ 表头底纹 + 表题位置 + 分章 N-N 编号；_list 统一字体。
  - 批次2 图片系统+封面：render_md 图片分支 → _image_render（split-h/split-v/inline/side-note/banner/timeline/card-mix/appendix/grid 9 布局）；_img_width（imageShare→图宽 5/7/9/12/14/15.5cm）；_image_rule_ok（photo-only/chart-only/plan-only 按图题关键词过滤）；_caption_text 全文 seq vs 分章 N-N vs 附表/附图前缀；新增 _render_cover 10 封面方案（full-block/line-white/image-underlay/gradient/frame-corners/top-banner/split-diagonal/minimal-type/emblem-center/ribbon-bottom）。
  - 批次3 页面/页眉页脚：tocStyle 驱动目录（\z 无页码开关、\o "1-N" 大纲级、标题字号加粗）；decoration=rich → w:background EAF1F8；pageSetup gutter 并入左边距；headerFooters 模板（页眉居中/企业名|投标技术标、页脚右对齐/居中/-N-、corner-dots ● 角点装饰）。
  - 批次4 暗标合规修：图片行不渲染时整行跳过（修复 markdown 原文被当正文的 bug）；表头/数据行序号/目录标题加粗切断（暗标 0 加粗）；表头底纹/数据行深底暗标切断；pBdr 单一节点合并（修 standard+hybrid-flow 双 pBdr 致 hybrid 左色条失效）。
- 踩坑（本轮关键）：
  ① layout.entries 用 LAYOUT_ALIAS_KEYS 单数 group 键，cmd 三处写复数（imageLayouts）→ KeyError；
  ② _builtin_preview_fixture 在临时目录建共享资源但 find_presets 找不到源预设 → presets_doc=None → 全部组回退 fallback（维度样张"假生效"）→ fixture 回溯 cwd/cwd.parent 复制 layout-presets.json；
  ③ 分章题注依赖 markdown 内 # 标题递增而 fixture 章标题来自章节树 → _chapter_no 恒 0 → 改 begin_chapter(idx+1) 按章节序驱动+每章重设 table_no/fig_no；
  ④ Windows 文件句柄：ZipFile 未关闭致 tempfile.cleanup PermissionError；
  ⑤ PowerShell 内嵌 python -c 引号/正则转义被 PS 解析破坏 → 校验脚本全部落 .py 文件。
- 验证：
  - 维度样张 31 份（dev/reports/dimension-samples/）：字体 2/标题 2/表格 2/题注 3/封面 5/装饰 4/图排 4/图比 2/图规则 2/目录 2/页眉 1/页面 1/组合 2，31/31 生成 OK；
  - XML 层实证：图宽 high=12.0/low=5.0/mid=9.0cm、c2 表1-1/图1-1、c1 表1、c6 附表/附图、t3 TOC \\z、t10 \\o "1-2"、photo-only 保留 3 照片滤 2 流程图、chart-only 反向、s30 6 处底纹、hf2 页眉 jc=center；
  - 暗标双态：hf9 图片0/底纹0/加粗0/无页脚；hf10 图片0/底纹0/加粗0/页脚 PAGE 域 ✓；
  - 10 范式 _verify_all10 10/10 ALL_OK；10 份明标样张重出+PDF；
  - 单测 test_m6_export.py 21 用例（新增 TechLayout12DimTest 7 用例：分章题注/表头底纹+暗标无底纹/封面渐变双色块/图宽映射/目录无页码/页眉居中+背景/暗标无图无加粗带页码）；全量回归 649 tests OK（skipped=1，上轮 642+7）。
- 耗时：约 4.5 小时。
- 待办：git 提交推送本轮（export.py/layout.py/test_m6_export.py/31 维度样张/10 范式样张/脚本 5 个/开发日志）；交付 10 范式样张 + 维度样张 + 报告；_render_chapter_title 章标题字号仍写死 16pt 未接 headingSystem level-1（小缺口，后续可补）。
"""
log.write_text(log.read_text(encoding="utf-8") + entry, encoding="utf-8")
print("LOG_APPENDED")
