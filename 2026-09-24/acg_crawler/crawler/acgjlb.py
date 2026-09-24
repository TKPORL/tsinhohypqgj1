"""ACG俱乐部爬虫"""
import json
import re
from pathlib import Path
from crawler.base import BaseCrawler
from parser import extract_links_multi, extract_links, extract_cloud_name, extract_cheat_code, fix_title_tags, fix_title_slash, fix_title_brackets, fix_title_cloud_name
from parser.image_handler import download_images

class ACGJLBCrawler(BaseCrawler):
    """ACG俱乐部爬虫"""

    def __init__(self, config):
        super().__init__(config)
        self.site_name = "ACG俱乐部"
        self.base_url = "https://www.acgjlb.cc"

    def get_list_page(self, page_num):
        # 该站使用 /page/N 路径分页，?page=N 实际仍返回第一页
        url = (f"{self.base_url}/acggame" if page_num == 1
               else f"{self.base_url}/acggame/page/{page_num}")
        soup = self._soup(url)
        results = []
        # ACG俱乐部使用Zibll主题，帖子在 div.item-body 容器中
        for item in soup.select("div.item-body"):
            a = item.select_one("h2.item-heading > a")
            if not a or not a.get("href"):
                continue

            link = a["href"]
            if not link.startswith("http"):
                link = self.base_url + link

            # 只保留数字ID的帖子（如 /86396.html），跳过置顶/分类帖
            if not re.search(r'/\d+\.html', link):
                continue

            # 跳过置顶帖子（标题以特定关键词开头）
            title_text = a.get_text(strip=True)
            skip_keywords = ["本站专用", "教程", "模拟器", "合集", "TOP", "解压", "冷月白狐", "必看"]
            if any(kw in title_text for kw in skip_keywords):
                continue

            # 从标签提取平台信息
            category = ""
            tag_els = item.select(".item-tags a, a[rel='tag']")
            for tag_el in tag_els:
                tag_text = tag_el.get_text(strip=True).lower()
                if tag_text in ("pc", "pc版", "windows"):
                    category = "PC"
                    break
                elif tag_text in ("安卓", "android", "az"):
                    category = "AZ"
                    break

            results.append({"url": link, "category": category})

        # 备用选择器：直接找数字ID链接
        if not results:
            for a in soup.select("a[href]"):
                href = a.get("href", "")
                if re.search(r'/\d+\.html$', href):
                    link = href if href.startswith("http") else self.base_url + href
                    if not any(r["url"] == link for r in results):
                        results.append({"url": link, "category": ""})

        return results

    def parse_detail(self, url, category=""):
        soup = self._soup(url)

        # 标题 - ACG俱乐部使用 h1.article-title
        title_el = soup.select_one("h1.article-title")
        title = title_el.get_text(strip=True) if title_el else ""

        # 标题开头的数字移到末尾（如 16495[RPG/...] → [RPG/...] 16495）
        title_match = re.match(r'^(\d{4,6})([\[【].+)', title)
        if title_match:
            num = title_match.group(1)
            rest = title_match.group(2)
            title = f"{rest} {num}"

        # 标题末尾]后面的数字移到标题区后面（如 ...joi]5286 1648 → ...joi] 5286 1648）
        end_match = re.search(r'[]】](\d[\d\s]*\d)\s*$', title)
        if end_match:
            nums = end_match.group(1).strip()
            title = title[:end_match.start(1)].rstrip() + " " + nums

        # 修复标题：【PC+安卓/9.35G/更新】→ 【PC+安卓 9.35G】，更新移到开头标签
        def fix_size_bracket(m):
            platform = m.group(1)
            size = m.group(2)
            extra = m.group(3) or ""
            # 额外信息（如更新）移到标题其他位置，在这里先存着
            return f'【{platform} {size}】'
        
        # 提取【】里的额外信息
        size_match = re.search(r'【([^】]*(?:PC|安卓)[^】]*?)】', title)
        if size_match:
            bracket_content = size_match.group(1)
            # 把/换成空格，提取出平台和大小
            parts = bracket_content.split('/')
            platform_size = []
            extra_tags = []
            for p in parts:
                p = p.strip()
                if re.match(r'^[\d\.]+[GMgm]', p):
                    platform_size.append(p)
                elif p in ('PC', '安卓', 'PC+安卓', 'android'):
                    platform_size.append(p)
                elif p in ('更新', '汉化', '官中'):
                    extra_tags.append(p)
                else:
                    platform_size.append(p)
            
            if extra_tags:
                # 把"更新"等移到开头的[]标签里
                tag_match = re.match(r'([【\[][^\]】]+[】\]])', title)
                if tag_match:
                    tag_content = tag_match.group(1)
                    for tag in extra_tags:
                        if tag not in tag_content:
                            # 统一用】结尾
                            tag_content = tag_content.rstrip('】]') + '/' + tag + '】'
                    title = tag_content + title[tag_match.end():]
                
                # 重建【】内容（只保留平台和大小）
                new_bracket = '【' + ' '.join(platform_size) + '】'
                title = title[:size_match.start()] + new_bracket + title[size_match.end():]
        
        # 修复斜杠：【PC+安卓/9.35G】→【PC+安卓 9.35G】
        title = re.sub(r'【(PC\+安卓|PC|安卓)/(\d+\.?\d*[GMgm][Bb]?)】', r'【\1 \2】', title)
        title = fix_title_slash(title)
        title = fix_title_tags(title)
        title = fix_title_brackets(title)

        # 内容 - ACG俱乐部使用 div.wp-posts-content
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
        # Zibll 主题：日期在 tooltip 的 title 属性里（title="2026年09月11日 02:59发布"）
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

        # 提取解压码（ACG俱乐部固定为007721）
        unzip_code = "007721"

        # 判断平台 - 优先从分类标签判断，正文标签兜底
        platform = "unknown"
        category_lower = (category or "").lower()
        title_lower = title.lower()
        content_lower = content.lower()

        if category_lower == "pc":
            platform = "pc"
        elif category_lower in ("az", "安卓", "android"):
            platform = "android"
        elif "pc+安卓" in title_lower or "pc&安卓" in title_lower or "pc/安卓" in title_lower:
            platform = "pc_android"
        elif "安卓" in title_lower:
            platform = "android"
        elif "pc" in title_lower or "steam" in title_lower:
            platform = "pc"
        else:
            # 兜底：正文中的平台标签（如 #PC #安卓）
            has_pc = "pc" in content_lower or "windows" in content_lower
            has_az = "安卓" in content_lower or "android" in content_lower
            if has_pc and has_az:
                platform = "pc_android"
            elif has_az:
                platform = "android"
            elif has_pc:
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
            url = f"{self.base_url}/acggame"
            soup = self._soup(url)
            # ACG俱乐部使用Zibll主题分页
            page_links = soup.select("div.pagenav a, a[href*='/page/'], a[href*='page=']")
            max_page = 1
            for a in page_links:
                href = a.get("href", "")
                match = re.search(r'(?:/page/|[?&]page=)(\d+)', href)
                if match:
                    max_page = max(max_page, int(match.group(1)))
            return max_page
        except:
            return 100
