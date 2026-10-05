# bidcraft_skill

**标书匠（bidcraft）** —— 项目级、平台无关的标书制作 skill。整个仓库即一个可被任意 agent（WorkBuddy、豆包、hermes、trae work 等）加载的分发单元。

## 仓库结构（项目级 skill）

```
bidcraft_skill/
├── SKILL.md          # skill 入口：角色、范围、模块总览、编排流程
├── references/       # 规范与契约：需求对齐、操作手册、模块契约、开发规范
├── scripts/          # 分包结构：bidcraft.py(薄壳) / _shared/(共享层) / m1_assets/(M1 子包)
├── tests/            # 测试金字塔：unit(L1) / integration(L2) / e2e(L3)
├── .github/          # CI/CD：ci.yml(推送/PR 三塔层测试) / release.yml(tag 发布 skill 包)
├── dev/notes/        # 开发日志 development-log.md
├── .gitignore
└── README.md
```

## 数据目录约定

- **素材库、模板库**数据属**企业级**：按企业隔离、主要支撑商务标。素材库（M1）用 `--root` 或环境变量 `BIDCRAFT_LIB_ROOT` 指向企业级目录，由脚本按需创建企业结构；模板库（M2）同为企业级。
- **知识库**数据属**共享级**：所有企业共用、与企业无关，主要支撑技术标。沉淀法规、评分标准、技术方案素材等；当前不预留占位，按后续需求创建。

## 模块进度

- M1 素材库：✅ 已交付（v0.2；v0.3 起数据目录企业级）
- M2 模板库：✅ 已交付（企业级，同素材库；台账+CLI：tpl-init/import/list/query/overview/sync/registry；首批 10 模板+登记清单入库）
- M3 知识库：⏳ 待实现（共享级，所有企业共用、与企业无关）
- M4 招标解析：✅ 已交付（v0.8.1：解析由 agent 完成，产出投标要点/素材清单双文本+JSON，脚本 tender-* 做编排与素材对照；项目级数据）
- M5 商务标：✅ 项目模板生成器 v1.0（proj-gen）+ 冻结（proj-freeze）+ 填充引擎 + 图框预览（ph-preview）；按「招标解析内容契约 + 素材清单 + 企业模板（格式排版契约）」动态生成项目模板，内容校验差异由用户决定；商务标主体 = 冻结项目模板
- M6 技术标：⏳ 待实现（路线图见 `references/module-contracts.md`）
- M7 标书检查：✅ 检查器 v1.0（m7-check：格式结构/占位符清零/敏感残留/Word 可打开冒烟/冻结版一致 5 项，可增行检查项表）
- M8 模拟评标：⏳ 待实现（路线图见 `references/module-contracts.md`）

> 术语约定（2026-10-05）：招标文件解析产物 = **内容契约**；企业模板库对应模板 = **格式与排版契约**（项目模板严格遵循）；代码/数据中历史命名"格式契约"仍保留，语义=内容契约。

## 使用

入口见 `SKILL.md`。首次使用先读 `SKILL.md`，开发新模块先读 `references/模块开发规范.md`。

## 素材库不入仓库（数据隔离）

- 素材库数据存放在**软件根**（如 `E:\监理标书制作\<企业>\企业级\素材库`），**在仓库之外**，天然不进 git；`.gitignore` 同时忽略兜底目录 `素材库/`，双保险。
- **任何素材一旦归档即受保护**：更改必须走标准流程（propose/apply/回收站等），除非用户明确指令。
- 测试全部使用 `tempfile` 临时素材根，**绝不触碰真实素材库**。

## 开发与测试（金字塔 + CI/CD）

```powershell
# 首次运行需安装运行依赖（python-docx/Pillow；CI 会自动安装）
pip install python-docx Pillow
# 本机跑三塔层测试（测试框架仅 Python 标准库 unittest）
python -m unittest discover -s tests/unit -t .        # L1 单元：命名引擎（最多、最快）
python -m unittest discover -s tests/integration -t . # L2 集成：存储层 core
python -m unittest discover -s tests/e2e -t .         # L3 端到端：CLI 全流程（最少、最慢）
```

- **测试金字塔**：层越低用例越多越快；新增逻辑按「先补对应层测试再实现」推进。
- **CI**（`.github/workflows/ci.yml`）：push/PR 触发，Python 3.10–3.12 三塔层 + py_compile 全绿才算通过。
- **CD**（`.github/workflows/release.yml`）：打 `v*` 标签自动打包发布 skill 可分发包（排除素材库/缓存）。

## 生产环境部署与升级（2026-10-05 现行流程）

- **开发与生产隔离**：开发/测试只在本仓库；生产环境 `E:\标书匠生产` 是**独立 git 仓库**（`git@github.com:chenjiancy/bidcraft_skill.git` main 分支，sparse-checkout 只检出 `scripts references SKILL.md README.md .gitignore`），工作区**无 tests/dev/.github**，本地永不开发。
- **升级链路（全自动，push 即部署）**：
  1. **main 受保护**：必须 PR 合并（0 审批可自合）、3 个必需 check（`test-pyramid` / `compile-check (ubuntu-latest)` / `compile-check (windows-latest)`，strict）、禁止强推/删除、必需会话解决、管理员同受保护（enforce_admins）。
  2. 功能分支 push → 开 PR → 检查全绿 → 合并。
  3. 合并自动触发：CI → `deploy.yml`（self-hosted runner，Windows 服务）→ 生产 fast-forward + 冒烟 + 写 `版本记录.txt`。
  4. 自动打版本 tag `v0.1.<run_number>`（`tag-release.yml`，push main 触发，run_number 仓库级单调递增）。
  5. **兜底**：Windows 计划任务「Bidcraft生产定时升级」每 6 小时自动跑 `升级生产.ps1`（GitHub 偶发断连时自动补拉；输出记 `E:\标书匠生产\升级日志.txt`；错过后补跑）。
- **手动升级（兜底命令）**：`cd E:\标书匠生产; .\升级生产.ps1`——防污染检查（已跟踪文件有改动→中止）→ fetch/pull → 冒烟 → 记版本。生产数据始终在 `E:\监理标书制作`（--root 指向），不在仓库内。
- **敏感信息治理（仓库 public 后）**：
  - 5 个业务文档（`dev/notes/development-log.md`、4 个 references 需求对齐/操作手册）**本地保留、.gitignore 不进公网**（历史已用 git-filter-repo 重写清除）。
  - 代码/测试中真实企业/人员/项目名一律**示例名**（示例建设工程监理有限公司、张三/李四/王五等）。
  - 真实数据路径**环境变量注入**：`BIDCRAFT_TEST_ENT` / `BIDCRAFT_TEST_PROJ`（默认示例名；本地真实回归用 `tests\run_local_regression.bat`，含真实路径、gitignore）。
