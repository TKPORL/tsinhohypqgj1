"""数据库模块"""
import sqlite3
import threading
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from contextlib import contextmanager

DB_PATH = Path(__file__).parent.parent / "data" / "crawler.db"
DB_BUSY_TIMEOUT_MS = 10000
DB_WRITE_RETRIES = 5
_WRITE_LOCK = threading.RLock()

# 结果排序口径（2026-09-23 用户确认）：点赞降序 → id 倒序。
# 旧口径是「双网盘置顶 → 组内点赞降序」，会让导出 HTML 到第 N 张时突然从高赞重新开始，
# 看着像排序坏了，故取消双网盘优先（is_dual_netdisk 仅保留作展示判定，不参与排序）。
POST_ORDER_SQL = "ORDER BY COALESCE(likes, 0) DESC, id DESC"


def is_dual_netdisk(post):
    """Python 侧判定：百度 + 移动云盘链接都有（现仅用于展示，不参与排序）"""
    return bool(post.get("baidu_link")) and bool(post.get("mobile_link"))


def sort_posts(posts):
    """按「点赞降序 → id 倒序」排序，与 POST_ORDER_SQL 保持一致。
    导出等 Python 侧路径统一走这里，避免和 SQL 排序口径不一致。
    """
    return sorted(posts, key=lambda p: (
        -int(p.get("likes") or 0),
        -int(p.get("id") or 0),
    ))

def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with get_conn() as conn:
        # 兼容迁移：旧库可能缺 crawl_id / download_items_json
        try:
            conn.execute("SELECT crawl_id FROM posts LIMIT 1")
        except Exception:
            conn.execute("ALTER TABLE posts ADD COLUMN crawl_id INTEGER")

        try:
            conn.execute("SELECT download_items_json FROM posts LIMIT 1")
        except Exception:
            conn.execute("ALTER TABLE posts ADD COLUMN download_items_json TEXT")
        
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL,
                source_id TEXT NOT NULL,
                source_url TEXT NOT NULL,
                title TEXT NOT NULL,
                platform TEXT DEFAULT 'unknown',
                content TEXT,
                likes INTEGER DEFAULT 0,
                comments INTEGER DEFAULT 0,
                views INTEGER DEFAULT 0,
                unzip_code TEXT,
                cheat_code TEXT,
                baidu_link TEXT,
                baidu_code TEXT,
                mobile_link TEXT,
                mobile_code TEXT,
                images TEXT,
                original_images TEXT,
                crawled_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                post_date TEXT,
                crawl_id INTEGER,
                download_items_json TEXT,
                UNIQUE(source, source_id)
            );

            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_type TEXT NOT NULL,
                params TEXT NOT NULL,
                status TEXT DEFAULT 'pending',
                sites TEXT,
                total_posts INTEGER DEFAULT 0,
                success_posts INTEGER DEFAULT 0,
                skipped_posts INTEGER DEFAULT 0,
                error_posts INTEGER DEFAULT 0,
                started_at TIMESTAMP,
                finished_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_posts_source ON posts(source);
            CREATE INDEX IF NOT EXISTS idx_posts_platform ON posts(platform);
            CREATE INDEX IF NOT EXISTS idx_posts_date ON posts(post_date);
            CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
            CREATE INDEX IF NOT EXISTS idx_posts_crawl_id ON posts(crawl_id);
            CREATE INDEX IF NOT EXISTS idx_posts_source_url ON posts(source_url);
        """)

@contextmanager
def get_conn():
    conn = sqlite3.connect(
        str(DB_PATH),
        timeout=DB_BUSY_TIMEOUT_MS / 1000,
        check_same_thread=False,
    )
    conn.row_factory = sqlite3.Row
    conn.execute(f"PRAGMA busy_timeout = {DB_BUSY_TIMEOUT_MS}")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    try:
        yield conn
        for attempt in range(DB_WRITE_RETRIES):
            try:
                with _WRITE_LOCK:
                    conn.commit()
                break
            except sqlite3.OperationalError as exc:
                if "locked" not in str(exc).lower() or attempt == DB_WRITE_RETRIES - 1:
                    raise
                time.sleep(0.05 * (2 ** attempt))
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def insert_post(post_data):
    # 使用本地时间（UTC+8）
    local_now = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S")
    with get_conn() as conn:
        conn.execute("""
            INSERT OR REPLACE INTO posts
            (source, source_id, source_url, title, platform, content,
             likes, comments, views, unzip_code, cheat_code,
             baidu_link, baidu_code, mobile_link, mobile_code,
             images, original_images, post_date, crawled_at, crawl_id,
             download_items_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            post_data.get("source"),
            post_data.get("source_id"),
            post_data.get("source_url"),
            post_data.get("title"),
            post_data.get("platform", "unknown"),
            post_data.get("content"),
            post_data.get("likes", 0),
            post_data.get("comments", 0),
            post_data.get("views", 0),
            post_data.get("unzip_code"),
            post_data.get("cheat_code"),
            post_data.get("baidu_link"),
            post_data.get("baidu_code"),
            post_data.get("mobile_link"),
            post_data.get("mobile_code"),
            post_data.get("images"),
            post_data.get("original_images"),
            post_data.get("post_date"),
            local_now,
            post_data.get("crawl_id"),
            post_data.get("download_items_json"),
        ))

def get_posts(platform=None, source=None, limit=100, offset=0):
    with get_conn() as conn:
        query = "SELECT * FROM posts WHERE 1=1"
        params = []
        if platform and platform != "all":
            if platform == "pc":
                query += " AND (platform = 'pc' OR platform = 'unknown')"
            elif platform == "pc_android":
                # PC+安卓：只含同时支持两者的资源，单安卓另立一类（用户 2026-09-23 要求）
                query += " AND platform = 'pc_android'"
            elif platform == "android":
                query += " AND platform = 'android'"
            else:
                query += " AND platform = ?"
                params.append(platform)
        if source and source != "all":
            query += " AND source = ?"
            params.append(source)
        query += f" {POST_ORDER_SQL} LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        return [dict(row) for row in conn.execute(query, params).fetchall()]

def get_post_count(platform=None, source=None):
    with get_conn() as conn:
        query = "SELECT COUNT(*) FROM posts WHERE 1=1"
        params = []
        if platform and platform != "all":
            if platform == "pc":
                query += " AND (platform = 'pc' OR platform = 'unknown')"
            elif platform == "pc_android":
                # PC+安卓：只含同时支持两者的资源，单安卓另立一类（用户 2026-09-23 要求）
                query += " AND platform = 'pc_android'"
            elif platform == "android":
                query += " AND platform = 'android'"
            else:
                query += " AND platform = ?"
                params.append(platform)
        if source and source != "all":
            query += " AND source = ?"
            params.append(source)
        return conn.execute(query, params).fetchone()[0]

def delete_post(post_id):
    with get_conn() as conn:
        conn.execute("DELETE FROM posts WHERE id = ?", (post_id,))

def delete_task(task_id):
    with get_conn() as conn:
        conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))

def create_task(task_type, params, sites):
    with get_conn() as conn:
        cursor = conn.execute(
            "INSERT INTO tasks (task_type, params, sites) VALUES (?, ?, ?)",
            (task_type, params, sites)
        )
        return cursor.lastrowid

def update_task(task_id, **kwargs):
    if not kwargs:
        return
    allowed_fields = {
        "status", "started_at", "finished_at",
        "success_posts", "skipped_posts", "error_posts"
    }
    invalid_fields = set(kwargs) - allowed_fields
    if invalid_fields:
        raise ValueError(f"不允许更新任务字段: {', '.join(sorted(invalid_fields))}")
    with get_conn() as conn:
        sets = ", ".join(f"{key} = ?" for key in kwargs)
        values = list(kwargs.values()) + [task_id]
        conn.execute(f"UPDATE tasks SET {sets} WHERE id = ?", values)

def recover_interrupted_tasks():
    """应用启动时将上次异常退出遗留的运行中任务标记为已中断。"""
    finished_at = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S")
    with get_conn() as conn:
        cursor = conn.execute(
            """
            UPDATE tasks
            SET status = 'interrupted', finished_at = ?
            WHERE status = 'running'
            """,
            (finished_at,),
        )
        return cursor.rowcount

def get_tasks(limit=20):
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT t.*, EXISTS(SELECT 1 FROM posts p WHERE p.crawl_id = t.id) AS has_posts
            FROM tasks t ORDER BY t.id DESC LIMIT ?
        """, (limit,)).fetchall()
        return [dict(r) for r in rows]

def get_task(task_id):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        return dict(row) if row else None

def get_crawl_batches():
    """获取所有爬取批次，按时间倒序"""
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT crawl_id, 
                   MIN(crawled_at) as crawl_time,
                   COUNT(*) as post_count,
                   SUM(CASE WHEN platform='pc' THEN 1 ELSE 0 END) as pc_count,
                   SUM(CASE WHEN platform IN ('pc_android','android') THEN 1 ELSE 0 END) as android_count
            FROM posts 
            WHERE crawl_id IS NOT NULL
            GROUP BY crawl_id
            ORDER BY crawl_id DESC
        """).fetchall()
        return [dict(row) for row in rows]

def get_posts_by_crawl_id(crawl_id, platform=None):
    """按爬取批次获取帖子"""
    with get_conn() as conn:
        query = "SELECT * FROM posts WHERE crawl_id = ?"
        params = [crawl_id]
        if platform and platform != "all":
            if platform == "pc":
                query += " AND (platform = 'pc' OR platform = 'unknown')"
            elif platform == "pc_android":
                query += " AND platform = 'pc_android'"
            elif platform == "android":
                query += " AND platform = 'android'"
        query += " " + POST_ORDER_SQL
        return [dict(row) for row in conn.execute(query, params).fetchall()]

def get_batch_post_count(crawl_id, platform=None):
    """获取某批次的帖子数量"""
    with get_conn() as conn:
        query = "SELECT COUNT(*) FROM posts WHERE crawl_id = ?"
        params = [crawl_id]
        if platform and platform != "all":
            if platform == "pc":
                query += " AND (platform = 'pc' OR platform = 'unknown')"
            elif platform == "pc_android":
                query += " AND platform = 'pc_android'"
            elif platform == "android":
                query += " AND platform = 'android'"
        return conn.execute(query, params).fetchone()[0]


def delete_posts_by_ids(post_ids):
    """批量删除帖子。返回删除数量与对应 source_id 列表（供图片清理）。"""
    if not post_ids:
        return 0, []
    with get_conn() as conn:
        placeholders = ",".join("?" * len(post_ids))
        rows = conn.execute(
            f"SELECT source_id FROM posts WHERE id IN ({placeholders})", post_ids
        ).fetchall()
        conn.execute(f"DELETE FROM posts WHERE id IN ({placeholders})", post_ids)
    return len(rows), [r["source_id"] for r in rows]


def get_shared_source_ids(source_ids):
    """查询这些 source_id 中仍被 posts 表引用的集合。

    不同站点的帖子 ID 均为纯数字，图片目录按 source_id 命名时会撞车；
    删除图片目录前用它做共享保护。
    """
    if not source_ids:
        return set()
    with get_conn() as conn:
        placeholders = ",".join("?" * len(source_ids))
        rows = conn.execute(
            f"SELECT DISTINCT source_id FROM posts WHERE source_id IN ({placeholders})",
            [str(s) for s in source_ids],
        ).fetchall()
    return {r["source_id"] for r in rows}


def delete_posts_by_task(task_id):
    """删除某次任务批次爬取的全部帖子，返回 source_id 列表（供图片清理）。"""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT source_id FROM posts WHERE crawl_id = ?", (task_id,)
        ).fetchall()
        conn.execute("DELETE FROM posts WHERE crawl_id = ?", (task_id,))
    return [r["source_id"] for r in rows]
