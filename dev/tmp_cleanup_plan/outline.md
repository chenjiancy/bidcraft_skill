# 生产环境清理方案 · 内容大纲

## 文档定位
- 体裁：专业领域文书（工程技术方案类）
- 交付物：Word（.docx）
- 读者：用户本人（bidcraft 生产环境维护者）
- 目标：给出 E:\标书匠生产 混入开发/测试环境的完整清理方案，供用户审阅后执行

## 一、问题诊断摘要
- 生产目录设计：sparse-checkout 只检出发布文件（scripts/references/SKILL.md/README/.gitignore/requirements.txt/VERSION），数据在 E:\监理标书制作
- 实际现状（2026-10-23 核查）：
  - git 跟踪 192 个 dev/tests/.github 文件（dev/ 179 文件、tests/ 53 文件 + .github/）
  - 根目录 9 个垃圾文件被跟踪：gen2.txt、gen_final.txt、out.txt、out_e2e.txt、push.txt、sme_prod_check.txt、verify_patch.txt、secedit.jfm、secedit.sdb
  - .deploy/ SSH 私钥被跟踪（bidcraft_deploy、bidcraft_deploy.pub、known_hosts）
  - 运维文件也被跟踪：升级日志.txt、定时升级.cmd、使用bidcraft_skill.bat、生产环境说明.txt
  - 本地 main 领先 origin/main 7 个 prod-sync 提交
- 根因（三条）：
  1. 升级脚本（升级生产.ps1）用 GitHub API zipball 全量快照下载整个仓库（含 dev/tests/.github），robocopy /E 全量同步工作区（只排除 .git/.deploy/scripts/tools/tmp_out + 少数文件），随后 git sparse-checkout disable + git add -A 全量入库 → 开发/测试文件进入生产并入库
  2. 根目录垃圾文件是生产目录早期本地遗留（2026-10-19 之前），在"全量收敛"提交（dcd741d / 1827390）时被 git add -A 一并入库；开发仓库中这些文件不存在
  3. .deploy 私钥在 dcd741d 时被 git add -A 跟踪
- 提交定位：
  - 1827390（10-19 19:15）：引入 gen2.txt/gen_final.txt/out.txt/out_e2e.txt/push.txt 等根目录垃圾文件
  - dcd741d（10-19 19:19 全量收敛）：引入 .deploy、tests/ 等
  - 80864d1（10-19 19:18 补充收敛）
  - 1019863（10-19 21:47）：最近一次 prod-sync，dev/ 等也在其中
  - dev/ 早期由 GitHub 上游提交就有（3ba3e7a 等），因开发仓库本就跟踪并推送 main

## 二、清理目标与边界
- 目标状态：生产目录 git 跟踪树仅含发布文件；工作区无 dev/tests/.github/根目录垃圾；.deploy 私钥仅存在于磁盘且不被跟踪；运维文件不跟踪
- 边界：
  - 不修改 GitHub main 上的历史（开发仓库仍保留 dev/tests，属于开发侧正常）
  - 不清除生产数据（E:\监理标书制作）
  - 不删除 .deploy 私钥（升级仍需使用）
  - 本次只出方案 + 用户确认后执行

## 三、分阶段清理方案
### 阶段 0：前置检查与备份
- 检查生产 git 状态、确认当前版本、备份 .git（或整目录到回收站/备份区）
- 确认定时任务「Bidcraft生产定时升级」当前状态（避免清理过程中被自动升级打断）

### 阶段 1：修复升级脚本（根治）
- 修改升级生产.ps1：
  - zipball 下载后，robocopy 改为白名单同步：只同步 scripts/references/SKILL.md/README/.gitignore/requirements.txt/VERSION，不 /E 全量
  - 或 robocopy 增加 /XD dev tests .github 排除 + /XF 根目录垃圾文件
  - git sparse-checkout disable 后不再 git add -A 全量，改 git add 白名单
  - 保留防污染检查、冒烟、版本记录逻辑
- 生产 .gitignore 增加忽略项（.deploy/、dev/、tests/、.github/、根目录垃圾文件、运维文件）
- 开发仓库 .gitignore 同步补充（避免再次被 zipball 带进来）—— 但注意开发仓库需要 dev/tests 跟踪，所以开发仓库 .gitignore 只加根目录垃圾文件和 .deploy 忽略，不忽略 dev/tests

### 阶段 2：清理生产 git 跟踪
- git rm -r --cached dev tests .github
- git rm --cached 9 个根目录垃圾文件
- git rm -r --cached .deploy（私钥移出跟踪，保留磁盘）
- git rm --cached 运维文件（升级日志.txt、定时升级.cmd、使用bidcraft_skill.bat、生产环境说明.txt）——注意这些在 git 里被跟踪了
- 提交 cleanup commit（prod-cleanup，本地，不推送）

### 阶段 3：清理工作区磁盘文件
- 删除 dev/、tests/、.github/、9 个垃圾文件（移入回收站或备份目录，符合用户"删除项目先进回收站"偏好）
- 保留 .deploy/（私钥）

### 阶段 4：验证与回归
- git ls-files 确认无 dev/tests/.github/垃圾/私钥
- git status 确认干净（仅 untracked 运维文件）
- 冒烟：python scripts\bidcraft.py --help + list-enterprises
- 跑一次手动升级确认新脚本不引入污染

## 四、风险与回滚预案
- 风险1：清理中断（断电/脚本失败）→ 备份先行，git 仓库可 reset
- 风险2：定时任务在清理中触发 → 阶段0先禁用或改触发条件
- 风险3：私钥被删 → 不删 .deploy 磁盘，只移出跟踪
- 风险4：开发仓库 .gitignore 误加 dev/tests 忽略 → 明确区分两份 .gitignore 的职责
- 回滚：git reset --hard 到 cleanup 前 commit；备份目录恢复

## 五、验收清单
- [ ] git ls-files 顶层仅含发布文件
- [ ] git status 无已跟踪改动（可容忍 untracked 运维文件）
- [ ] 冒烟通过
- [ ] 手动升级一次后工作区仍干净
- [ ] 私钥仍在磁盘且可登录

## 六、待用户确认事项
- 清理范围是否含根目录 9 个垃圾文件（确认删除 vs 移备份）
- 是否同时调整开发仓库 .gitignore
- 清理执行时间窗口（避开定时任务）
- 执行者：本 Agent 执行 or 用户手动执行
