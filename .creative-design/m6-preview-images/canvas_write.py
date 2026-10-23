# -*- coding: utf-8 -*-
"""下载 3 张样张配图到共享素材目录，并写入 Canvas Workspace（+create / +get 回读）。"""
import json
import os
import subprocess
import sys
import urllib.request

ACTIVE_WS = "cws_59061000646486274"
DESIGN_CLI = r"C:\Users\hxjlcj\AppData\Local\Doubao\User Data\Default\sandbox_envs_dir\envs\bfd038c4-6221-4428-9497-3a5db74dd95b\override_dlcs\design-cli.EXE"
ASSET_DIR = r"E:\bidcraft_skill\共享资源\技术标风格\样张素材"
CANVAS_PATH_ROOT = "/generated-assets/m6-preview-images"

IMAGES = [
    {
        "url": "https://aka.doubaocdn.com/s/ZwTmDjW4fP",
        "file": "样张_施工现场全景.jpg",
        "title": "施工现场全景",
        "brief": "技术标样张配图1：在建公共建筑施工现场全景，写实摄影，16:9",
    },
    {
        "url": "https://aka.doubaocdn.com/s/IxaW2xWuUy",
        "file": "样张_水准测量放线.jpg",
        "title": "水准测量放线",
        "brief": "技术标样张配图2：监理工程师水准测量放线，写实摄影，16:9",
    },
    {
        "url": "https://aka.doubaocdn.com/s/I1SxUUVFhF",
        "file": "样张_图纸会审.jpg",
        "title": "监理例会图纸会审",
        "brief": "技术标样张配图3：监理例会图纸会审场景，写实摄影，16:9",
    },
]


def run_cli(args, xml_text=None):
    """调用 design-cli；stdin 用 utf-8 字节传入 XML。"""
    p = subprocess.run(
        [DESIGN_CLI] + args,
        input=xml_text.encode("utf-8") if xml_text is not None else None,
        capture_output=True,
    )
    return p


def main():
    os.makedirs(ASSET_DIR, exist_ok=True)
    # 1) 下载到本地素材目录（fixture 引用用）
    for im in IMAGES:
        dst = os.path.join(ASSET_DIR, im["file"])
        if not os.path.exists(dst):
            req = urllib.request.Request(im["url"], headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req) as r, open(dst, "wb") as f:
                f.write(r.read())
        print("downloaded:", dst, os.path.getsize(dst))

    # 2) +create 三个 IMAGE item
    created = []
    for im in IMAGES:
        xml = (
            '<item type="IMAGE" path="%s/%s" title="%s" brief="%s">'
            '<size width="2730" height="1536"/>'
            '<asset url="%s"/>'
            "</item>"
        ) % (
            CANVAS_PATH_ROOT,
            im["title"],
            im["title"],
            im["brief"],
            im["url"],
        )
        p = run_cli(
            ["design-workspace", "+create", "--canvas-workspace-id", ACTIVE_WS, "--input", "-"],
            xml,
        )
        if p.returncode != 0:
            print("CREATE FAILED", im["title"], p.returncode, p.stderr.decode("utf-8", "replace"))
            sys.exit(1)
        out = json.loads(p.stdout.decode("utf-8"))
        print("created:", im["title"], "->", out.get("xml_data", "")[:200])
        # 提取 item_id
        xml_data = out.get("xml_data", "")
        item_id = None
        for token in ("item_id=", 'item_id="'):
            idx = xml_data.find(token)
            if idx >= 0:
                rest = xml_data[idx + len(token):]
                item_id = rest.split('"')[0]
                break
        created.append((im, item_id))

    # 3) +get 回读核对
    ids = [cid for _, cid in created]
    p = run_cli(
        ["design-workspace", "+get", "--canvas-workspace-id", ACTIVE_WS, "--item-ids", ",".join(ids)],
    )
    print("GET rc:", p.returncode)
    print(p.stdout.decode("utf-8", "replace")[:1500])


if __name__ == "__main__":
    main()
