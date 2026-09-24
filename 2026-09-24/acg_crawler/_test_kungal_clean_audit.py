# -*- coding: utf-8 -*-
"""备注引流清洗 + 清洗日志 的回归测试

覆盖三件事：
1. 文档 4.1 的样本表（删哪些 / 留哪些）必须与原行为一致
2. _promo_rule() 返回的规则名与 _is_promo_line() 的布尔结果必须一一对应
3. audit 输出必须如实反映"删了什么、按哪条规则删、留下什么可疑行"

运行：cd acg_crawler && C:/Python314/python.exe _test_kungal_clean_audit.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from crawler.kungal import KungalCrawler, _is_promo_line, _promo_rule, _audit_clean

_fail = 0


def check(name, got, want):
    global _fail
    ok = got == want
    if not ok:
        _fail += 1
    print(f"{'PASS' if ok else 'FAIL'}  {name}")
    if not ok:
        print(f"      期望 {want!r}")
        print(f"      实际 {got!r}")


# ---------- 1. 文档 4.1 样本表 ----------
DELETE_CASES = [
    ("◆！先看解压教程【pan.quark.cn/s/b85f2556d1dc】", "②外部域名"),
    ("欢迎加群 581561231(工具&教程&汇总群)", "③社群或教程关键词"),
    ("<https://www.slpeey.com/%E3%80%90PC+%E5%AE%89%E5%8D%93%E3%80%91>", "①整行裸链接"),
    ("https://yun.139.com/shareweb/#/w/i/2wFGZpCs0g60e", "①整行裸链接"),
    ("lz4 解压工具如下 https://yun.139.com/shareweb/", "④链接+工具教程词"),
    ("更详细的介绍请查看", "⑤引导句收尾"),
    ("581561231", "⑥QQ号"),
    ("PC\u200b", "⑦残留平台名"),
    ("安卓\u3000", "⑦残留平台名"),
]
KEEP_CASES = [
    "推荐使用 Bandizip",
    "甜蜜夏日系列合集，包含以下内容",
    "lz4 解压工具",              # 提到工具但没链接 → 保留（文档 4.1 明确要求）
    "1. 第一章 日常篇",
    "",
    "   ",
]

for line, want_rule in DELETE_CASES:
    check(f"删除 → {want_rule}  {line[:26]!r}", _promo_rule(line), want_rule)

for line in KEEP_CASES:
    check(f"保留  {line[:26]!r}", _promo_rule(line), None)

# ---------- 2. 规则名与布尔结果一致 ----------
for line in [c[0] for c in DELETE_CASES] + KEEP_CASES:
    check(f"rule/bool 一致 {line[:20]!r}",
          _is_promo_line(line), _promo_rule(line) is not None)

# ---------- 3. audit 输出 ----------
NOTE = "\n".join([
    "◆！先看解压教程【pan.quark.cn/s/b85f2556d1dc】",   # ② 删
    "推荐使用 Bandizip",                                  # 保留
    "解压密码：open",                                     # 密码行 → 删
    "注：以下内容以推荐游玩顺序排列：",                      # 组上方引导句 → 连坐删
    "1. 某游戏A https://www.bilibili.com/video/BV1xx",    # ② 删，触发整组
    "2. 某游戏B https://b23.tv/abcdef",                   # ② 删
    "3. 某游戏C",                                         # 无链接 → 连坐删
    "问题解答请联系 root@example.com",                     # ③ 删（"问题解答"）
    "更多说明见 https://example.org/help",                 # ★ 现有规则不覆盖 → 保留，进 suspect
])
audit = {"label": "百度网盘"}
out = KungalCrawler._optimize_note(NOTE, "", audit)

removed_lines = {r["line"] for r in audit["removed"]}
check("正文不再含已识别的引流行",
      any(x in out for x in ("pan.quark.cn", "bilibili", "b23.tv")), False)
check("正文保留 Bandizip 行", "推荐使用 Bandizip" in out, True)
check("密码行被删除", any("解压密码" in l for l in removed_lines), True)
check("编号列表整组删除（含末项）",
      {"2. 某游戏B https://b23.tv/abcdef", "3. 某游戏C"} <= removed_lines, True)
check("组上方引导句被删除",
      any(l.startswith("注：") for l in removed_lines), True)
check("命中规则名带出来",
      {r["rule"] for r in audit["removed"]}
      >= {"②外部域名", "解压密码行", "编号列表连坐"}, True)
check("被删行都有规则标注",
      all(r["rule"] for r in audit["removed"]), True)

# 已知缺口：编号列表里挂了个不在域名库的外部链接 → 规则不覆盖，行会被留下。
# 这正是 suspect 日志要暴露的"漏删候选"，这里固化下来，避免以后误以为已覆盖。
check("规则未覆盖的外部链接行被保留（漏删候选）",
      "example.org" in out, True)
suspect = {s["line"] for s in audit["suspect"]}
check("漏删候选进了 suspect",
      any("example.org" in s for s in suspect), True)
check("suspect 不包含被删行", suspect & removed_lines, set())

audit2 = {"label": "移动云盘"}
KungalCrawler._optimize_note("正常说明，推荐使用 lz4 解压\n联系方式见签名", "", audit2)
check("全保留时 removed 为空", audit2["removed"], [])
check("含'联系'的保留行进 suspect",
      [s["line"] for s in audit2["suspect"]] == ["联系方式见签名"], True)

# 编号列不触发整组时不得误删
audit3 = {}
KungalCrawler._optimize_note("1. 第一章 日常篇\n2. 第二章 学院篇", "", audit3)
check("正常编号列表不误删", audit3["removed"], [])

# 空备注不得报错
check("空备注返回空串", KungalCrawler._optimize_note(""), "")

# ---------- 4. 日志落盘 ----------
# 用唯一 gid，避免重复运行时命中上一轮留下的记录（日志是追加写的）
marker = f"test-{os.getpid()}"
_audit_clean(marker, "测试条目 【PC】", [audit])
log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs", "promo_clean")
files = sorted(os.listdir(log_dir)) if os.path.isdir(log_dir) else []
check("清洗日志已生成", bool(files), True)
if files:
    import json
    with open(os.path.join(log_dir, files[-1]), encoding="utf-8") as f:
        recs = [json.loads(x) for x in f if x.strip()]
    hit = [r for r in recs if r.get("gid") == marker]
    check("日志含本次记录", len(hit), 1)
    if hit:
        check("日志分级标注网盘", hit[0]["notes"][0]["label"], "百度网盘")
        check("日志含删除明细", len(hit[0]["notes"][0]["removed"]) > 0, True)

print()
print("全部通过 ✓" if _fail == 0 else f"有 {_fail} 项失败 ✗")
sys.exit(1 if _fail else 0)
