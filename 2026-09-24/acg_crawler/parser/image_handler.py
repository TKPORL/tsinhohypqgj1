"""图片下载处理模块"""
import os
import re
import hashlib
import requests
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

IMAGES_DIR = Path(__file__).parent.parent / "images"

# 共享Session（连接池）
_session = None

def _get_session():
    """获取共享Session，支持连接池和自动重试"""
    global _session
    if _session is None:
        _session = requests.Session()
        retry = Retry(total=2, backoff_factor=0.5, status_forcelist=[500, 502, 503, 504])
        adapter = HTTPAdapter(max_retries=retry, pool_connections=20, pool_maxsize=20)
        _session.mount("http://", adapter)
        _session.mount("https://", adapter)
        _session.verify = False
        _session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "image/webp,image/apng,image/*,*/*;q=0.8",
        })
    return _session


def get_image_dir(post_id):
    """获取图片存储目录：images/{post_id}/"""
    dir_path = IMAGES_DIR / str(post_id)
    dir_path.mkdir(parents=True, exist_ok=True)
    return dir_path


def _url_hash(url):
    """URL的纯ASCII哈希"""
    return hashlib.md5(url.encode()).hexdigest()[:16]


def _guess_ext(url):
    """从URL猜扩展名"""
    lower = url.lower().split("?")[0]
    for ext in (".webp", ".png", ".gif", ".jpg", ".jpeg"):
        if lower.endswith(ext):
            return ext
    return ".jpg"


def download_image(url, post_id, proxy=None, timeout=10):
    """下载单张图片，成功返回本地相对路径，失败返回原始URL"""
    try:
        img_dir = get_image_dir(post_id)
        filename = _url_hash(url) + _guess_ext(url)
        local_path = img_dir / filename

        if local_path.exists():
            return f"images/{post_id}/{filename}"

        session = _get_session()
        headers = {"Referer": url}

        # 尝试方式1: 直连（优先，因为CDN通常可直连）
        try:
            resp = session.get(url, headers=headers, timeout=timeout, stream=True)
            resp.raise_for_status()
            data = resp.content
            if len(data) >= 500:
                with open(local_path, "wb") as f:
                    f.write(data)
                return f"images/{post_id}/{filename}"
        except Exception:
            pass

        # 尝试方式2: 通过代理
        if proxy:
            try:
                proxies = {"http": proxy, "https": proxy}
                resp = session.get(url, headers=headers, proxies=proxies, timeout=timeout, stream=True)
                resp.raise_for_status()
                data = resp.content
                if len(data) >= 500:
                    with open(local_path, "wb") as f:
                        f.write(data)
                    return f"images/{post_id}/{filename}"
            except Exception:
                pass

        # 尝试方式3: 直连 + 不同Referer
        try:
            resp = session.get(url, timeout=timeout, stream=True)
            resp.raise_for_status()
            data = resp.content
            if len(data) >= 500:
                with open(local_path, "wb") as f:
                    f.write(data)
                return f"images/{post_id}/{filename}"
        except Exception:
            pass

        return url

    except Exception:
        return url


def download_images(urls, post_id, proxy=None, max_workers=6):
    """批量下载图片，返回路径列表（本地相对路径或原始URL）"""
    results = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [
            executor.submit(download_image, url, post_id, proxy)
            for url in urls
        ]
        for future in futures:
            try:
                result = future.result(timeout=30)
                if result:
                    results.append(result)
            except Exception:
                pass
    return results


def img_src(path_or_url):
    """前端用：本地相对路径 → 绝对路径；远程URL原样返回"""
    if not path_or_url:
        return ""
    s = str(path_or_url)
    if s.startswith("images/"):
        return "/" + s
    return s
