# -*- coding: utf-8 -*-
"""重跑：下载 + create + 逐项 get，全部输出写日志文件避免 stdout 截断。"""
import json
import os
import subprocess
import urllib.request

ACTIVE_WS = "cws_59061000646486274"
DESIGN_CLI = r"C:\Users\hxjlcj\AppData\Local\Doubao\User Data\Default\sandbox_envs_dir\envs\bfd038c4-6221-4428-9497-3a5db74dd95b\override_dlcs\design-cli.EXE"
ASSET_DIR = r"E:\bidcraft_skill\共享资源\技术标风格\样张素材"
LOG = r"E:\bidcraft_skill\.creative-design\m6-preview-images\canvas_log.txt"

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

log_lines = []
def log(msg):
    log_lines.append(str(msg))
    print(str(msg))


def run_cli(args, xml_text=None):
    p = subprocess.run(
        [DESIGN_CLI] + args,
        input=xml_text.encode("utf-8") if xml_text is not None else None,
        capture_output=True,
    )
    return p


def extract_item_id(xml_data):
    for token in ('item_id="',):
        idx = xml_data.find(token)
        if idx >= 0:
            rest = xml_data[idx + len(token):]
            return rest.split('"')[0]
    return None


def main():
    os.makedirs(ASSET_DIR, exist_ok=True)
    for im in IMAGES:
        dst = os.path.join(ASSET_DIR, im["file"])
        if not os.path.exists(dst):
            req = urllib.request.Request(im["url"], headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req) as r, open(dst, "wb") as f:
                f.write(r.read())
        log("DOWNLOADED %s %d bytes" % (im["file"], os.path.getsize(dst)))

    ids = {}
    for im in IMAGES:
        xml = (
            '<item type="IMAGE" path="%s/%s" title="%s" brief="%s">'
            '<size width="2730" height="1536"/>'
            '<asset url="%s"/>'
            "</item>"
        ) % ("/generated-assets/m6-preview-images", im["title"], im["title"], im["brief"], im["url"])
        p = run_cli(
            ["design-workspace", "+create", "--canvas-workspace-id", ACTIVE_WS, "--input", "-"],
            xml,
        )
        log("CREATE %s rc=%d" % (im["title"], p.returncode))
        if p.returncode != 0:
            log("  stderr: " + p.stderr.decode("utf-8", "replace"))
            continue
        xml_data = p.stdout.decode("utf-8")
        log("  xml: " + xml_data[:300])
        ids[im["title"]] = extract_item_id(xml_data)

    log("IDS: %s" % json.dumps(ids, ensure_ascii=False))

    for title, iid in ids.items():
        if not iid:
            log("GET %s: no id" % title)
            continue
        p = run_cli(
            ["design-workspace", "+get", "--canvas-workspace-id", ACTIVE_WS, "--item-ids", iid],
        )
        log("GET %s rc=%d" % (title, p.returncode))
        if p.returncode == 0:
            log("  xml: " + p.stdout.decode("utf-8")[:400])
        else:
            log("  stderr: " + p.stderr.decode("utf-8", "replace"))

    with open(LOG, "w", encoding="utf-8") as f:
        f.write("\n".join(log_lines))


if __name__ == "__main__":
    main()
