"""爬虫引擎：站点并发 + 站内详情并发 + 独立站点状态"""
import json
import threading
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

from crawler.acgyxj import ACGYXJCrawler
from crawler.acgrx import ACGRXCrawler
from crawler.acgll import ACGLLCrawler
from crawler.acgjlb import ACGJLBCrawler
from crawler.kungal import KungalCrawler
from database import insert_post, create_task, update_task, delete_task, delete_posts_by_task, get_conn
from config import get_speed_profile, get_site_detail_workers

CRAWLERS = {
    "acgyxj": ACGYXJCrawler,
    "acgrx": ACGRXCrawler,
    "acgll": ACGLLCrawler,
    "acgjlb": ACGJLBCrawler,
    "kungal": KungalCrawler,
}

# 站点键 -> 中文名（面板显示用，不依赖爬虫实例）
SITE_NAMES = {
    "acgyxj": "ACG游戏姬",
    "acgrx": "萌幻ACG",
    "acgll": "ACG图书馆",
    "acgjlb": "ACG俱乐部",
    "kungal": "鲲Galgame",
}


class CrawlerEngine:
    """爬虫引擎"""

    def __init__(self, config):
        self.config = config
        self.running = False
        self.cancelled = False
        self.task_id = None
        self.auto_delete_on_cancel = False
        self.cleanup_images_callback = None
        self.speed_name = "balanced"
        self.progress_callback = None
        self.log_callback = None
        self.site_status_callback = None
        self._lock = threading.Lock()
        # 每站独立状态：{site_key: {status, current, total, success, skipped, error, page, logs: []}}
        self.site_states = {}
        self.site_logs = {}

    def _log(self, site, msg, level="info"):
        if self.log_callback:
            self.log_callback(site, msg, level)
        # 按站点名记录日志（键与site_states的site_key通过名字反查兼容）
        with self._lock:
            if site not in self.site_logs:
                self.site_logs[site] = []
            self.site_logs[site].append({"text": msg, "level": level})
            if len(self.site_logs[site]) > 200:
                self.site_logs[site] = self.site_logs[site][-100:]

    # 站点名 -> site_key 反查表（懒加载，用于站点日志与面板对齐）
    _NAME_TO_KEY = None

    @classmethod
    def _get_name_to_key(cls):
        if cls._NAME_TO_KEY is None:
            cls._NAME_TO_KEY = {v: k for k, v in SITE_NAMES.items()}
        return cls._NAME_TO_KEY

    def _site_log(self, site_key, msg, level="info"):
        """站点专属日志（面板显示用）"""
        site_name = SITE_NAMES.get(site_key, site_key)
        self._log(site_name, msg, level)

    def _update_site_state(self, site_key, **kwargs):
        with self._lock:
            if site_key not in self.site_states:
                self.site_states[site_key] = {
                    "status": "waiting", "current": 0, "total": 0,
                    "success": 0, "skipped": 0, "error": 0, "page": 0
                }
            self.site_states[site_key].update(kwargs)
            state = dict(self.site_states[site_key])
        if self.site_status_callback:
            self.site_status_callback(site_key, state)

    def _init_site_states(self, sites):
        self.site_states = {}
        self.site_logs = {}
        for site in sites:
            self._update_site_state(site, status="waiting", current=0, total=0,
                                    success=0, skipped=0, error=0, page=0)

    def _aggregate_progress(self):
        """汇总所有站点进度"""
        with self._lock:
            states = list(self.site_states.values())
        current = sum(s.get("current", 0) for s in states)
        total = sum(s.get("total", 0) for s in states)
        success = sum(s.get("success", 0) for s in states)
        skipped = sum(s.get("skipped", 0) for s in states)
        error = sum(s.get("error", 0) for s in states)
        if self.progress_callback:
            self.progress_callback(current, total, success, skipped, error)

    def _process_post(self, site_key, crawler, post, counters, task_id):
        """处理单个帖子：过滤+入库，返回 'success'/'skipped'/'error'"""
        try:
            if self.cancelled:
                return "skipped"
            if not post:
                return "error"
            if not post.get("title", "").strip():
                return "skipped"
            if post.get("platform") == "unknown":
                return "skipped"
            has_baidu = bool(post.get("baidu_link"))
            has_mobile = bool(post.get("mobile_link"))
            # 兼容 v4 多链接：download_items_json 含 baidu/mobile provider 时也算有链接
            if not (has_baidu or has_mobile):
                items_str = post.get("download_items_json")
                if items_str:
                    try:
                        items = json.loads(items_str) if isinstance(items_str, str) else items_str
                        if any(it.get("provider") in ("baidu", "mobile") for it in items):
                            has_baidu = True
                    except Exception:
                        pass
            if not (has_baidu or has_mobile):
                return "skipped"
            post["crawl_id"] = task_id
            insert_post(post)
            return "success"
        except Exception:
            return "error"

    def _crawl_detail_and_count(self, site_key, crawler, item, counters, task_id, skip_existing=False):
        """解析单个详情页并更新站点计数；skip_existing=True 时已入库的帖子直接跳过"""
        url = item["url"] if isinstance(item, dict) else item
        category = item.get("category", "") if isinstance(item, dict) else ""
        result = "error"
        if skip_existing and self._url_exists(crawler, url):
            self._site_log(site_key, f"已入库，跳过 {url}")
            with self._lock:
                st = self.site_states.get(site_key, {})
                st["current"] = st.get("current", 0) + 1
                st["skipped"] = st.get("skipped", 0) + 1
            self._aggregate_progress()
            return "skipped"
        try:
            if self.cancelled:
                return "skipped"
            post = crawler.parse_detail(url, category=category) if category else crawler.parse_detail(url)
            result = self._process_post(site_key, crawler, post, counters, task_id)
            if result == "success":
                self._site_log(site_key, f"✓ {post['title'][:50]}...")
            elif result == "skipped" and post:
                reason = post.get("skip_reason")
                if reason:
                    self._site_log(site_key,
                                   f"✗ 跳过 {reason}：{(post.get('title') or '')[:50]}")
                else:
                    self._site_log(site_key,
                                   f"✗ 跳过(无链接/平台未知): {(post.get('title') or '')[:50]}...")
        except Exception as e:
            result = "error"
            self._site_log(site_key, f"解析失败: {e}", "error")

        # 更新站点计数
        with self._lock:
            st = self.site_states.get(site_key, {})
            st["current"] = st.get("current", 0) + 1
            if result == "success":
                st["success"] = st.get("success", 0) + 1
            elif result == "skipped":
                st["skipped"] = st.get("skipped", 0) + 1
            else:
                st["error"] = st.get("error", 0) + 1
        self._aggregate_progress()
        return result

    def _crawl_site_by_page(self, site_key, start_page, end_page, task_id, skip_existing=False):
        """单站点按页码爬取（站内详情并发）；skip_existing=True 时跳过已入库帖子"""
        detail_workers = get_site_detail_workers(self.speed_name, site_key)
        crawler_cls = CRAWLERS.get(site_key)
        if not crawler_cls:
            return
        crawler = crawler_cls(self.config)
        self._update_site_state(site_key, status="running")
        dedup_hint = "，跳过已入库" if skip_existing else ""
        self._site_log(site_key, f"开始爬取第 {start_page}-{end_page} 页（详情并发{detail_workers}{dedup_hint}）")

        try:
            for page in range(start_page, end_page + 1):
                if self.cancelled:
                    break
                try:
                    items = crawler.get_list_page(page)
                    with self._lock:
                        self.site_states[site_key]["page"] = page
                        self.site_states[site_key]["total"] += len(items)
                    self._site_log(site_key, f"第{page}页: 发现 {len(items)} 个帖子")
                    self._aggregate_progress()

                    if detail_workers <= 1:
                        for item in items:
                            if self.cancelled:
                                break
                            self._crawl_detail_and_count(site_key, crawler, item, None, task_id, skip_existing)
                    else:
                        with ThreadPoolExecutor(max_workers=detail_workers) as executor:
                            futures = []
                            for item in items:
                                if self.cancelled:
                                    break
                                futures.append(executor.submit(
                                    self._crawl_detail_and_count, site_key, crawler, item, None, task_id, skip_existing))
                            for f in as_completed(futures):
                                try:
                                    f.result()
                                except Exception:
                                    pass
                except Exception as e:
                    with self._lock:
                        self.site_states[site_key]["error"] = self.site_states[site_key].get("error", 0) + 1
                    self._site_log(site_key, f"第{page}页获取失败: {e}", "error")
                    self._aggregate_progress()

            final_status = "cancelled" if self.cancelled else "completed"
            self._update_site_state(site_key, status=final_status)
            self._site_log(site_key, "爬取完成" if not self.cancelled else "已停止")
        except Exception as e:
            self._update_site_state(site_key, status="failed")
            self._site_log(site_key, f"爬取出错: {e}", "error")

    def _url_exists(self, crawler, url):
        """URL预查：该站是否已存在此帖子（免去下载整个详情页）"""
        try:
            with get_conn() as conn:
                return conn.execute(
                    "SELECT id FROM posts WHERE source = ? AND source_url = ?",
                    (crawler.site_name, url)
                ).fetchone()
        except Exception:
            return None

    def _crawl_site_incremental(self, site_key, task_id):
        """单站点增量爬取：URL预查省流量，连续一整页全部已入库才停止。

        说明：这些站点会把"更新过的旧帖"顶回列表页（URL不变），
        旧逻辑"遇到第一个已存在就停"会永远学不到这类更新帖，
        因此改为整页判断。
        """
        detail_workers = get_site_detail_workers(self.speed_name, site_key)
        crawler_cls = CRAWLERS.get(site_key)
        if not crawler_cls:
            return
        crawler = crawler_cls(self.config)
        self._update_site_state(site_key, status="running")
        self._site_log(site_key, f"开始增量爬取（详情并发{detail_workers}）")

        try:
            page = 1
            max_pages = crawler.get_total_pages()
            consecutive_existing_pages = 0

            while page <= max_pages and consecutive_existing_pages < 2 and not self.cancelled:
                try:
                    items = crawler.get_list_page(page)
                    with self._lock:
                        self.site_states[site_key]["page"] = page
                    self._site_log(site_key, f"第{page}页: 发现 {len(items)} 个帖子")

                    # URL 预查：先在本页内判重，全已存在才停止翻页
                    urls = [item["url"] if isinstance(item, dict) else item for item in items]
                    existing_flags = {u: bool(self._url_exists(crawler, u)) for u in urls}
                    new_items = [it for it in items
                                 if not existing_flags[it["url"] if isinstance(it, dict) else it]]

                    if items and not new_items:
                        consecutive_existing_pages += 1
                        self._site_log(
                            site_key,
                            f"第{page}页全部已入库（连续{consecutive_existing_pages}页），继续确认下一页")
                        page += 1
                        continue
                    consecutive_existing_pages = 0

                    if not items:
                        self._site_log(site_key, f"第{page}页无帖子，停止")
                        break

                    # 只处理新帖：详情并发
                    with self._lock:
                        self.site_states[site_key]["total"] += len(items)
                    if detail_workers <= 1:
                        for item in new_items:
                            if self.cancelled:
                                break
                            self._crawl_detail_and_count(site_key, crawler, item, None, task_id)
                    else:
                        with ThreadPoolExecutor(max_workers=detail_workers) as executor:
                            futures = []
                            for item in new_items:
                                if self.cancelled:
                                    break
                                futures.append(executor.submit(
                                    self._crawl_detail_and_count, site_key, crawler, item, None, task_id))
                            for f in as_completed(futures):
                                try:
                                    f.result()
                                except Exception:
                                    pass

                    # 本页已存在部分计入进度
                    skipped_existing = len(items) - len(new_items)
                    if skipped_existing:
                        with self._lock:
                            st = self.site_states[site_key]
                            st["current"] += skipped_existing
                            st["skipped"] += skipped_existing
                        self._aggregate_progress()

                    page += 1
                except Exception as e:
                    self._site_log(site_key, f"第{page}页获取失败: {e}", "error")
                    page += 1

            if not self.cancelled and consecutive_existing_pages >= 2:
                self._site_log(site_key, "连续两页全部已入库，增量爬取完成")
            final_status = "cancelled" if self.cancelled else "completed"
            self._update_site_state(site_key, status=final_status)
            self._site_log(site_key, "增量爬取完成" if not self.cancelled else "已停止")
        except Exception as e:
            self._update_site_state(site_key, status="failed")
            self._site_log(site_key, f"爬取出错: {e}", "error")

    def _run_sites_parallel(self, sites, site_runner, mode_name, params):
        """并行运行各站点任务，返回汇总统计"""
        self.running = True
        self.cancelled = False
        self.auto_delete_on_cancel = False
        self._init_site_states(sites)

        sites_str = ",".join(sites)
        self.task_id = create_task(mode_name, params, sites_str)
        update_task(self.task_id, status="running", started_at=datetime.now().isoformat())

        max_workers = min(self.config.get("crawler", {}).get("site_workers", 4), len(sites))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(site_runner, site): site for site in sites}
            for future in as_completed(futures):
                site = futures[future]
                try:
                    future.result()
                except Exception as e:
                    # 不再静默吞掉站点线程异常
                    self._update_site_state(site, status="failed")
                    self._site_log(site, f"站点线程异常退出: {e}", "error")

        self.running = False
        status = "cancelled" if self.cancelled else "completed"

        # 汇总站点统计
        with self._lock:
            states = list(self.site_states.values())
        success = sum(s.get("success", 0) for s in states)
        skipped = sum(s.get("skipped", 0) for s in states)
        error = sum(s.get("error", 0) for s in states)

        update_task(
            self.task_id,
            status=status,
            finished_at=datetime.now().isoformat(),
            success_posts=success,
            skipped_posts=skipped,
            error_posts=error,
        )

        # Cancel后根据用户选择决定是否删除已爬数据
        if self.cancelled and self.auto_delete_on_cancel and self.task_id:
            self._site_log("系统", "正在删除已爬取的临时数据...")
            source_ids = delete_posts_by_task(self.task_id)
            if source_ids and self.cleanup_images_callback:
                self.cleanup_images_callback(source_ids)
            delete_task(self.task_id)
            self._site_log("系统", f"已删除 {len(source_ids)} 条帖子及图片")
            self.task_id = None

        return {
            "task_id": self.task_id,
            "status": status,
            "success": success,
            "skipped": skipped,
            "error": error,
        }

    def set_speed(self, speed_name):
        """设置速度档位（带白名单校验）"""
        name, _profile = get_speed_profile(speed_name)
        self.speed_name = name
        return name

    def crawl_by_page(self, site_pages, speed_name=None, skip_existing=False):
        """按页码爬取，每站可用不同区间。

        site_pages: {site_key: (start_page, end_page)}，非空。
                   各站总页数/更新速度不同，逐个指定可避免更新慢的站点翻到旧内容。
        skip_existing=True 时跳过已入库帖子（不刷新旧数据）。
        """
        if not isinstance(site_pages, dict) or not site_pages:
            raise ValueError("crawl_by_page 需要非空的 {site_key: (start_page, end_page)}")
        if speed_name:
            self.set_speed(speed_name)

        pages = {k: (int(v[0]), int(v[1])) for k, v in site_pages.items()}
        params = json.dumps({
            "site_pages": {k: {"start": s, "end": e} for k, (s, e) in pages.items()},
            "skip_existing": skip_existing,
        }, ensure_ascii=False)
        return self._run_sites_parallel(
            list(pages.keys()),
            lambda site: self._crawl_site_by_page(site, pages[site][0], pages[site][1],
                                                  self.task_id, skip_existing),
            "by_page", params
        )

    def crawl_by_date(self, sites, start_date, end_date, speed_name=None, skip_existing=False):
        """按日期爬取：逐页翻页，按帖子发布日期过滤，越界自动停。

        旧实现依赖 crawler.crawl_date_range() 一次性收集全部帖子再入库，
        没有进度、无法取消、日期提取失败时静默丢弃全部数据，已弃用。
        """
        if speed_name:
            self.set_speed(speed_name)
        params = json.dumps({"start_date": start_date, "end_date": end_date,
                            "skip_existing": skip_existing})
        return self._run_sites_parallel(
            sites,
            lambda site: self._crawl_site_by_date(site, start_date, end_date, self.task_id, skip_existing),
            "by_date", params
        )

    def crawl_incremental(self, sites, speed_name=None):
        """增量爬取（自动去重，整页已存在才停止）"""
        if speed_name:
            self.set_speed(speed_name)
        params = json.dumps({"mode": "incremental"})
        return self._run_sites_parallel(
            sites,
            lambda site: self._crawl_site_incremental(site, self.task_id),
            "incremental", params
        )

    def _crawl_site_by_date(self, site_key, start_date, end_date, task_id, skip_existing=False):
        """单站点按日期爬取：逐页解析，post_date 早于 start_date 即停止"""
        detail_workers = get_site_detail_workers(self.speed_name, site_key)
        crawler_cls = CRAWLERS.get(site_key)
        if not crawler_cls:
            return
        crawler = crawler_cls(self.config)
        self._update_site_state(site_key, status="running")
        dedup_hint = "，跳过已入库" if skip_existing else ""
        self._site_log(site_key, f"按日期爬取 {start_date} ~ {end_date}（详情并发{detail_workers}{dedup_hint}）")

        try:
            page = 1
            max_pages = crawler.get_total_pages()
            reached_older = False

            while page <= max_pages and not reached_older and not self.cancelled:
                try:
                    items = crawler.get_list_page(page)
                    with self._lock:
                        self.site_states[site_key]["page"] = page
                        self.site_states[site_key]["total"] += len(items)
                    self._site_log(site_key, f"第{page}页: 发现 {len(items)} 个帖子")
                    self._aggregate_progress()

                    in_range = []
                    for item in items:
                        url = item["url"] if isinstance(item, dict) else item
                        category = item.get("category", "") if isinstance(item, dict) else ""
                        if skip_existing and self._url_exists(crawler, url):
                            with self._lock:
                                st = self.site_states[site_key]
                                st["current"] += 1
                                st["skipped"] += 1
                            self._aggregate_progress()
                            continue
                        post = crawler.parse_detail(url, category=category) if category else crawler.parse_detail(url)
                        if post:
                            pd = post.get("post_date") or ""
                            if pd and pd < start_date:
                                # 列表按时间倒序，遇到更早的帖子即可停止
                                reached_older = True
                            elif pd and pd > end_date:
                                # 晚于结束日期：跳过但继续翻页
                                with self._lock:
                                    st = self.site_states[site_key]
                                    st["current"] += 1
                                self._aggregate_progress()
                            elif pd:
                                in_range.append(post)
                            else:
                                # 无日期数据：保守入库（避免日期提取偶发失败丢帖）
                                in_range.append(post)
                        else:
                            with self._lock:
                                st = self.site_states[site_key]
                                st["current"] += 1
                                st["error"] += 1
                            self._aggregate_progress()

                    for post in in_range:
                        if self.cancelled:
                            break
                        result = self._process_post(site_key, crawler, post, None, task_id)
                        with self._lock:
                            st = self.site_states[site_key]
                            st["current"] += 1
                            if result == "success":
                                st["success"] += 1
                            elif result == "skipped":
                                st["skipped"] += 1
                            else:
                                st["error"] += 1
                        self._aggregate_progress()

                    if reached_older:
                        self._site_log(site_key, f"第{page}页出现早于 {start_date} 的帖子，停止翻页")
                    page += 1
                except Exception as e:
                    self._site_log(site_key, f"第{page}页获取失败: {e}", "error")
                    page += 1

            final_status = "cancelled" if self.cancelled else "completed"
            self._update_site_state(site_key, status=final_status)
            self._site_log(site_key, "按日期爬取完成" if not self.cancelled else "已停止")
        except Exception as e:
            self._update_site_state(site_key, status="failed")
            self._site_log(site_key, f"爬取出错: {e}", "error")

    def cancel(self):
        self.cancelled = True

    # ===== 兼容旧接口 =====
    # 旧的 _make_site_runner_by_date / _process_and_count 已删除：
    # 依赖 crawl_date_range() 一次性收集全部帖子，无进度无取消，
    # 日期提取失败时静默丢帖，已由 _crawl_site_by_date 取代。
