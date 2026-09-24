"""临时验证脚本：站点页码解析 + 请求校验 + 幽灵站点回归。

只 monkeypatch 引擎的爬取入口，不发起任何真实网络请求。
"""
import time

import app

captured = {}


def fake_crawl_by_page(site_pages, speed_name=None, skip_existing=False):
    captured["site_pages"] = site_pages
    captured["skip_existing"] = skip_existing


app.engine.crawl_by_page = fake_crawl_by_page
c = app.app.test_client()

fails = []


def check(name, got, want):
    ok = got == want
    print(("PASS " if ok else "FAIL ") + name + " -> " + repr(got))
    if not ok:
        fails.append(name + ": got=" + repr(got) + " want=" + repr(want))


print("---- 1. 每站独立页码 ----")
captured.clear()
r = c.post("/api/start_crawl", json={
    "mode": "by_page",
    "sites": ["acgyxj", "acgrx", "acgll", "acgjjb"],
    "site_pages": {
        "acgyxj": {"start": 1, "end": 5},
        "acgrx": {"start": 2, "end": 3},
        "acgll": {"start": 1, "end": 10},
        "acgjlb": {"start": 1, "end": 1},
    },
    "speed": "balanced",
    "skip_existing": True,
})
check("启动返回", r.get_json().get("status"), "ok")
time.sleep(0.4)
check("按站传参", captured.get("site_pages"), {
    "acgyxj": (1, 5), "acgrx": (2, 3), "acgll": (1, 10), "acgjlb": (1, 1)})
check("去重开关", captured.get("skip_existing"), True)

print("---- 2. 非法站点 key 被丢弃（幽灵站点回归）----")
captured.clear()
r = c.post("/api/start_crawl", json={
    "mode": "by_page",
    "site_pages": {"acgyxj": {"start": 1, "end": 3}, "on": {"start": 1, "end": 9}},
})
check("只保留白名单站点", captured.get("site_pages"), {"acgyxj": (1, 3)})

print("---- 3. 全非法站点 -> 直接拒绝，不启动任务 ----")
captured.clear()
r = c.post("/api/start_crawl", json={"mode": "by_page", "sites": ["on"], "site_pages": {}})
check("返回 error", r.get_json().get("status"), "error")
check("未调用爬取", "site_pages" in captured, False)

print("---- 4. 页码越界与倒置 ----")
captured.clear()
c.post("/api/start_crawl", json={
    "mode": "by_page",
    "site_pages": {"acgyxj": {"start": 0, "end": 99999},
                   "acgrx": {"start": 7, "end": 2},
                   "acgll": {"start": "abc", "end": None}},
})
time.sleep(0.4)
check("夹取与倒置修正", captured.get("site_pages"),
      {"acgyxj": (1, 999), "acgrx": (7, 7), "acgll": (1, 1)})

print("---- 5. 旧格式 sites + start_page/end_page 仍可用 ----")
captured.clear()
c.post("/api/start_crawl", json={
    "mode": "by_page", "sites": ["acgyxj", "acgrx"], "start_page": 3, "end_page": 6,
})
time.sleep(0.4)
check("旧格式兼容", captured.get("site_pages"), {"acgyxj": (3, 6), "acgrx": (3, 6)})

print("---- 6. 未知模式被拒绝 ----")
r = c.post("/api/start_crawl", json={"mode": "by_magic", "sites": ["acgyxj"]})
check("返回 error", r.get_json().get("status"), "error")

print("---- 7. 引擎入口参数校验 ----")
try:
    app.engine.__class__.crawl_by_page(app.engine, [])
    check("空字典抛错", "no-raise", "raise")
except ValueError:
    check("空字典抛错", "raise", "raise")

print("---- 8. index.html 里 #targetSites 内恰好 4 个站点勾选框 ----")
html = open("templates/index.html", encoding="utf-8").read()
block = html.split('id="targetSites"')[1].split("</div>\n                </div>")[0]
check("站点勾选框数量", block.count('type="checkbox"'), 4)
check("已移除死控件 pageSite", 'id="pageSite"' in html, False)
check("已移除旧 pageGroup", 'id="pageGroup"' in html, False)

print()
print("FAILED: " + (", ".join(fails) if fails else "none"))
