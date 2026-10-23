# -*- coding: utf-8 -*-
"""按真实 ID 逐个 +get 回读画布资产，核对 URL 与 path。"""
import json
import re
import subprocess

CLI = r"C:\Users\hxjlcj\AppData\Local\Doubao\User Data\Default\sandbox_envs_dir\envs\bfd038c4-6221-4428-9497-3a5db74dd95b\override_dlcs\design-cli.EXE"
WS = "cws_59061000646486274"
IDS = {
    "施工现场全景": "qI0DnGQa-4O4XGRACHK-0201",
    "水准测量放线": "kQLFza3J-4O4tpf29Kc-0201",
    "监理例会图纸会审": "RbN04QK2-4NxDExhbCk-0201",
}

for title, iid in IDS.items():
    p = subprocess.run(
        [CLI, "design-workspace", "+get", "--canvas-workspace-id", WS, "--item-ids", iid],
        capture_output=True,
    )
    print(title, "rc=", p.returncode)
    if p.returncode == 0:
        xml = json.loads(p.stdout.decode("utf-8"))["xml_data"]
        url = re.search(r'url="([^"]+)"', xml).group(1)
        path = re.search(r'path="([^"]+)"', xml).group(1)
        typ = re.search(r'type="([^"]+)"', xml).group(1)
        print("   type=", typ, " path=", path)
        print("   url=", url)
    else:
        print("   stderr=", p.stderr.decode("utf-8", "replace")[:300])
