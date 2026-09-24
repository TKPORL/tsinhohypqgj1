# -*- coding: utf-8 -*-
"""把 output/ 下指定的旧测试产物移入 Windows 回收站（不永久删除）。

用法：
    C:/Python314/python.exe tools/trash_output_cleanup.py            # 干跑，只打印
    C:/Python314/python.exe tools/trash_output_cleanup.py --go       # 真正移入回收站

安全约束：
- 目标在白名单 TARGETS 内才处理，不接受命令行任意路径
- 只走回收站（SHFileOperationW），可恢复
- 单批最多 10 项，逐项复核存在性
"""
import argparse
import ctypes
import os
import sys
from ctypes import wintypes

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "output")

# 白名单：与 tools/list_output_cleanup.py 的 TARGETS 保持一致
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

# --- Windows 回收站 ---------------------------------------------------------
FO_DELETE = 3
FOF_ALLOWUNDO = 0x40          # 移入回收站
FOF_NOCONFIRMATION = 0x10     # 不弹确认框
FOF_SILENT = 0x4
FOF_NOERRORUI = 0x400


class SHFILEOPSTRUCTW(ctypes.Structure):
    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("wFunc", wintypes.UINT),
        ("pFrom", wintypes.LPCWSTR),
        ("pTo", wintypes.LPCWSTR),
        ("fFlags", ctypes.c_uint16),
        ("fAnyOperationsAborted", wintypes.BOOL),
        ("hNameMappings", ctypes.c_void_p),
        ("lpszProgressTitle", wintypes.LPCWSTR),
    ]


def send_to_recycle_bin(paths):
    """把一批绝对路径移入回收站。pFrom 必须双 \\0 结尾。

    注意：必须用 create_unicode_buffer 传多字符串，不能直接给 LPCWSTR 赋
    带内部 \\0 的 Python str —— ctypes 会在第一个 \\0 处截断，导致返回码 2
    （ERROR_FILE_NOT_FOUND，因为 pFrom 变成了空串）。
    """
    if not paths:
        return 0
    joined = "\0".join(paths) + "\0\0"
    buf = ctypes.create_unicode_buffer(joined)

    op = SHFILEOPSTRUCTW()
    op.hwnd = None
    op.wFunc = FO_DELETE
    op.pFrom = ctypes.cast(buf, wintypes.LPCWSTR)
    op.pTo = None
    op.fFlags = FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_SILENT | FOF_NOERRORUI
    op.fAnyOperationsAborted = False
    op.hNameMappings = None
    op.lpszProgressTitle = None
    res = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--go", action="store_true", help="真正执行（默认只干跑）")
    args = ap.parse_args()

    # 展开白名单 → 实际存在的路径（目录 + 同名 zip）
    found = []
    for name in TARGETS:
        for cand in (os.path.join(OUT, name), os.path.join(OUT, name + ".zip")):
            if os.path.exists(cand):
                found.append(os.path.abspath(cand))

    if not found:
        print("没有匹配到任何待删项")
        return 0

    print(f"{'执行' if args.go else '干跑'}：命中 {len(found)} 项")
    for p in found:
        print("  -", os.path.relpath(p, ROOT))

    if not args.go:
        print("\n加 --go 才会真正移入回收站")
        return 0

    # 分批，每批最多 10 项
    # 注意：SHFileOperationW 在成功时也可能返回 2（ctypes 传 pTo=None 的老问题），
    # 因此不拿返回码当失败依据，改为逐个复核文件是否真的消失。
    total = 0
    remaining = []
    for i in range(0, len(found), 10):
        batch = found[i:i + 10]
        rc = send_to_recycle_bin(batch)
        gone = [p for p in batch if not os.path.exists(p)]
        left = [p for p in batch if os.path.exists(p)]
        total += len(gone)
        remaining.extend(left)
        print(f"批次 {i // 10 + 1}：成功 {len(gone)} 项，未删 {len(left)} 项（返回码 {rc}）")
        for p in left:
            print("  未删 ->", os.path.relpath(p, ROOT))

    print(f"\n共 {total} 项已移入回收站")
    if remaining:
        print(f"仍有 {len(remaining)} 项未删，请检查是否被占用")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
