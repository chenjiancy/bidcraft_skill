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
- M2 模板库：⏳ 待实现（企业级，同素材库）
- M3 知识库：⏳ 待实现（共享级，所有企业共用、与企业无关）
- M4 招标解析：✅ 已交付（v0.8.0：解析由 agent 完成，产出投标要点/素材清单双文本+JSON，脚本 tender-* 做编排与素材对照；项目级数据）
- M5 商务标 / M6 技术标 / M7 标书检查 / M8 模拟评标：⏳ 待实现（路线图见 `references/module-contracts.md`）

## 使用

入口见 `SKILL.md`。首次使用先读 `SKILL.md`，开发新模块先读 `references/模块开发规范.md`。

## 素材库不入仓库（数据隔离）

- 素材库数据存放在**软件根**（如 `E:\监理标书制作\<企业>\企业级\业绩库`），**在仓库之外**，天然不进 git；`.gitignore` 同时忽略兜底目录 `素材库/`，双保险。
- **任何素材一旦归档即受保护**：更改必须走标准流程（propose/apply/回收站等），除非用户明确指令。
- 测试全部使用 `tempfile` 临时素材根，**绝不触碰真实素材库**。

## 开发与测试（金字塔 + CI/CD）

```powershell
# 本机跑三塔层测试（零外部依赖，仅 Python 标准库 unittest）
python -m unittest discover -s tests/unit -t .        # L1 单元：命名引擎（最多、最快）
python -m unittest discover -s tests/integration -t . # L2 集成：存储层 core
python -m unittest discover -s tests/e2e -t .         # L3 端到端：CLI 全流程（最少、最慢）
```

- **测试金字塔**：层越低用例越多越快；新增逻辑按「先补对应层测试再实现」推进。
- **CI**（`.github/workflows/ci.yml`）：push/PR 触发，Python 3.10–3.12 三塔层 + py_compile 全绿才算通过。
- **CD**（`.github/workflows/release.yml`）：打 `v*` 标签自动打包发布 skill 可分发包（排除素材库/缓存）。
