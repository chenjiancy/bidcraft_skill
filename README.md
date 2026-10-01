# bidcraft_skill

**标书匠（bidcraft）** —— 项目级、平台无关的标书制作 skill。整个仓库即一个可被任意 agent（WorkBuddy、豆包、hermes、trae work 等）加载的分发单元。

## 仓库结构（项目级 skill）

```
bidcraft_skill/
├── SKILL.md          # skill 入口：角色、范围、模块总览、编排流程
├── references/       # 规范与契约：需求对齐、操作手册、模块契约、开发规范
├── scripts/          # 各模块可复用脚本（M1 已交付：bidcraft.py / bidcraft_core.py / bidcraft_naming.py）
├── dev/notes/        # 开发日志 development-log.md
├── .gitignore
└── README.md
```

## 数据目录约定

- **素材库数据**属**企业级**：不在本仓库内，使用 M1 时以 `--root` 或环境变量 `BIDCRAFT_LIB_ROOT` 指向企业级目录，由脚本按需创建企业结构。
- **模板库、知识库**等模块：**按后续需求再创建**，当前不预留占位目录。

## 模块进度

- M1 素材库：✅ 已交付（v0.2；v0.3 起数据目录企业级）
- M2 模板库 / M3 知识库：⏳ 按后续需求创建
- M4 招标解析 / M5 商务标 / M6 技术标 / M7 标书检查 / M8 模拟评标：⏳ 待实现（路线图见 `references/module-contracts.md`）

## 使用

入口见 `SKILL.md`。首次使用先读 `SKILL.md`，开发新模块先读 `references/模块开发规范.md`。
