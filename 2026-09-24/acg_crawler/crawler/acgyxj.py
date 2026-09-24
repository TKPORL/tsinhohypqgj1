"""ACG游戏姬爬虫"""
import json
import re
from pathlib import Path
from crawler.base import BaseCrawler
from parser import extract_links_multi, extract_links, extract_cloud_name, extract_cheat_code, fix_title_tags, fix_title_slash, fix_title_brackets, fix_title_cloud_name
from parser.image_handler import download_images

class ACGYXJCrawler(BaseCrawler):
    """ACG游戏姬爬虫"""

    def __init__(self, config):
        super().__init__(config)
        self.site_name = "ACG游戏姬"
        self.base_url = "https://www.acgyxjvip.com"
        self.alt_url = "https://www.acgyxjvip2.com"

    def _fetch(self, url):
        """先用主域名，失败则尝试备用域名"""
        try:
            return self._soup(url)
        except Exception:
            if self.alt_url and self.base_url in url:
                try:
                    return self._soup(url.replace(self.base_url, self.alt_url))
                except Exception:
                    return None
            return None

    def get_list_page(self, page_num):
        url = f"{self.base_url}/page/{page_num}"
        soup = self._fetch(url)
        if not soup:
            return []
        results = []
        for article in soup.select("article.post-list"):
            a = article.select_one("h3.post-title a")
            if a and a.get("href"):
                link = a["href"]
                if not link.startswith("http"):
                    link = self.base_url + link

                category = ""
                cat_el = article.select_one("div.category div.tags a")
                if cat_el:
                    category = cat_el.get_text(strip=True)

                # 跳过置顶/公告帖
                title_text = a.get_text(strip=True)
                skip_keywords = ["MTool", "喵笔记", "教程", "工具", "模拟器", "必看"]
                if any(kw in title_text for kw in skip_keywords):
                    continue

                results.append({"url": link, "category": category})
        return results

    def _format_title(self, title, category=""):
        """格式化标题：[新作/类型/标签] 游戏名 [PC+安卓 大小] [C码]"""
        if not title:
            return title

        # 保存原始标题用于平台检测
        orig_title = title

        # 先提取标签前缀 [新作/...] 或直接 新作...
        prefix = ""
        m = re.match(r'^(新作|更新|汉化|原创)\s*', title)
        if m:
            prefix = m.group(1)
            title = title[m.end():]

        tags = ""
        m = re.match(r'[\[【]([^]】]+)[\]】]', title)
        if m:
            tags = m.group(1)
            title = title[m.end():].strip()

        # 提取云名 [PCC155555] 等
        code = ""
        m = re.search(r'\s*[\[【]([A-Za-z]*\d{5,})[\]】]\s*$', title)
        if m:
            code = m.group(1)
            title = title[:m.start()].strip()

        # 提取大小 - 处理已有的 [平台/大小] 格式（如 [PC+安卓/1.70G]、[PC/9G]）
        size = ""
        # 匹配 [PC+安卓/1.70G] 或 [安卓/889M] 等整体模式
        m = re.search(r'\s*[\[【](PC\+安卓|PC|安卓|android)[/\s](\d+\.?\d*\s*[GMgm][Bb]?)[\]】]', title, re.IGNORECASE)
        if m:
            size = m.group(2)
            title = title[:m.start()].strip()
        else:
            # 匹配独立的 [大小] 或纯大小
            m = re.search(r'(?:[\[【])?(\d+\.?\d*\s*[GMgm][Bb]?)(?:[\]】])?\s*$', title)
            if m:
                size = m.group(1)
                title = title[:m.start()].strip()

        # 清理残留的半截括号（如 [PC+安卓/ 被提取后留下的）
        title = re.sub(r'\s*[\[【]\s*$', '', title).strip()

        # 判断平台类型（基于原始标题，包含所有信息）
        all_text = (prefix + " " + tags + " " + orig_title).upper()
        has_android = "安卓" in all_text or "ANDROID" in all_text
        has_pc = "PC" in all_text

        parts = []
        if prefix or tags:
            tag_str = "/".join(filter(None, [prefix, tags]))
            parts.append(f"【{tag_str}】")
        parts.append(title)
        if size:
            if has_android and has_pc:
                plat = "PC+安卓"
            elif has_android:
                plat = ""
            else:
                plat = "PC"
            parts.append(f"【{plat} {size}】".strip() if plat else f"【{size}】")
        if code:
            # 云名去除平台前缀（如 PCC148222 → C148222）
            clean_code = re.sub(r'^(PC|pc|Pc)', '', code)
            parts.append(f"【{clean_code}】")

        result = " ".join(parts)
        return result if result.strip() else title

    def parse_detail(self, url, category=""):
        soup = self._fetch(url)
        if not soup:
            return None

        title_el = soup.select_one("h1")
        title = title_el.get_text(strip=True) if title_el else ""
        title = self._format_title(title, category)
        title = fix_title_slash(title)
        title = fix_title_tags(title)
        title = fix_title_brackets(title)

        content_el = soup.select_one("div.single-content")
        content = content_el.get_text(separator="\n", strip=True) if content_el else ""

        images = []
        if content_el:
            for img in content_el.select("img"):
                src = img.get("data-src") or img.get("src") or ""
                if src and "loading" not in src and "avatar" not in src and "emoji" not in src and "cravatar" not in src:
                    if not src.startswith("http"):
                        src = self.base_url + src
                    images.append(src)

        likes = 0

        # 点赞 - span.like-count
        likes_el = soup.select_one("span.like-count")
        if likes_el:
            try:
                likes = int(re.sub(r'[^\d]', '', likes_el.get_text(strip=True)) or 0)
            except:
                pass

        post_date = ""
        # 游戏姬详情页的 time 元素无 class，直接取第一个带 datetime 的
        date_el = soup.select_one("time[datetime]")
        if date_el:
            post_date = date_el.get("datetime", "")[:10]

        links = extract_links_multi(content)
        if not links.get("baidu_link") and not links.get("mobile_link"):
            full_text = str(soup)
            links = extract_links_multi(full_text)

        cloud_name = extract_cloud_name(content)
        # 修正标题里的云名：把 PCC/AZC 前缀统一为 C
        title = fix_title_cloud_name(title)
        if cloud_name and cloud_name not in title:
            title = f"{title} 【{cloud_name}】"

        cheat_code = extract_cheat_code(title, content)

        unzip_code = ""

        platform = "unknown"
        title_lower = title.lower()
        category_lower = (category or "").lower()

        # 优先从标题判断（标题比分类更准确）
        if "pc+安卓" in title_lower or "pc&安卓" in title_lower or "pc/安卓" in title_lower or ("pc" in title_lower and "安卓" in title_lower):
            platform = "pc_android"
        elif category_lower == "pc":
            platform = "pc"
        elif category_lower in ("az", "安卓", "android"):
            # ACG游戏姬分类标安卓的，标题里有PC就归为pc_android
            if "pc" in title_lower:
                platform = "pc_android"
            else:
                platform = "android"
        elif "安卓" in title_lower:
            if "pc" in title_lower:
                platform = "pc_android"
            else:
                platform = "android"
        elif "pc" in title_lower or "steam" in title_lower:
            platform = "pc"

        source_id = url.split("/")[-1].replace(".html", "")

        proxy = None
        if self.config.get("proxy", {}).get("enabled"):
            proxy = self.config["proxy"]["http"]
        import json as _json_dl
        local_images = download_images(images, source_id, proxy=proxy)
        if local_images:
            images = local_images

        return {
            "source": self.site_name,
            "source_id": source_id,
            "source_url": url,
            "title": title,
            "platform": platform,
            "content": content[:5000],
            "download_items_json": _json_dl.dumps(links.get("items", []), ensure_ascii=False),
            "likes": likes,
            "comments": 0,
            "views": 0,
            "unzip_code": unzip_code,
            "cheat_code": cheat_code,
            "baidu_link": links.get("baidu_link"),
            "baidu_code": links.get("baidu_code"),
            "mobile_link": links.get("mobile_link"),
            "mobile_code": links.get("mobile_code"),
            "images": json.dumps(images),
            "original_images": json.dumps(images),
            "post_date": post_date,
        }

    def get_total_pages(self):
        try:
            soup = self._fetch(self.base_url)
            if not soup:
                return 10
            page_links = soup.select("ul.pagination li a.page-link")
            max_page = 1
            for a in page_links:
                text = a.get_text(strip=True)
                if text.isdigit():
                    max_page = max(max_page, int(text))
            return max_page
        except:
            return 10
