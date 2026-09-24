"""排序规则回归测试：点赞降序 -> id 倒序。

覆盖 SQL 侧（POST_ORDER_SQL）、Python 侧（sort_posts）、接口分页、导出 HTML 四条路径，
断言它们口径一致。不发起任何网络请求。

2026-09-23 起取消「双网盘置顶」：那会让导出 HTML 到第 N 张时从高赞重新开始，
看着像排序坏了（用户反馈），现在全库应为单一段单调不增。
"""
import os
import re
import shutil

import app
import generator
from database import (get_posts, get_posts_by_crawl_id, get_crawl_batches,
                      is_dual_netdisk, sort_posts, POST_ORDER_SQL)

fails = []


def check(name, got, want=True):
    ok = got == want
    print(("PASS " if ok else "FAIL ") + name + " -> " + repr(got))
    if not ok:
        fails.append(name + ": got=" + repr(got) + " want=" + repr(want))


def likes_of(rows):
    return [int(r.get("likes") or 0) for r in rows]


def is_ordered(rows):
    """点赞单调不增（单一段，允许相等）"""
    s = likes_of(rows)
    return all(s[i] >= s[i + 1] for i in range(len(s) - 1))


print("---- 1. SQL 侧：全库排序形状 ----")
all_rows = get_posts(limit=10 ** 6)
check("全库条数", len(all_rows) > 0)
check("全库点赞单调不增（无分段重启）", is_ordered(all_rows))
dual_n = sum(1 for r in all_rows if is_dual_netdisk(r))
print("   双网盘 %s 条，单网盘 %s 条（仅作信息，已不参与排序）" % (dual_n, len(all_rows) - dual_n))
restarts = [i for i in range(1, len(all_rows)) if likes_of(all_rows)[i] > likes_of(all_rows)[i - 1]]
check("分段重启点数量", len(restarts), 0)

print("---- 2. SQL 与 Python 两侧口径一致 ----")
check("sort_posts 结果与 SQL 顺序完全一致",
      [(r["id"], r["likes"]) for r in sort_posts(all_rows)] == [(r["id"], r["likes"]) for r in all_rows])

print("---- 3. 接口分页：每页每组有序 + 同一组跨页连续 ----")
# 注意：接口返回的是按平台分好的组，视觉顺序 = 逐组展示，
# 所以「有序」只在组内成立，不能把不同组拉平了比。
c = app.app.test_client()
by_group = {}
page_ids = []
for off in (0, 60, 120):
    d = c.get("/api/posts_grouped?platform=all&limit=60&offset=%d" % off).get_json()
    for g in d["groups"]:
        check("offset=%d [%s] 组内有序" % (off, g["label"]), is_ordered(g["posts"]))
        by_group.setdefault(g["label"], []).extend(g["posts"])
        page_ids.extend(p["id"] for p in g["posts"])
for label, rows in by_group.items():
    check("[%s] 跨页拼接后仍有序" % label, is_ordered(rows))
check("三页无重复", len(set(page_ids)) == len(page_ids))

print("---- 4. 批次视图同样口径 ----")
bid = get_crawl_batches()[0]["crawl_id"]
batch_rows = get_posts_by_crawl_id(bid)
check("批次(%s)排序形状" % bid, is_ordered(batch_rows))

print("---- 5. 导出 HTML 卡片顺序 ----")
posts = all_rows[:40]
path = generator.generate_html(posts, "排序测试", "_sort_check.html")
img_dir = os.path.join(os.path.dirname(path), "images")
try:
    html = open(path, encoding="utf-8").read()
    likes = [int(x) for x in re.findall(r"LIKE\s*</span>\s*(\d+)", html)]
    want = [int(p["likes"]) for p in sort_posts(posts)]
    check("导出卡片点赞序列 == sort_posts 结果", likes == want)
    check("导出卡片序列单调不增", all(likes[i] >= likes[i + 1] for i in range(len(likes) - 1)))
    check("导出条数", len(likes), len(posts))
finally:
    if os.path.exists(path):
        os.remove(path)
    if os.path.isdir(img_dir):
        shutil.rmtree(img_dir, ignore_errors=True)
    check("临时导出文件已清理", os.path.exists(path), False)

print("---- 6. 排序 SQL 口径 ----")
check("POST_ORDER_SQL 为纯点赞降序（不含双网盘 CASE）",
      "likes" in POST_ORDER_SQL and "id DESC" in POST_ORDER_SQL and "CASE WHEN" not in POST_ORDER_SQL)

print()
print("FAILED: " + (", ".join(fails) if fails else "none"))
