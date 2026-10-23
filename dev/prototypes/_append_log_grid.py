# -*- coding: utf-8 -*-
"""追加 grid 两图并排落地条目到 development-log.md（UTF-8 安全）。"""
from pathlib import Path

log = Path(r"E:\bidcraft_skill\dev\notes\development-log.md")
entry = """

## 2026-10-23 grid 两图并排渲染落地（任务19）
- 背景：用户目视 12 维样张后指出"没看到一页两张图并排排列的样张"——grid（图组并排）方案在渲染层仅把单图缩至 7cm（_image_single），并未实现并排。
- 实现：export.py render_md 图片分支新增 grid 合并逻辑（下一行仍是图片引用 → 两图一组 _image_grid_pair，1×2 无边框表、各 6.8cm、图下各自题注、表下组注；否则降级单图 7cm）；_image_grid_pair 调用前自增 fig_no 两次（修首次版本两图同为图1-1）；layout.py _builtin_preview_fixture 增 grid_pair 参数（第一章插 survey+meeting 连续两图，避免与顶部 site 单图重复，组注去掉 x-x 占位）。
- 测试：test_m6_export.py 新增 test_dim12_grid_pair（连续两照片 → 并排表 1 个含 2 drawing + 图题图1-1/1-2 连续），22 用例全绿；全量回归 650 OK（skipped=1）。
- 验证：s31 维度样张 docx+PDF 目视——第 3 页底部 图1-2 现场水准测量放线（左）/图1-3 监理例会图纸会审（右）同高并排、题注连续、组注正常；XML 实证 PICS=5、CAPS=图1-1/1-2/1-3。
- 待办：git 提交推送本轮；交付 s31 样张。
"""
log.write_text(log.read_text(encoding="utf-8") + entry, encoding="utf-8")
print("LOG_APPENDED")
