# -*- coding: utf-8 -*-
"""标书匠软件使用端 UI 全站一致性检查（可复跑）。

输入: dev/prototypes/_template_ui.html（唯一编辑入口）
检查项:
  C1 每个 hash 路由 href=#/X → view-X / ctx-X / VIEW_CTX 键 / 路由白名单 均存在
  C2 VIEW_CTX 键 ↔ 路由白名单 ↔ view 集合 ↔ ctx 集合 四方一致
  C3 每个 onclick=go('X') 的 X ∈ VIEW_CTX（无死路由）
  C4 每个 view 至少存在一个入口（顶栏 href 或 go 调用），无孤儿视图
  C5 每个 ctx 至少被 VIEW_CTX 引用，无孤儿上下文
  C6 暗标开关（body.dark + toggleDark + 徽章联动）存在
  C7 向导 stepper 步骤（提取标题文本，供人工比对真实管道）
  C8 产物路径引用清单（项目级/<项目>/… 目录，供人工核对真实模块产物目录）
  C9 未实现功能占位统计（规划中/后续迭代实现 计数，确认均有占位反馈）

用法: python _check_ui_consistency.py [模板路径]
退出码: 0=全部通过(或仅人工核对项), 1=存在结构性问题
"""
import re
import sys
from collections import Counter

def main():
    path = sys.argv[1] if len(sys.argv) > 1 else r"E:\bidcraft_skill\dev\prototypes\_template_ui.html"
    with open(path, "r", encoding="utf-8") as f:
        html = f.read()

    # ---- 提取 ----
    href_views = sorted(set(re.findall(r'href="#/([A-Za-z0-9_-]+)"', html)))
    go_calls = sorted(set(re.findall(r"go\('([A-Za-z0-9_-]+)'\)", html)))
    views = sorted(set(re.findall(r'id="view-([A-Za-z0-9_-]+)"', html)))
    ctxs = sorted(set(re.findall(r'id="ctx-([A-Za-z0-9_-]+)"', html)))
    m2 = re.search(r"if\(\[([^\]]*)\]\.indexOf\(h\)>-1\)", html)
    whitelist = sorted(set(re.findall(r"'([A-Za-z0-9_-]+)'", m2.group(1)))) if m2 else []
    # 键为裸标识符: {home:'ctx-home', ...}
    vctx = {}
    m = re.search(r"var VIEW_CTX=\{(.*?)\};", html, re.S)
    if m:
        for k, v in re.findall(r"([A-Za-z0-9_-]+):'(ctx-[A-Za-z0-9_-]+)'", m.group(1)):
            vctx[k] = v

    # ---- C1/C2 ----
    issues = []
    for r in href_views:
        if r not in views: issues.append(f"C1 href=#/{r} 无对应 view-{r}")
        if r not in ctxs: issues.append(f"C1 href=#/{r} 无对应 ctx-{r}")
        if r not in vctx: issues.append(f"C1 href=#/{r} 未注册 VIEW_CTX")
        if r not in whitelist: issues.append(f"C1 href=#/{r} 不在路由白名单")
    vs, cs, kset, wset = set(views), set(ctxs), set(vctx.keys()), set(whitelist)
    if kset != wset:
        issues.append(f"C2 VIEW_CTX键 与 白名单 不一致: 仅KEY={sorted(kset-wset)} 仅LIST={sorted(wset-kset)}")
    if kset != vs:
        issues.append(f"C2 VIEW_CTX键 与 view 集合 不一致: 仅KEY={sorted(kset-vs)} 仅VIEW={sorted(vs-kset)}")
    if kset != cs:
        issues.append(f"C2 VIEW_CTX键 与 ctx 集合 不一致: 仅KEY={sorted(kset-cs)} 仅CTX={sorted(cs-kset)}")

    # ---- C3 ----
    for g in go_calls:
        if g not in vctx:
            issues.append(f"C3 go('{g}') 未注册 VIEW_CTX")

    # ---- C4/C5 ----
    entry_targets = set(href_views) | set(go_calls)
    orphan_views = sorted(vs - entry_targets)
    ctx_ids = set(vctx.values())
    orphan_ctxs = sorted(cs - set(c[4:] for c in ctx_ids))  # 去 ctx- 前缀
    if orphan_views: issues.append(f"C4 孤儿视图(无任何入口): {orphan_views}")
    if orphan_ctxs: issues.append(f"C5 孤儿上下文(无 VIEW_CTX 引用): {orphan_ctxs}")

    # ---- C6 暗标开关 ----
    dark_checks = {
        "darkMode 状态变量": bool(re.search(r"var darkMode", html)),
        "classList.toggle 调用": "classList.toggle" in html,
        "'dark' 类名": "'dark'" in html or '"dark"' in html,
        "暗标徽章": bool(re.search(r"dark-tag|暗标", html)),
    }
    if not all(dark_checks.values()):
        issues.append("C6 暗标开关组件缺失: " + str([k for k, v in dark_checks.items() if not v]))

    # ---- C7 向导 stepper（JS 渲染，WZ_STEPS 数组为权威） ----
    mw = re.search(r"var WZ_STEPS=\[(.*?)\];", html)
    stepper = re.findall(r"'([^']+)'", mw.group(1)) if mw else []
    # ---- C8 产物路径引用 ----
    paths = sorted(set(re.findall(r'项目级/[^<" ]+(?:商务标|招标解析|项目模板|模拟评标|标书检查|模板库|素材库)[^<" ]*', html)))
    # ---- C9 未实现占位 ----
    placeholders = Counter(re.findall(r"(规划中|后续迭代实现|待开发|待处理)", html))

    # ---- 输出 ----
    print("== 标书匠 UI 全站一致性检查 ==")
    print(f"模板: {path}")
    print(f"视图 {len(vs)}: {sorted(vs)}")
    print(f"上下文 {len(cs)}: {sorted(cs)}")
    print(f"VIEW_CTX {len(kset)} / 白名单 {len(wset)} / href路由 {len(href_views)} / go调用 {len(go_calls)}")
    print(f"顶栏一级导航: {href_views}")
    print(f"暗标开关: {dark_checks}")
    if stepper:
        print(f"向导步骤({len(stepper)}): {' → '.join(stepper)}")
    if paths:
        print("产物路径引用:")
        for p in paths:
            print("  -", p)
    print("未实现占位计数:", dict(placeholders))

    if issues:
        print("\n[FAIL] 结构性问题:")
        for it in issues:
            print("  -", it)
        return 1
    print("\n[PASS] 结构一致性通过（C1-C6）；C7 步骤 / C8 产物路径 / C9 占位计数为人工核对项。")
    return 0

if __name__ == "__main__":
    sys.exit(main())
