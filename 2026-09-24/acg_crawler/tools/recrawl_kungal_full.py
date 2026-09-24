# -*- coding: utf-8 -*-
"""全库重爬鲲Galgame（应用最新备注引流清洗规则）

为什么单独做脚本而不点界面按钮：界面是常驻进程，Python 模块在启动时就加载完了；
如果页面服务在改动 crawler/kungal.py 之前就起着，点按钮跑的还是改动前的旧代码。
本脚本每次新起进程，保证用的是磁盘上最新的清洗规则。

用法：
    cd acg_crawler
    C:/Python314/python.exe tools/recrawl_kungal_full.py                # 默认 1 → 站点末页
    C:/Python314/python.exe tools/recrawl_kungal_full.py --start 31     # 断点续爬

说明：
- 入库是 INSERT OR REPLACE（UNIQUE source+source_id），重爬是就地刷新，不会产生重复
- 逐条入库、逐页提交，中断后带 --start 续爬即可
- 清洗审计写在 logs/promo_clean/YYYY-MM-DD.jsonl
- 爬取过程日志写在 logs/recrawl_kungal_<时间戳>.log
"""
import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config import load_config                      # noqa: E402
from crawler import CrawlerEngine                   # noqa: E402
from crawler.kungal import KungalCrawler            # noqa: E402


def main():
    ap = argparse.ArgumentParser(description="全库重爬鲲Galgame")
    ap.add_argument("--start", type=int, default=1, help="起始页（断点续爬用）")
    ap.add_argument("--end", type=int, default=0, help="结束页，0=站点末页")
    ap.add_argument("--speed", default="balanced", choices=["stable", "balanced", "fast"])
    args = ap.parse_args()

    log_path = ROOT / "logs" / f"recrawl_kungal_{time.strftime('%Y%m%d-%H%M%S')}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_fp = log_path.open("a", encoding="utf-8")

    def log(msg):
        line = f"[{datetime.now():%H:%M:%S}] {msg}"
        print(line, flush=True)
        log_fp.write(line + "\n")
        log_fp.flush()

    cfg = load_config()
    total_pages = KungalCrawler(cfg).get_total_pages()
    end = args.end or total_pages
    if args.start < 1 or args.start > end:
        log(f"页范围不合法: {args.start}-{end}（站点共 {total_pages} 页）")
        return 1

    log(f"===== 全库重爬鲲Galgame 第 {args.start}-{end} 页 "
        f"（站点共 {total_pages} 页，速度 {args.speed}）=====")

    engine = CrawlerEngine(cfg)
    engine.log_callback = lambda site, msg, level="info": log(f"[{site}][{level}] {msg}")

    t0 = time.time()
    result = engine.crawl_by_page({"kungal": (args.start, end)},
                                  speed_name=args.speed, skip_existing=False)
    mins = (time.time() - t0) / 60
    log(f"===== 结束 status={result['status']} 成功={result['success']} "
        f"跳过={result['skipped']} 失败={result['error']} 用时={mins:.1f} 分钟 =====")
    log(f"任务ID={result['task_id']}  爬取日志={log_path.name}")
    log_fp.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
