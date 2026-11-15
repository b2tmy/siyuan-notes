#!/usr/bin/env python3
"""从本机 SiYuan 重新导出笔记到本仓库。

前置：SiYuan 内核在 127.0.0.1:6806 运行，且已打开对应工作空间。
用法：python export.py
"""
import json
import os
import re
import shutil
import urllib.request

BASE = "http://127.0.0.1:6806"
OUT = os.path.dirname(os.path.abspath(__file__))

# 只导出有内容的笔记本；空笔记本（只有「未命名文档」）自动跳过
INCLUDE = [
    "20261009210000-cry7p1n",   # cryption
    "20260928140511-khr6csy",   # Resever_learning
    "20261008153000-ag7n2kx",   # Agent开发
    "20261115213631-g7hydk1",   # frida_hook
    "20261115221442-yq33vof",   # pwn
]


def api(path, data):
    req = urllib.request.Request(
        BASE + path, data=json.dumps(data).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=60).read().decode("utf-8"))


def safe(name: str) -> str:
    name = re.sub(r'[\\/:*?"<>|\r\n\t]', "-", name).strip().strip(".")
    name = re.sub(r"\s+", " ", name)
    return name[:80] or "untitled"


def body_len(md: str) -> int:
    if md.startswith("---"):
        parts = md.split("---", 2)
        if len(parts) >= 3:
            md = parts[2]
    return len(md.strip())


def main():
    nb_meta = {n["id"]: n["name"]
               for n in api("/api/notebook/lsNotebooks", {})["data"]["notebooks"]}

    index_lines = ["# 笔记总览", "",
                   "由 SiYuan 导出的 Markdown，按笔记本分目录。空笔记本与「未命名文档」已在导出时过滤掉。",
                   "", "重新导出：`python export.py`（需要 SiYuan 内核在 127.0.0.1:6806 运行）。", ""]
    stats = []

    for nb_id in INCLUDE:
        nb_name = nb_meta.get(nb_id, nb_id)
        files = api("/api/filetree/listDocsByPath",
                    {"notebook": nb_id, "path": "/"})["data"]["files"]

        docs = []
        for f in files:
            if f["name"].strip() in ("未命名文档", "Untitled", "untitled"):
                continue
            md = api("/api/export/exportMdContent", {"id": f["id"]})["data"]["content"]
            if body_len(md) < 40:
                continue
            docs.append((f["name"], md))

        if not docs:
            continue

        nb_dir = os.path.join(OUT, safe(nb_name))
        os.makedirs(nb_dir, exist_ok=True)
        used = {}
        links = []
        for name, md in docs:
            base = safe(name)
            used[base] = used.get(base, 0) + 1
            fn = base if used[base] == 1 else f"{base}-{used[base]}"
            with open(os.path.join(nb_dir, fn + ".md"), "w", encoding="utf-8") as fh:
                fh.write(md)
            links.append((fn, name))

        src_scripts = os.path.join(r"C:\Users\Lenovo\SiYuan\data", nb_id, "scripts")
        if os.path.isdir(src_scripts):
            dst_scripts = os.path.join(nb_dir, "scripts")
            shutil.copytree(src_scripts, dst_scripts, dirs_exist_ok=True)
            shutil.rmtree(os.path.join(dst_scripts, "__pycache__"), ignore_errors=True)

        index_lines += [f"## {nb_name}", ""]
        for fn, title in links:
            link = f"{safe(nb_name)}/{fn}.md".replace(" ", "%20")
            index_lines.append(f"- [{title}]({link})")
        index_lines.append("")
        stats.append((nb_name, len(links)))

    with open(os.path.join(OUT, "README.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(index_lines).rstrip() + "\n")

    for name, n in stats:
        print(f"{name}: {n} docs")


if __name__ == "__main__":
    main()
