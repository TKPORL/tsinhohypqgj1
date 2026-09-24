# -*- coding: utf-8 -*-
"""把 output/ 下的旧测试产物清单落盘存档（只读，不删）。

用于在删除前留证据：谁在什么时候删了什么、多大、删前有没有备份。
"""
import os
import sys
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "output")
LOG_DIR = os.path.join(ROOT, "logs")

# 建议删除的旧测试产物（按前缀匹配，包含同名 zip 与目录两份）
TARGETS = [
    "PC下载-拆分测试-20260923-091917",
    "PC+安卓下载-拆分测试-20260923-091917",
    "安卓下载-拆分测试-20260923-091917",
    "PC+安卓下载-ACG俱乐部-ACG图书馆-ACG游戏姬-萌幻ACG-20260920-095333",
    "PC下载-鲲Galgame-20260923-084601",
    "PC+安卓下载-鲲Galgame-20260923-084601",
    "PC下载-鲲Galgame-20260923-085200",
    "PC+安卓下载-鲲Galgame-20260923-085200",
    "PC下载-测试预览-20260923-141405",
]


def size_of(path):
    if os.path.isfile(path):
        return os.path.getsize(path)
    total = 0
    for dirpath, _, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(dirpath, f))
            except OSError:
                pass
    return total


def main():
    lines = [f"# output/ 清理清单  （生成于 {datetime.now():%Y-%m-%d %H:%M:%S}）", ""]
    lines.append("## 建议删除（旧测试产物）")
    lines.append("")
    grand = 0
    found = []
    for name in TARGETS:
        for cand in (os.path.join(OUT, name), os.path.join(OUT, name + ".zip")):
            if os.path.exists(cand):
                s = size_of(cand)
                grand += s
                found.append(cand)
                lines.append(f"- {os.path.relpath(cand, ROOT)}  |  {s/2**20:.1f} MB")
    lines.append("")
    lines.append(f"小计：{len(found)} 项，{grand/2**30:.2f} GB")
    lines.append("")
    lines.append("## 保留")
    lines.append("")
    for keep in ("PC下载-测试预览-20260923-141555", "PC.html", "仅安卓.html"):
        for cand in (os.path.join(OUT, keep), os.path.join(OUT, keep + ".zip")):
            if os.path.exists(cand):
                lines.append(f"- {os.path.relpath(cand, ROOT)}  |  {size_of(cand)/2**20:.1f} MB")
    lines.append("")
    lines.append("## 说明")
    lines.append("")
    lines.append("- output/ 是可重建的导出产物；原始数据在 data/crawler.db 与 images/，不受影响")
    lines.append("- 删除走回收站，可恢复")

    os.makedirs(LOG_DIR, exist_ok=True)
    dest = os.path.join(LOG_DIR, f"output_cleanup_{datetime.now():%Y%m%d-%H%M%S}.md")
    with open(dest, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"清单已写入：{dest}")
    print(f"共 {len(found)} 项，合计 {grand/2**30:.2f} GB")
    for p in found:
        print("  DEL ->", os.path.relpath(p, ROOT))


if __name__ == "__main__":
    sys.exit(main())
