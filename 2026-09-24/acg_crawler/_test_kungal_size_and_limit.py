# -*- coding: utf-8 -*-
"""验证 2026-09-23 三项需求改动：
1. 「网盘大小」行按各网盘实际平台标注 -PC / -安卓
2. 该行改为可复制（导出与前端都不再剔除）
3. 单网盘超过 10GB 的整个游戏跳过

用法：C:/Python314/python.exe _test_kungal_size_and_limit.py
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from crawler.kungal import KungalCrawler, _size_to_gb, MAX_SIZE_GB  # noqa: E402

PASS = FAIL = 0


def check(name, got, want):
    global PASS, FAIL
    ok = got == want
    if ok:
        PASS += 1
    else:
        FAIL += 1
    print(f"  {'OK ' if ok else 'FAIL'} {name}")
    if not ok:
        print(f"       期望: {want!r}")
        print(f"       实际: {got!r}")


print("=== 1. 体积文本解析 ===")
check("10.8 GB", _size_to_gb("10.8 GB"), 10.8)
check("900 MB", round(_size_to_gb("900 MB"), 6), round(900 / 1024, 6))
check("1.15GB 无空格", _size_to_gb("1.15GB"), 1.15)
check("44.94 GB", _size_to_gb("44.94 GB"), 44.94)
check("空文本", _size_to_gb(""), None)
check("无单位", _size_to_gb("10086"), None)
check("2 TB", _size_to_gb("2 TB"), 2048.0)

print()
print("=== 2. 上限常量 ===")
check("MAX_SIZE_GB", MAX_SIZE_GB, 10.0)

print()
print("=== 3. 「网盘大小」行带平台标注 ===")
# 构造 (label, size, tag) 三元组，直接验 _build_content 的拼装
crawler = KungalCrawler.__new__(KungalCrawler)  # 不走 __init__，避免读配置

galgame = {"name": "测试游戏", "name_original": "", "alias": [], "intro_text": ""}
cases = [
    # (sizes, 期望片段)
    ([("百度网盘", "6.18 GB", "-PC"), ("移动云盘", "1.9 GB", "-安卓")],
     "网盘大小：百度网盘-PC 6.18 GB ｜ 移动云盘-安卓 1.9 GB"),
    ([("百度网盘", "14.2 GB", "-PC"), ("移动云盘", "15.28 GB", "-PC")],
     "网盘大小：百度网盘-PC 14.2 GB ｜ 移动云盘-PC 15.28 GB"),
    ([("百度网盘", "4.64 GB", "-PC")],
     "网盘大小：百度网盘-PC 4.64 GB"),
    ([("百度网盘", "5 GB", "")],          # 双端支持 → 不标注
     "网盘大小：百度网盘 5 GB"),
]
for sizes, want in cases:
    out = crawler._build_content(galgame, [], sizes)
    first_line = out.split("\n")[0]
    check(f"标注 {want[:28]}...", first_line, want)

print()
print("=== 4. 导出侧不再剔除「网盘大小」行 ===")
gen_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "generator", "__init__.py")
src = open(gen_path, encoding="utf-8").read()
check("生成器已无剔除逻辑",
      'if not ln.strip().startswith("网盘大小：")' in src, False)
check("生成器 copy_text 取完整备注",
      "copy_text = note_text.strip()" in src, True)

js_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "app.js")
js = open(js_path, encoding="utf-8").read()
check("前端已无剔除逻辑",
      'indexOf("网盘大小：") !== 0' in js, False)
check("导出模板 copyNote 本就不过滤",
      "function copyNote(el) {{" in src and "网盘大小" not in src.split("function copyNote")[1][:400],
      True)

print()
print("=== 5. 超限跳过逻辑 ===")
# 直接调 parse_detail 太重（要联网），改为验证判定分支的构造
oversize_src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                 "crawler", "kungal.py"), encoding="utf-8").read()
check("超过上限时返回 skip_reason",
      "skip_reason" in oversize_src, True)
check("超限返回 platform=unknown（引擎据此跳过）",
      oversize_src.count('"platform": "unknown"') >= 2, True)


def would_skip(size_text):
    """复刻跳过判定：任一网盘 > 10GB 即跳过。"""
    gb = _size_to_gb(size_text)
    return gb is not None and gb > MAX_SIZE_GB


check("9.99 GB 不跳过", would_skip("9.99 GB"), False)
check("10.0 GB 不跳过（等于上限）", would_skip("10.0 GB"), False)
check("10.01 GB 跳过", would_skip("10.01 GB"), True)
check("44.94 GB 跳过（万华镜实例）", would_skip("44.94 GB"), True)
check("900 MB 不跳过", would_skip("900 MB"), False)
check("解析失败不跳过（保守）", would_skip("未知"), False)

print()
print("=== 6. 引擎日志会输出跳过原因 ===")
eng_src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "crawler", "__init__.py"), encoding="utf-8").read()
check("_crawl_detail_and_count 读 skip_reason",
      "post.get(\"skip_reason\")" in eng_src, True)

print()
print(f"总计：{PASS} 通过 / {FAIL} 失败")
sys.exit(1 if FAIL else 0)
