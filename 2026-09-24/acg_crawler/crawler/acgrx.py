"""萌幻ACG爬虫"""
import json
import re
from pathlib import Path
from urllib.parse import urljoin
from crawler.base import BaseCrawler
from parser import extract_links_multi, extract_links, extract_cloud_name, extract_cheat_code, fix_title_tags, fix_title_slash, fix_title_brackets, fix_title_cloud_name
from parser.image_handler import download_images

class ACGRXCrawler(BaseCrawler):
    """萌幻ACG爬虫"""

    def __init__(self, config):
        super().__init__(config)
        self.site_name = "萌幻ACG"
        self.base_url = "https://bbs4.acgrx.com"
        self.logged_in = False
        self._login()

    def _soup(self, url):
        """带登录态自愈的页面获取：详情页被踢回登录页时自动重登一次再取"""
        soup = super()._soup(url)
        if "login.php" not in url and soup.select_one("form[name='login']") is not None:
            print(f"[{self.site_name}] 检测到登录页，cookie 可能失效，尝试重新登录")
            self.logged_in = False
            self._login()
            if self.logged_in:
                soup = super()._soup(url)
        return soup

    def _login(self):
        """自动登录"""
        try:
            login_page_url = f"{self.base_url}/adminacgrx/login.php"
            soup = self._soup(login_page_url)

            # 查找登录表单
            form = soup.select_one("form[name='login']")
            if not form:
                print(f"[{self.site_name}] 未找到登录表单")
                return

            # 获取action URL（含CSRF token）；相对路径转绝对，避免 POST 打到错误地址
            action = form.get("action", "")
            if not action:
                print(f"[{self.site_name}] 未找到登录action")
                return
            if not action.startswith("http"):
                action = urljoin(f"{self.base_url}/adminacgrx/login.php", action)

            email = self.config.get("acgrx", {}).get("email", "")
            password = self.config.get("acgrx", {}).get("password", "")

            if not email or not password:
                print(f"[{self.site_name}] 未配置登录凭据")
                return

            # 登录 - 使用完整的headers模拟浏览器
            self.session.headers.update({
                "Referer": login_page_url,
                "Origin": self.base_url,
            })

            login_data = {
                "name": email,
                "password": password,
                "remember": "1",
                "referer": "",
            }

            resp = self.session.post(
                action,
                data=login_data,
                timeout=15,
                allow_redirects=True
            )

            # 检查登录是否成功：查看cookie中是否有typecho_uid
            if any("typecho_uid" in c.name for c in self.session.cookies):
                self.logged_in = True
                print(f"[{self.site_name}] 登录成功")
            elif "logout" in resp.text:
                self.logged_in = True
                print(f"[{self.site_name}] 登录成功")
            else:
                print(f"[{self.site_name}] 登录可能失败")

        except Exception as e:
            print(f"[{self.site_name}] 登录出错: {e}")

    def get_list_page(self, page_num):
        if page_num == 1:
            url = self.base_url
        else:
            url = f"{self.base_url}/page/{page_num}"
        soup = self._soup(url)
        results = []
        for item in soup.select("div.post-item"):
            a = item.select_one("a.post-title")
            if not a or not a.get("href"):
                continue

            link = a["href"]
            if not link.startswith("http"):
                link = self.base_url + link

            # 过滤掉广告链接
            if "/go/" in link:
                continue

            # 只保留游戏分类帖子
            cate_el = item.select_one("span.post-cate a")
            category = cate_el.get_text(strip=True) if cate_el else ""
            if category != "游戏":
                continue

            # 从标签提取平台信息
            platform_tag = ""
            for tag_el in item.select("span[class^='article-categories'] a"):
                tag_text = tag_el.get_text(strip=True)
                if tag_text in ("PC",):
                    platform_tag = "PC"
                    break
                elif tag_text in ("安卓",):
                    platform_tag = "AZ"
                    break

            results.append({"url": link, "category": platform_tag})
        return results

    def parse_detail(self, url, category=""):
        soup = self._soup(url)

        # 标题
        title_el = soup.select_one("div.post-contentr h1")
        title = title_el.get_text(strip=True) if title_el else ""

        # 修复标题：如果【大小】里没有平台，自动从标签里提取添加
        # 【ADV/PC/汉化】游戏名【12.53GB】→ 【ADV/PC/汉化】游戏名【PC 12.53GB】
        m = re.search(r'【(\d+\.?\d*GB?)】', title)
        if m:
            size_text = m.group(1)
            # 检查标签里有没有平台
            tags_part = title[:m.start()]
            if 'PC' in tags_part or 'pc' in tags_part:
                new_size = f'【PC {size_text}】'
            elif '安卓' in tags_part or 'Android' in tags_part or 'AZ' in tags_part:
                new_size = f'【安卓 {size_text}】'
            else:
                new_size = f'【PC {size_text}】'  # 默认PC
            title = title[:m.start()] + new_size + title[m.end():]

        # 修复斜杠：【PC/1.08GB】→【PC 1.08GB】
        title = re.sub(r'【(PC\+安卓|PC|安卓)/(\d+\.?\d*[GMgm][Bb]?[Bb]?)】', r'【\1 \2】', title)
        title = fix_title_slash(title)
        title = fix_title_tags(title)
        title = fix_title_brackets(title)

        # 内容
        content_el = soup.select_one("div.post-contentr")
        content = ""
        if content_el:
            # 获取所有文本内容
            content = content_el.get_text(separator="\n", strip=True)

        # 提取图片
        images = []
        if content_el:
            for img in content_el.select("img"):
                src = img.get("data-original") or img.get("data-src") or img.get("src") or ""
                if src and "loading" not in src and "avatar" not in src and "emoji" not in src:
                    if not src.startswith("http"):
                        src = self.base_url + src
                    images.append(src)

        # 提取互动数据 (萌幻ACG没有互动数据)
        likes = 0
        comments = 0
        views = 0

        # 提取发布日期
        post_date = ""
        date_el = soup.select_one("div.post-contentr time[datetime]")
        if date_el:
            post_date = date_el.get("datetime", "")[:10]

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

        # 提取解压码 - 从内容中提取（如 "解压密码：xxx" 或 "密码：xxx"）
        unzip_code = ""
        unzip_patterns = [
            r'(?:解压密码|统一解压密码|解压码|密码)[：:\s]*(\S+)',
        ]
        for pat in unzip_patterns:
            m = re.search(pat, content)
            if m:
                code = m.group(1).strip()
                # 过滤掉明显不是解压码的内容
                if len(code) >= 3 and not code.startswith("http") and "使用" not in code:
                    unzip_code = code
                    break

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
        source_id = url.split("/")[-1].replace(".html", "")

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
            "likes": 0,
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
            soup = self._soup(self.base_url)
            page_links = soup.select("div.pagination a, a[href*='/page/']")
            max_page = 1
            for a in page_links:
                href = a.get("href", "")
                match = re.search(r'/page/(\d+)', href)
                if match:
                    max_page = max(max_page, int(match.group(1)))
            return max_page
        except:
            return 100
