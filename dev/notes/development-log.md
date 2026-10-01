# bidcraft 开发日志（development-log）

> 记录决策、踩坑、验证数据、耗时，供后期写论文总结经验。
> 格式：`## YYYY-MM-DD` → 条目（背景 / 决策 / 踩坑 / 验证 / 耗时）。

---

## 2026-10-01

### 项目级化改造（v0.2 → v0.3）
- **背景**：bidcraft skill 此前嵌于 `.workbuddy/skills/bidcraft/`（workbuddy 私有结构），仓库根仅有素材库/模板库/知识库三个占位目录。
- **决策**（用户确认）：① skill 改为**项目级**——仓库根即 skill，`SKILL.md`、`references/`、`scripts/` 直接置于根目录，平台无关、可整体打包分发给 WorkBuddy/豆包/hermes/trae work 等；② 删除素材库/模板库/知识库三个数据占位目录；③ 整目录删除 `.workbuddy/`（含 skill 旧位置与 memory，未提交 git，删除不可恢复，已确认）。
- **定位调整**：素材库数据目录属**企业级**，不在仓库内，由 `--root`/`BIDCRAFT_LIB_ROOT` 指向企业级目录、脚本按需创建；模板库/知识库等模块**按后续需求创建**，不再预留占位。
- **踩坑**：素材库/.gitkeep 被 git 跟踪，直接 `Remove-Item` 会留下索引脏状态，需用 `git rm` 同步索引；模板库/知识库/.workbuddy 为 untracked，可 `Remove-Item`。
- **验证**：复制 references/scripts 至根目录后逐一核对（4 文档 + 3 脚本齐全）；脚本默认根逻辑（`--root > BIDCRAFT_LIB_ROOT > ./素材库`）确认依赖运行时路径、不依赖仓库占位，删除占位不影响功能；`.gitignore` 改为忽略兜底 `素材库/`。
- **耗时**：约 15 分钟。
