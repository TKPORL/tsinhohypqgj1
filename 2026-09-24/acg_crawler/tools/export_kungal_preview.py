# -*- coding: utf-8 -*-
"""导出鲲Galgame 清洗效果预览 HTML（测试用，只取前 N 页）。

用途：只看爬取+清洗后的 HTML 呈现效果，不追求数据量。
默认取前 1 页（20 条），可用 --pages 调整。

用法：
    C:/Python314/python.exe tools/export_kungal_preview.py            # 1 页
    C:/Python314/python.exe tools/export_kungal_preview.py --pages 10 # 10 页
"""
import argparse
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import get_posts  # noqa: E402
from generator import export_posts  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(ROOT, "data", "crawler.db")


def load_kungal(limit):
    """按最新重爬批次取前 limit 条鲲Galgame。"""
    conn = sqlite3.connect(DB)
    try:
        # 取本次重爬批次（crawl_id 最大的一批），保证是新清洗规则产物
        row = conn.execute(
            "SELECT crawl_id FROM posts WHERE source='鲲Galgame' "
            "ORDER BY crawled_at DESC LIMIT 1").fetchone()
        crawl_id = row[0] if row else None
        sql = ("SELECT * FROM posts WHERE source='鲲Galgame' "
               + ("AND crawl_id=? " if crawl_id is not None else "")
               + "ORDER BY crawled_at DESC LIMIT ?")
        args = (crawl_id, limit) if crawl_id is not None else (limit,)
        cur = conn.execute(sql, args)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()], crawl_id
    finally:
        conn.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pages", type=int, default=1, help="取前几页（每页 20 条）")
    args = ap.parse_args()

    limit = args.pages * 20
    posts, crawl_id = load_kungal(limit)
    print(f"取到鲲Galgame {len(posts)} 条（来源批次 crawl_id={crawl_id}）")
    if not posts:
        print("没有数据，先跑 tools/recrawl_kungal_full.py")
        return 1

    result = export_posts(posts, name_suffix="测试预览")
    for key, path in result.items():
        if path:
            print(f"  {key:12s} -> {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
