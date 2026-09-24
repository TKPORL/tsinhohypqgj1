"""ACG图书馆爬虫"""
import json
import re
from pathlib import Path
from crawler.base import BaseCrawler
from parser import extract_links_multi, extract_links, extract_cloud_name, extract_cheat_code, fix_title_tags, fix_title_slash, fix_title_brackets, fix_title_cloud_name
from parser.image_handler import download_images

class ACGLLCrawler(BaseCrawler):
    """ACG图书馆爬虫"""

    def __init__(self, config):
        super().__init__(config)
        self.site_name = "ACG图书馆"
        self.base_url = "https://acgll.xyz"

    def get_list_page(self, page_num):
        url = f"{self.base_url}/category/youxi/page/{page_num}"
        soup = self._soup(url)
        results = []
        # ACG图书馆使用Zibll 8.8主题，帖子在 posts.posts-item 元素中
        for item in soup.select("posts.posts-item"):
            a = item.select_one("h2.item-heading > a")
            if a and a.get("href"):
                link = a["href"]
                if not link.startswith("http"):
                    link = self.base_url + link

                # 跳过置顶/公告帖
                title_text = a.get_text(strip=True)
                skip_keywords = ["教程", "模拟器", "工具", "必看", "合集"]
                if any(kw in title_text for kw in skip_keywords):
                    continue

                # 从标签提取平台信息
                category = ""
                tag_els = item.select(".item-meta a, .item-tag a, a[rel='tag']")
                for tag_el in tag_els:
                    tag_text = tag_el.get_text(strip=True).lower()
                    if tag_text in ("pc", "pc版", "windows"):
                        category = "PC"
                        break
                    elif tag_text in ("安卓", "android", "az"):
                        category = "AZ"
                        break

                results.append({"url": link, "category": category})
        return results

    def parse_detail(self, url, category=""):
        soup = self._soup(url)

        # 标题 - ACG图书馆使用 h1.article-title
        title_el = soup.select_one("h1.article-title")
        title = title_el.get_text(strip=True) if title_el else ""

        # 修复标题格式：【安卓/538M】→ 【安卓 538M】（斜杠换空格）
        title = re.sub(r'【(PC\+安卓|PC|安卓|android)/(\d+\.?\d*[GMgm][Bb]?)】', r'【\1 \2】', title)
        title = fix_title_slash(title)
        title = fix_title_tags(title)
        title = fix_title_brackets(title)

        # 内容 - ACG图书馆使用 div.wp-posts-content
        content_el = soup.select_one("div.wp-posts-content")
        content = content_el.get_text(separator="\n", strip=True) if content_el else ""

        # 提取图片
        images = []
        if content_el:
            for img in content_el.select("img"):
                src = img.get("data-src") or img.get("src") or ""
                if src and "loading" not in src and "avatar" not in src and "emoji" not in src:
                    if not src.startswith("http"):
                        src = self.base_url + src
                    images.append(src)

        # 提取点赞数
        likes = 0
        likes_el = soup.select_one(".content-footer-zan-cai .like-count, .meta-like")
        if likes_el:
            try:
                likes = int(re.sub(r'[^\d]', '', likes_el.get_text(strip=True)) or 0)
            except:
                pass

        # 提取发布日期
        post_date = ""
        # Zibll 主题：日期在 tooltip 的 title 属性里（title="2026年09月08日 13:40发布"）
        date_el = soup.select_one("[data-toggle='tooltip'][title*='发布']")
        if date_el:
            m = re.search(r'(\d{4})年(\d{2})月(\d{2})日', date_el.get("title", ""))
            if m:
                post_date = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"

        # 提取网盘链接
        links = extract_links_multi(content)
        if not links.get("baidu_link"):  # 移动云盘已下线，只认百度
            full_text = str(soup)
            links = extract_links_multi(full_text)

        # 提取下载名追加到标题
        cloud_name = extract_cloud_name(content)
        # 修正标题里的云名：把 PCC/AZC 前缀统一为 C
        title = fix_title_cloud_name(title)
        if cloud_name and cloud_name not in title:
            title = f"{title} 【{cloud_name}】"

        # 提取作弊码
        cheat_code = extract_cheat_code(title, content)

        # ACG图书馆没有解压码
        unzip_code = ""

        # 判断平台 - 优先从标题判断（标题比列表页分类更准确，与 acgyxj 对齐）
        platform = "unknown"
        category_lower = (category or "").lower()
        title_lower = title.lower()

        if "pc+安卓" in title_lower or "pc&安卓" in title_lower or "pc/安卓" in title_lower or ("pc" in title_lower and "安卓" in title_lower):
            platform = "pc_android"
        elif category_lower == "pc":
            platform = "pc"
        elif category_lower in ("az", "安卓", "android"):
            # 列表页分类为安卓，但标题里同时含 PC，按 pc_android 处理（标题优先）
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

        # 提取source_id
        source_id = url.split("/")[-1].replace(".html", "").split("?")[0]

        # 下载图片到本地（用source_id作为临时目录名）
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
            url = f"{self.base_url}/category/youxi"
            soup = self._soup(url)
            # ACG图书馆使用Zibll主题分页
            page_links = soup.select("div.pagenav a, a.page-numbers")
            max_page = 1
            for a in page_links:
                text = a.get_text(strip=True)
                if text.isdigit():
                    max_page = max(max_page, int(text))
            return max_page
        except:
            return 100
