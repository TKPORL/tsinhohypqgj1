"""ACG资源聚合爬取工具 - 主程序"""
import json
import os
import time
import threading
import requests as req_lib
from pathlib import Path
from flask import Flask, render_template, request, jsonify, send_file, Response

from config import load_config
from database import (init_db, get_posts, get_post_count, delete_post, get_tasks, delete_task,
                      get_conn, get_crawl_batches, get_posts_by_crawl_id, get_batch_post_count,
                      recover_interrupted_tasks, delete_posts_by_ids, delete_posts_by_task,
                      get_shared_source_ids, POST_ORDER_SQL)
from crawler import CrawlerEngine
from crawler import SITE_NAMES
from generator import export_posts, export_posts_filtered

app = Flask(__name__)
config = load_config()
init_db()
recovered_tasks = recover_interrupted_tasks()

def _maybe_auto_backup():
    """启动时检查，距上次备份 > 7 天自动备份一次（保留最近 10 个）"""
    try:
        from database import DB_PATH
        backups_dir = DB_PATH.parent / "backups"
        backups_dir.mkdir(parents=True, exist_ok=True)
        # 检查最近备份时间
        existing = sorted(backups_dir.glob("crawler-*.db"), key=lambda p: p.stat().st_mtime, reverse=True)
        if existing and (existing[0].stat().st_mtime > time.time() - 7 * 86400):
            return  # 7 天内已备份过，跳过
        # 执行备份
        import shutil as _sh
        ts = time.strftime("%Y%m%d-%H%M%S")
        dest = backups_dir / f"crawler-{ts}.db"
        _sh.copy2(str(DB_PATH), str(dest))
        # 清理多余备份（保留最近 10 个）
        all_backups = sorted(backups_dir.glob("crawler-*.db"), key=lambda p: p.stat().st_mtime, reverse=True)
        for old_bak in all_backups[10:]:
            try:
                old_bak.unlink()
            except Exception:
                pass
    except Exception as e:
        print(f"[备份] 自动备份失败: {e}")

_maybe_auto_backup()

IMAGES_DIR = Path(__file__).parent / "images"
LOG_DIR = Path(__file__).parent / "logs"
LOG_RETENTION_DAYS = 30


def _write_log_file(entry):
    """把日志条目追加到 logs/{YYYY-MM-DD}.log，超 30 天自动清理"""
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        log_file = LOG_DIR / f"{time.strftime('%Y-%m-%d')}.log"
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(entry + "\n")
        # 清理 30 天前的旧日志
        import glob
        cutoff = time.time() - LOG_RETENTION_DAYS * 86400
        for old_file in glob.glob(str(LOG_DIR / "*.log")):
            try:
                if os.path.getmtime(old_file) < cutoff:
                    os.remove(old_file)
            except Exception:
                pass
    except Exception:
        pass  # 日志落盘失败不影响主流程

# 重新下载图片任务状态（可取消）
redownload_state = {
    "running": False,
    "cancelled": False,
    "total": 0,
    "current": 0,
    "updated": 0,
    "skipped": 0,
    "failed": 0,
    "started_at": None,
    "finished_at": None,
    "error": None,
}

engine = CrawlerEngine(config)

# 日志和进度存储
log_store = {"logs": []}
progress_store = {"current": 0, "total": 0, "success": 0, "skipped": 0, "error": 0}

def log_callback(site, msg, level="info"):
    timestamp = time.strftime("%H:%M:%S")
    full_ts = time.strftime("%Y-%m-%d %H:%M:%S")
    log_entry = f"[{timestamp}] [{site}] {msg}"
    log_store["logs"].append({"text": log_entry, "level": level})
    if len(log_store["logs"]) > 500:
        log_store["logs"] = log_store["logs"][-300:]
    # 落盘到 logs/{YYYY-MM-DD}.log（含 ISO 时间戳，便于追溯）
    _write_log_file(f"{full_ts} [{level.upper()}] [{site}] {msg}")

def progress_callback(current, total, success, skipped, error):
    progress_store["current"] = current
    progress_store["total"] = total
    progress_store["success"] = success
    progress_store["skipped"] = skipped
    progress_store["error"] = error

engine.log_callback = log_callback
engine.progress_callback = progress_callback
engine.cleanup_images_callback = lambda ids: _remove_post_images(ids)


def _export_filter_conditions(plat, source, keyword):
    """构造与结果页一致的 WHERE 条件，返回 (conditions, params)"""
    conds, params = [], []
    if plat and plat != "all":
        if plat == "pc":
            conds.append("(platform = 'pc' OR platform = 'unknown')")
        elif plat == "pc_android":
            conds.append("platform = 'pc_android'")
        elif plat == "android":
            conds.append("platform = 'android'")
        else:
            conds.append("platform = ?")
            params.append(plat)
    if source and source != "all":
        conds.append("source = ?")
        params.append(source)
    for kw in keyword.split():
        if kw:
            conds.append("title LIKE ?")
            params.append(f"%{kw}%")
    return conds, params


def _export_tag(source, export_type):
    """文件名标识：来源站名（平台已在前缀"PC下载/PC+安卓下载"里，不重复）"""
    if source and source != "all":
        return source
    return "全部来源"


def _fetch_filtered_posts(plat=None, source="all", keyword=""):
    conds, params = _export_filter_conditions(plat, source, keyword)
    sql = "SELECT * FROM posts"
    if conds:
        sql += " WHERE " + " AND ".join(conds)
    sql += " " + POST_ORDER_SQL
    with get_conn() as conn:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]


def _filtered_post_count(plat=None, source="all", keyword=""):
    conds, params = _export_filter_conditions(plat, source, keyword)
    sql = "SELECT COUNT(*) FROM posts"
    if conds:
        sql += " WHERE " + " AND ".join(conds)
    with get_conn() as conn:
        return conn.execute(sql, params).fetchone()[0]


def _remove_post_images(source_ids):
    """删除指定 source_id 对应的 images/{source_id}/ 目录。

    各站帖子ID均为纯数字可能撞车：仅当该 source_id 不再被任何帖子
    引用时才删目录，避免删A站帖子误删B站图片。
    目录不存在/删除失败仅记日志，不抛异常。
    """
    import shutil
    if not source_ids:
        return
    unique_ids = {str(s) for s in source_ids if s}
    try:
        still_used = get_shared_source_ids(unique_ids)
    except Exception:
        still_used = set()  # 查询失败时保守跳过删除，防止误删
    for sid in unique_ids - still_used:
        d = IMAGES_DIR / sid
        if d.exists() and d.is_dir():
            try:
                shutil.rmtree(d)
            except Exception as e:
                log_callback("系统", f"清理图片目录失败 {d}: {e}", "error")

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/images/<path:subpath>")
def serve_image(subpath):
    """提供本地下载的图片：/images/{post_id}/{filename}"""
    import re as _re
    # 安全校验：只允许数字目录名和合法文件名
    if ".." in subpath or not _re.fullmatch(r"[A-Za-z0-9_\-]+/[A-Za-z0-9_\-]+\.\w+", subpath):
        return "", 400
    img_path = IMAGES_DIR / subpath
    if img_path.exists():
        resp = send_file(str(img_path))
        resp.headers["Cache-Control"] = "public, max-age=86400"
        return resp
    return "", 404

import ipaddress
import socket
from urllib.parse import urlparse

@app.route("/api/proxy_image")
def api_proxy_image():
    """图片代理：服务端下载图片后转发给浏览器，解决防盗链问题（含SSRF防护）"""
    url = request.args.get("url", "")
    if not url:
        return "", 400

    # SSRF防护：只允许http/https，拒绝环回/私有/保留地址
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return "", 400
        hostname = parsed.hostname
        if not hostname:
            return "", 400
        addr_infos = socket.getaddrinfo(hostname, parsed.port or (443 if parsed.scheme == "https" else 80), proto=socket.IPPROTO_TCP)
        for addr_info in addr_infos:
            ip = ipaddress.ip_address(addr_info[4][0])
            if (ip.is_loopback or ip.is_private or ip.is_link_local
                    or ip.is_reserved or ip.is_multicast or ip.is_unspecified):
                return "", 400
    except (ValueError, socket.gaierror):
        return "", 400

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "image/webp,image/apng,image/*,*/*;q=0.8",
    }
    proxy = None
    if config.get("proxy", {}).get("enabled"):
        proxy = config["proxy"]["http"]

    # 尝试方式1: 通过代理
    if proxy:
        try:
            proxies = {"http": proxy, "https": proxy}
            resp = req_lib.get(url, headers={**headers, "Referer": url},
                               proxies=proxies, timeout=15, stream=True, verify=False)
            resp.raise_for_status()
            content_type = resp.headers.get("Content-Type", "image/jpeg")
            return Response(resp.iter_content(8192), content_type=content_type)
        except Exception:
            pass

    # 尝试方式2: 直连（无代理）
    try:
        resp = req_lib.get(url, headers=headers, timeout=15, stream=True, verify=False)
        resp.raise_for_status()
        content_type = resp.headers.get("Content-Type", "image/jpeg")
        return Response(resp.iter_content(8192), content_type=content_type)
    except Exception:
        return "", 404

@app.route("/api/posts")
def api_posts():
    platform = request.args.get("platform", "all")
    source = request.args.get("source", "all")
    try:
        limit = max(1, min(int(request.args.get("limit", 100)), 500))
        offset = max(0, int(request.args.get("offset", 0)))
    except (TypeError, ValueError):
        limit, offset = 100, 0
    posts = get_posts(platform=platform, source=source, limit=limit, offset=offset)
    total = get_post_count(platform=platform, source=source)
    return jsonify({"posts": posts, "total": total, "limit": limit, "offset": offset})

@app.route("/api/posts_grouped")
def api_posts_grouped():
    """按平台分组返回帖子（支持分页 limit/offset、关键字搜索）"""
    platform = request.args.get("platform", "all")
    source = request.args.get("source", "all")
    keyword = (request.args.get("q") or "").strip()
    batch = request.args.get("batch", type=int)
    try:
        limit = max(1, min(int(request.args.get("limit", 100)), 500))
        offset = max(0, int(request.args.get("offset", 0)))
    except (TypeError, ValueError):
        limit, offset = 100, 0

    # 关键字按空格分词，标题 AND 匹配
    kw_conditions, kw_params = [], []
    for kw in keyword.split():
        if kw:
            kw_conditions.append("title LIKE ?")
            kw_params.append(f"%{kw}%")

    with get_conn() as conn:
        # 先算过滤后总数（用于前端分页）
        count_query = "SELECT COUNT(*) FROM posts WHERE 1=1"
        count_params = []
        if batch:
            count_query += " AND crawl_id = ?"
            count_params.append(batch)
        if platform and platform != "all":
            if platform == "pc":
                count_query += " AND (platform = 'pc' OR platform = 'unknown')"
            elif platform == "pc_android":
                count_query += " AND platform = 'pc_android'"
            elif platform == "android":
                count_query += " AND platform = 'android'"
        if source and source != "all":
            count_query += " AND source = ?"
            count_params.append(source)
        for cond in kw_conditions:
            count_query += f" AND {cond}"
        count_params.extend(kw_params)
        total = conn.execute(count_query, count_params).fetchone()[0]

        query = "SELECT *, strftime('%Y-%m-%d %H:%M', crawled_at) as crawl_date FROM posts WHERE 1=1"
        params = []
        if batch:
            query += " AND crawl_id = ?"
            params.append(batch)
        if platform and platform != "all":
            if platform == "pc":
                query += " AND (platform = 'pc' OR platform = 'unknown')"
            elif platform == "pc_android":
                query += " AND platform = 'pc_android'"
            elif platform == "android":
                query += " AND platform = 'android'"
        if source and source != "all":
            query += " AND source = ?"
            params.append(source)
        for cond in kw_conditions:
            query += f" AND {cond}"
        params.extend(kw_params)
        query += f" {POST_ORDER_SQL} LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        rows = conn.execute(query, params).fetchall()

        # 按平台分组：PC / PC+安卓 / 安卓 三类互不重叠（2026-09-23 起单安卓独立成组）
        groups = {}
        for row in rows:
            d = dict(row)
            p = d.get("platform", "unknown")
            if p == "unknown":
                p = "pc"
            plat_label = {"pc": "PC", "pc_android": "PC+安卓", "android": "安卓"}.get(p, "其他")
            if plat_label not in groups:
                groups[plat_label] = {"label": plat_label, "platform": plat_label, "posts": [], "total": 0}
            groups[plat_label]["posts"].append(d)
            groups[plat_label]["total"] += 1

        plat_order = {"PC": 0, "PC+安卓": 1, "其他": 3}
        final = sorted(groups.values(), key=lambda g: plat_order.get(g["platform"], 9))
        return jsonify({"groups": final, "total": total, "limit": limit, "offset": offset})

MAX_PAGE = 999          # 单站页码上限，防止手滑输入超大值
CRAWL_MODES = ("by_page", "by_date", "incremental")


def _clamp_page(v, default):
    try:
        n = int(v)
    except (TypeError, ValueError):
        return default
    return max(1, min(n, MAX_PAGE))


def _parse_site_pages(data):
    """解析「勾了哪些站点 + 每个站点各自的页码范围」。

    返回 {site_key: (start, end)}，只保留白名单站点。
    优先读 site_pages={site:{start,end}}（前端新格式）；
    没有时回落到 sites + 全局 start_page/end_page（旧调用方/脚本兼容）。
    """
    site_pages = {}
    raw = data.get("site_pages")
    if isinstance(raw, dict):
        for key, rng in raw.items():
            if key not in SITE_NAMES or not isinstance(rng, dict):
                continue
            start = _clamp_page(rng.get("start"), 1)
            end = _clamp_page(rng.get("end"), start)
            site_pages[key] = (start, max(start, end))

    if not site_pages:
        start = _clamp_page(data.get("start_page"), 1)
        end = _clamp_page(data.get("end_page"), 10)
        end = max(start, end)
        for site in data.get("sites") or []:
            if site in SITE_NAMES:
                site_pages[site] = (start, end)

    return site_pages


@app.route("/api/start_crawl", methods=["POST"])
def api_start_crawl():
    if engine.running:
        return jsonify({"status": "error", "message": "已有任务在运行"})

    data = request.json or {}
    mode = data.get("mode", "by_page")
    if mode not in CRAWL_MODES:
        return jsonify({"status": "error", "message": f"未知的爬取模式: {mode}"})

    site_pages = _parse_site_pages(data)
    if not site_pages:
        return jsonify({"status": "error", "message": "请至少选择一个站点"})
    # 站点顺序按前端请求顺序，保证面板顺序稳定
    sites = list(site_pages.keys())

    speed_name = data.get("speed", "balanced")
    # 去重开关：仅按页码/按日期模式生效（增量模式本身就带去重）
    skip_existing = bool(data.get("skip_existing", False))

    # 速度档位白名单校验
    actual_speed = engine.set_speed(speed_name)

    log_store["logs"] = []
    progress_store.update({"current": 0, "total": 0, "success": 0, "skipped": 0, "error": 0})

    def run():
        if mode == "by_page":
            engine.crawl_by_page(site_pages, speed_name=actual_speed,
                                 skip_existing=skip_existing)
        elif mode == "by_date":
            start_date = data.get("start_date", "")
            end_date = data.get("end_date", "")
            engine.crawl_by_date(sites, start_date, end_date, speed_name=actual_speed,
                                 skip_existing=skip_existing)
        else:  # incremental
            engine.crawl_incremental(sites, speed_name=actual_speed)

    thread = threading.Thread(target=run, daemon=True)
    thread.start()

    return jsonify({"status": "ok", "speed": actual_speed})

@app.route("/api/confirm_cancel", methods=["POST"])
def api_confirm_cancel():
    """用户确认取消：discard=True 删数据，discard=False 保留数据"""
    data = request.json or {}
    discard = bool(data.get("discard", True))
    engine.auto_delete_on_cancel = discard
    engine.cancel()
    if discard:
        return jsonify({"status": "ok", "message": "已停止，将删除本次已爬数据"})
    return jsonify({"status": "ok", "message": "已停止，已保留本次爬取数据"})

@app.route("/api/stop_crawl", methods=["POST"])
def api_stop_crawl():
    engine.cancel()
    return jsonify({"status": "ok"})

@app.route("/api/progress")
def api_progress():
    # 站点独立状态（四站窗口）
    site_states = {}
    with engine._lock:
        for site_key, state in engine.site_states.items():
            site_states[site_key] = dict(state)
    # 每站最近日志：把站点名键转回site_key，与前端面板对齐
    name_to_key = engine._get_name_to_key()
    site_logs = {}
    with engine._lock:
        for site_key, logs in engine.site_logs.items():
            normalized_key = name_to_key.get(site_key, site_key)
            if normalized_key not in site_logs:
                site_logs[normalized_key] = []
            site_logs[normalized_key].extend(logs[-20:])
    return jsonify({
        "running": engine.running,
        "speed": engine.speed_name,
        **progress_store,
        "site_states": site_states,
        "site_logs": site_logs,
        "recent_logs": log_store["logs"][-50:],
    })

@app.route("/api/tasks")
def api_tasks():
    tasks = get_tasks()
    status_label = {
        "completed": "完成",
        "running": "运行中",
        "cancelled": "已取消",
        "failed": "失败",
        "interrupted": "已中断",
        "pending": "等待中",
    }
    for task in tasks:
        if task.get("status") in status_label:
            task["status_label"] = status_label[task["status"]]
        else:
            task["status_label"] = task.get("status", "")
    return jsonify(tasks)

@app.route("/api/delete_post", methods=["POST"])
def api_delete_post():
    data = request.json
    post_id = data.get("id")
    if post_id:
        _, source_ids = delete_posts_by_ids([int(post_id)])
        _remove_post_images(source_ids)
    return jsonify({"status": "ok"})

@app.route("/api/delete_task", methods=["POST"])
def api_delete_task():
    data = request.json or {}
    task_id = data.get("id")
    delete_posts_too = bool(data.get("delete_posts"))
    if task_id:
        source_ids = []
        if delete_posts_too:
            source_ids = delete_posts_by_task(int(task_id))
        delete_task(task_id)
        if source_ids:
            _remove_post_images(source_ids)
            log_callback("系统", f"任务{task_id}及其 {len(source_ids)} 条帖子已删除")
    return jsonify({"status": "ok"})

@app.route("/api/delete_and_recrawl", methods=["POST"])
def api_delete_and_recrawl():
    """删除某批次帖子数据，然后启动增量爬取重新爬取"""
    if engine.running:
        return jsonify({"status": "error", "message": "有任务正在运行，请先等待或取消当前任务"})

    data = request.json or {}
    task_id = data.get("id")
    sites_str = data.get("sites", "")
    if not task_id:
        return jsonify({"status": "error", "message": "缺少任务ID"})

    # 1. 删除该批次的帖子数据（含图片）
    source_ids = delete_posts_by_task(int(task_id))
    _remove_post_images(source_ids)

    # 2. 解析站点列表
    site_names = [s.strip() for s in sites_str.split(",") if s.strip()]
    site_keys = []
    name_to_key = engine._get_name_to_key()
    key_set = set(SITE_NAMES.keys())
    for name in site_names:
        # 优先直接作为 site_key 使用（历史记录存的就是 key）
        if name in key_set:
            site_keys.append(name)
        else:
            key = name_to_key.get(name)
            if key:
                site_keys.append(key)
    if not site_keys:
        return jsonify({"status": "error", "message": "未找到有效站点，请检查历史记录中的站点信息"})

    # 3. 启动增量爬取
    actual_speed = engine.set_speed(engine.speed_name)
    def do_crawl():
        try:
            engine.crawl_incremental(site_keys, speed_name=actual_speed)
        except Exception as e:
            engine._log("系统", f"重爬异常: {e}", "error")

    threading.Thread(target=do_crawl, daemon=True).start()
    return jsonify({"status": "ok", "deleted": len(source_ids)})

@app.route("/api/batch_delete", methods=["POST"])
def api_batch_delete():
    data = request.json
    ids = data.get("ids", [])
    # 类型安全：过滤非整数 id
    safe_ids = [int(x) for x in ids if isinstance(x, (int, str)) and str(x).isdigit()]
    source_ids = []
    if safe_ids:
        _, source_ids = delete_posts_by_ids(safe_ids)
        _remove_post_images(source_ids)
    return jsonify({"status": "ok", "deleted": len(safe_ids)})

@app.route("/api/redownload_images", methods=["POST"])
def api_redownload_images():
    """批量重新下载图片：带进度查询、取消、批量事务提交"""
    import json as _json
    from parser.image_handler import download_images

    if redownload_state["running"]:
        return jsonify({"status": "error", "message": "已有重新下载任务在运行"})

    # 重置状态
    redownload_state.update({
        "running": True,
        "cancelled": False,
        "total": 0,
        "current": 0,
        "updated": 0,
        "skipped": 0,
        "failed": 0,
        "started_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "finished_at": None,
        "error": None,
    })

    def run():
        try:
            proxy = config["proxy"]["http"] if config.get("proxy", {}).get("enabled") else None
            BATCH = 20  # 每批事务提交

            with get_conn() as conn:
                rows = conn.execute("SELECT id, source_id, images FROM posts").fetchall()
                redownload_state["total"] = len(rows)
                engine._log("系统", f"开始重新下载图片，共 {len(rows)} 条")

                pending = []  # 待更新列表 (post_id, new_images)
                for i, row in enumerate(rows):
                    if redownload_state["cancelled"]:
                        engine._log("系统", "重新下载被用户取消")
                        break

                    post_id = row["id"]
                    source_id = row["source_id"]
                    images_str = row["images"] or "[]"
                    try:
                        images = _json.loads(images_str)
                    except Exception:
                        images = []

                    if not images:
                        redownload_state["skipped"] += 1
                        redownload_state["current"] += 1
                        continue

                    needs_download = any(img.startswith("http") for img in images)
                    if not needs_download:
                        redownload_state["skipped"] += 1
                        redownload_state["current"] += 1
                        continue

                    local_images = download_images(images, source_id, proxy=proxy)
                    if local_images and any(img.startswith("images/") for img in local_images):
                        pending.append((post_id, _json.dumps(local_images)))
                        redownload_state["updated"] += 1
                    else:
                        redownload_state["failed"] += 1

                    redownload_state["current"] += 1

                    # 批量提交
                    if len(pending) >= BATCH:
                        conn.executemany("UPDATE posts SET images = ? WHERE id = ?", pending)
                        conn.commit()
                        pending.clear()

                    if (i + 1) % 50 == 0:
                        engine._log("系统",
                            f"进度 {i+1}/{len(rows)}, 已更新 {redownload_state['updated']}, 失败 {redownload_state['failed']}")

                # 收尾批次
                if pending:
                    conn.executemany("UPDATE posts SET images = ? WHERE id = ?", pending)
                    conn.commit()

            engine._log("系统",
                f"重新下载完成: 共 {redownload_state['total']} 条, 更新 {redownload_state['updated']}, 失败 {redownload_state['failed']}")
        except Exception as e:
            redownload_state["error"] = str(e)
            engine._log("系统", f"重新下载异常: {e}", "error")
        finally:
            redownload_state["finished_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
            redownload_state["running"] = False

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return jsonify({"status": "ok"})


@app.route("/api/redownload_status")
def api_redownload_status():
    """查询重新下载任务的实时进度"""
    return jsonify(dict(redownload_state))


@app.route("/api/cancel_redownload", methods=["POST"])
def api_cancel_redownload():
    """请求取消正在运行的重新下载任务（标记，下一轮循环检测）"""
    if not redownload_state["running"]:
        return jsonify({"status": "error", "message": "没有正在运行的任务"})
    redownload_state["cancelled"] = True
    return jsonify({"status": "ok"})

@app.route("/api/export")
def api_export():
    posts = get_posts(limit=get_post_count())
    result = export_posts(posts, name_suffix="全部来源")
    return jsonify({"status": "ok", "files": result})

@app.route("/api/cleanup_info")
def api_cleanup_info():
    """返回可清理项及可释放空间（字节）"""
    import shutil as _sh
    info = {"orphan_images": {"count": 0, "size": 0}, "export_leftovers": {"count": 0, "size": 0}, "empty_tasks": []}

    # 孤儿图片目录：库里无任何帖子引用的 source_id 目录
    with get_conn() as conn:
        db_sids = {r["source_id"] for r in conn.execute("SELECT DISTINCT source_id FROM posts").fetchall()}
    if IMAGES_DIR.exists():
        for d in IMAGES_DIR.iterdir():
            if d.is_dir() and d.name not in db_sids and not d.name.startswith("orphans-backup"):
                for root, _, files in os.walk(d):
                    for f in files:
                        try:
                            info["orphan_images"]["size"] += os.path.getsize(os.path.join(root, f))
                            info["orphan_images"]["count"] += 1
                        except OSError:
                            pass

    # 导出残留：output/ 里除最近10个zip外的全部zip+目录
    out_dir = Path(__file__).parent / "output"
    if out_dir.exists():
        zips = sorted((f for f in out_dir.glob("*.zip") if f.is_file()),
                      key=lambda p: p.stat().st_mtime, reverse=True)
        for old in zips[10:]:
            info["export_leftovers"]["count"] += 1
            try:
                info["export_leftovers"]["size"] += old.stat().st_size
            except OSError:
                pass
        keep_stems = {p.stem for p in zips[:10]}
        for d in out_dir.iterdir():
            if d.is_dir() and d.stem not in keep_stems:
                for root, _, files in os.walk(d):
                    for f in files:
                        try:
                            info["export_leftovers"]["size"] += os.path.getsize(os.path.join(root, f))
                        except OSError:
                            pass

    # 空任务：任务记录还在但 posts 里已无该批次数据
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT t.id, t.task_type, t.success_posts, t.sites, t.created_at
            FROM tasks t
            WHERE t.status IN ('completed', 'cancelled')
              AND NOT EXISTS (SELECT 1 FROM posts p WHERE p.crawl_id = t.id)
            ORDER BY t.id DESC
        """).fetchall()
        info["empty_tasks"] = [dict(r) for r in rows]

    return jsonify(info)


@app.route("/api/cleanup", methods=["POST"])
def api_cleanup():
    """执行清理：orphan_images / export_leftovers / empty_tasks（任选多项）"""
    import shutil as _sh
    targets = set((request.json or {}).get("targets", []))
    result = {}

    if "orphan_images" in targets:
        with get_conn() as conn:
            db_sids = {r["source_id"] for r in conn.execute("SELECT DISTINCT source_id FROM posts").fetchall()}
        removed = 0
        if IMAGES_DIR.exists():
            for d in IMAGES_DIR.iterdir():
                if d.is_dir() and d.name not in db_sids and not d.name.startswith("orphans-backup"):
                    try:
                        _sh.rmtree(d)
                        removed += 1
                    except Exception:
                        pass
        result["orphan_images_removed"] = removed

    if "export_leftovers" in targets:
        out_dir = Path(__file__).parent / "output"
        removed = 0
        if out_dir.exists():
            zips = sorted((f for f in out_dir.glob("*.zip") if f.is_file()),
                          key=lambda p: p.stat().st_mtime, reverse=True)
            for old in zips[10:]:
                try:
                    old.unlink()
                    removed += 1
                except Exception:
                    pass
            keep_stems = {p.stem for p in zips[:10]}
            for d in out_dir.iterdir():
                if d.is_dir() and d.stem not in keep_stems:
                    try:
                        _sh.rmtree(d)
                        removed += 1
                    except Exception:
                        pass
        result["export_leftovers_removed"] = removed

    if "empty_tasks" in targets:
        with get_conn() as conn:
            rows = conn.execute("""
                SELECT t.id FROM tasks t
                WHERE t.status IN ('completed', 'cancelled')
                  AND NOT EXISTS (SELECT 1 FROM posts p WHERE p.crawl_id = t.id)
            """).fetchall()
            ids = [r["id"] for r in rows]
            for tid in ids:
                delete_task(tid)
        result["empty_tasks_removed"] = len(ids)

    log_callback("系统", f"清理完成: {result}")
    return jsonify({"status": "ok", "result": result})


@app.route("/api/export_counts")
def api_export_counts():
    """返回各平台导出数量（PC / PC+安卓 / 安卓 三类互不重叠）"""
    pc = get_post_count(platform="pc")
    pc_android = get_post_count(platform="pc_android")
    android = get_post_count(platform="android")
    return jsonify({"pc": pc, "pc_android": pc_android, "android": android,
                    "mixed": pc_android})   # mixed 兼容旧前端

@app.route("/api/crawl_batches")
def api_crawl_batches():
    """获取所有爬取批次"""
    batches = get_crawl_batches()
    return jsonify({"batches": batches})

@app.route("/api/export_batch")
def api_export_batch():
    """按批次导出"""
    crawl_id = request.args.get("crawl_id", type=int)
    platform = request.args.get("platform", "all")
    
    if not crawl_id:
        return jsonify({"status": "error", "message": "缺少crawl_id"})
    
    posts = get_posts_by_crawl_id(crawl_id, platform)
    if not posts:
        return jsonify({"status": "error", "message": "该批次无数据"})

    sources = sorted({p.get("source", "") for p in posts if p.get("source")})
    tag = "-".join(sources) if sources else f"批次{crawl_id}"
    result = export_posts(posts, name_suffix=tag)
    
    # 根据平台选择文件
    if platform == "pc":
        filepath = result.get("pc", "")
    elif platform == "android":
        filepath = result.get("android", "")
    else:
        filepath = result.get("pc_android") or result.get("mixed") or ""
    
    if filepath:
        import os
        filename = os.path.basename(filepath)
        return send_file(filepath, as_attachment=True, download_name=filename)
    
    return jsonify({"status": "error", "message": "导出失败"})

@app.route("/api/export_download")
def api_export_download():
    """导出下载。type=all/pc/mixed/selected/filtered；
    source/platform/q 与结果页筛选同语义，实现"所见即所得"导出。"""
    export_type = request.args.get("type", "all")
    selected_ids = request.args.get("ids", "")
    source = request.args.get("source", "all")
    platform_filter = request.args.get("platform", "all")
    keyword = (request.args.get("q") or "").strip()

    if export_type == "selected" and selected_ids:
        id_list = [int(i) for i in selected_ids.split(",") if i.strip()]
        with get_conn() as conn:
            placeholders = ",".join("?" * len(id_list))
            rows = conn.execute(
                f"SELECT * FROM posts WHERE id IN ({placeholders}) ORDER BY id",
                id_list
            ).fetchall()
        posts = [dict(row) for row in rows]
    elif export_type == "filtered":
        # 按筛选条件一次性拉取全部匹配帖子，不分平台
        posts = _fetch_filtered_posts(source=source, keyword=keyword)
    else:
        # 与结果页一致的筛选条件（来源/平台/关键字）
        def count_filtered(plat=None):
            return _filtered_post_count(plat, source, keyword)

        def fetch_filtered(plat=None):
            return _fetch_filtered_posts(plat, source, keyword)

        if export_type == "pc":
            posts = fetch_filtered("pc")
        elif export_type == "mixed":
            # 只含同时支持 PC 与安卓的资源
            posts = fetch_filtered("pc_android")
        elif export_type == "android":
            # 单安卓（2026-09-23 起不再并入 PC+安卓）
            posts = fetch_filtered("android")
        else:
            posts = fetch_filtered()

    if export_type == "filtered":
        # 单zip：包含所有平台的筛选结果
        result = export_posts_filtered(posts, source=source)
        filepath = result.get("filtered", "")
    else:
        result = export_posts(posts, name_suffix=_export_tag(source, export_type))
        if export_type == "pc":
            filepath = result.get("pc", "")
        elif export_type == "android":
            filepath = result.get("android", "")
        else:
            filepath = result.get("pc_android") or result.get("mixed") or ""

    if filepath:
        import os
        filename = os.path.basename(filepath)
        return send_file(filepath, as_attachment=True, download_name=filename)

    return jsonify({"status": "error", "message": "无数据可导出"})

if __name__ == "__main__":
    flask_config = config.get("flask", {})
    app.run(
        host=flask_config.get("host", "127.0.0.1"),
        port=flask_config.get("port", 5000),
        debug=flask_config.get("debug", False),
        use_reloader=flask_config.get("debug", False),
    )
