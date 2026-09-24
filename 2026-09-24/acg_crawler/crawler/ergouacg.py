"""二狗ACG（2gouacg.com）爬虫

WordPress 站（TouchGal 风格主题），四站 HTML 方案（不套鲲的 API 方案）：
- 列表：/?cat=3，第 N 页 /?cat=3&paged=N；帖子 <a href="?p=ID" title="全标题 - 二狗ACG">
- 详情：/?p=ID；标题在 <title> 标签（H1 是 JS 占位"加载中"，不可用）
- 正文容器 div.single-content：全部图片 + 下载按钮区（百度/UC，UC 不采集）
- 解压密码固定 twodog；百度提取码在链接 ?pwd= 参数里
- 标题改写规则（用户 2026-09-24 定稿，见【新站调研】文档第五节）：
  "【日式RPG/中文/动态】AAA/BBB V1.05 PC+安卓双端官方中文版 百度+UC/758M"
  → "【日式RPG/中文/动态/官方中文版】AAA BBB V1.05 【PC+安卓 758M】"
"""
import json
import re
from bs4 import BeautifulSoup
from crawler.base import BaseCrawler
from parser import extract_links_multi, extract_cheat_code
from parser.image_handler import download_images

# " - 二狗ACG" 后缀
_SITE_SUFFIX_RE = re.compile(r'\s*[-|｜]\s*二狗ACG\s*$')

# 网盘尾巴 + 体积：百度+UC/758M、百度/1.59G、百度+UC /2.48G 等
_PAN_SIZE_TAIL_RE = re.compile(
    r'\s*百度(?:\s*[+＋]\s*UC|\s*[/／]\s*UC|\+UC)?(?:网盘|云)?\s*[/／]\s*'
    r'(\d+(?:\.\d+)?\s*[GMKBgmkb]+)\s*$')
# 网盘尾巴无体积
_PAN_TAIL_RE = re.compile(r'\s*百度(?:\s*[+＋]\s*UC|\+UC|[/／]\s*UC)?(?:网盘|云)?\s*$')

# 平台词：PC+安卓双端 / PC+安卓 / 安卓 / PC；要求前后有边界（空格/【/首尾），
# 避免"某PC游戏"这类名字里的 PC 被误吃；单独 PC 后必须跟 双端/端/版/空格/结尾
_PLATFORM_TOKEN_RE = re.compile(
    r'(?:^|(?<=[\s【]))(PC\s*[+＋&]\s*安卓|安卓|PC)(?:\s*(?:双端|端|版)(?![A-Za-z])|(?=\s)|$)')

# 附加描述词（挪进开头标签）：官方中文正式版+存档 / 官方中文版 / 中文版 / 完整版 / 硬盘版 / 存档
_BADGE_CUT_RE = re.compile(r'[+＋]?(?:官方中文[^，。/\s]*|中文版|完整版|硬盘版|免安装[^，。/\s]*|存档)')


def rewrite_title(raw):
    """二狗标题改写（用户 2026-09-24 给的两条标准样例为验收基准）。

    之前：原样入库（含"百度+UC/758M"等站方噪音）
    现在：【原标签/新增描述词】名字 空格分隔 【平台 体积】
    """
    t = _SITE_SUFFIX_RE.sub('', (raw or '').strip()).strip()
    if not t:
        return ""

    # "更新"前缀保留在最前
    update = ""
    m = re.match(r'^更新\s*', t)
    if m:
        update = "更新"
        t = t[m.end():]

    # 开头【】标签
    tags = []
    tags_m = re.match(r'^[【\[]([^】\]]+)[】\]]\s*', t)
    if tags_m:
        tags = [x.strip() for x in tags_m.group(1).split('/') if x.strip()]
        t = t[tags_m.end():]

    # 网盘尾巴 + 体积
    size = ""
    pan_m = _PAN_SIZE_TAIL_RE.search(t)
    if pan_m:
        size = pan_m.group(1).strip()
        t = t[:pan_m.start()].rstrip()
    else:
        pan_m = _PAN_TAIL_RE.search(t)
        if pan_m:
            t = t[:pan_m.start()].rstrip()

    # 平台词（取尾部最后一个匹配，避免名字里的 PC 误伤）
    plat = ""
    pm = None
    for pm in _PLATFORM_TOKEN_RE.finditer(t):
        pass
    if pm:
        # 平台词与名字之间的边界符（空格或【）一并去掉
        cut = pm.start()
        if cut > 0 and t[cut-1] in ' \t':
            cut = cut - 1
        raw_tok = pm.group(1).replace(' ', '')
        if '+' in raw_tok or '＋' in raw_tok or '&' in raw_tok:
            plat = "PC+安卓"
        elif '安卓' in raw_tok:
            plat = "安卓"
        else:
            plat = "PC"
        t = (t[:cut] + t[pm.end():]).strip()

    # 附加描述词（官方中文版等）挪进开头标签
    badge = ""
    bm = _BADGE_CUT_RE.search(t)
    if bm and bm.start() > 0:
        badge = bm.group(0).lstrip('+＋')
        # 连续多个描述词（如 "官方中文正式版+存档"）一起吃掉
        while True:
            nm = _BADGE_CUT_RE.match(t, bm.end())
            if not nm:
                break
            badge += nm.group(0)
            bm = nm
        t = t[:bm.start()].rstrip()

    # 名字分隔符 "/" → 空格（别名并列）
    name = re.sub(r'\s*/\s*', ' ', t).strip()
    name = re.sub(r'\s{2,}', ' ', name)

    if badge and badge not in tags:
        tags = tags + [badge]

    parts = []
    if update:
        parts.append(update)
    if tags:
        parts.append('【' + '/'.join(tags) + '】')
    tail = ''
    if plat or size:
        tail = ' 【' + ' '.join(x for x in (plat or 'PC', size) if x) + '】'
    return (''.join(parts) + name + tail).strip()


class ErGouACGCrawler(BaseCrawler):
    """二狗ACG爬虫（WordPress 明文链接，四站方案）"""

    def __init__(self, config):
        super().__init__(config)
        self.site_name = "二狗ACG"
        self.base_url = "https://2gouacg.com"
        # 该站封旧版 Chrome UA（Chrome/120 实测 403），用较新 UA
        self.session.headers["User-Agent"] = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                              "AppleWebKit/537.36 (KHTML, like Gecko) "
                                              "Chrome/126.0.0.0 Safari/537.36")

    # ---------- 列表 ----------

    def get_list_page(self, page_num):
        url = f"{self.base_url}/?cat=3" if page_num == 1 else f"{self.base_url}/?cat=3&paged={page_num}"
        soup = self._soup(url)
        results = []
        seen = set()
        for a in soup.select("a[href*='?p=']"):
            href = a.get("href", "")
            m = re.search(r'[?&]p=(\d+)', href)
            if not m:
                continue
            pid = m.group(1)
            if pid in seen:
                continue
            seen.add(pid)
            # 用 title 属性里的全标题预判平台（parse_detail 会以 <title> 为准重算）
            raw_title = a.get("title", "") or a.get_text(strip=True)
            category = ""
            if re.search(r'PC\s*[+＋&]\s*安卓|双端', raw_title):
                category = "pc_android"
            elif re.search(r'安卓', raw_title):
                category = "android"
            results.append({"url": f"{self.base_url}/?p={pid}", "category": category})
        return results

    def get_total_pages(self):
        try:
            soup = self._soup(f"{self.base_url}/?cat=3")
            max_page = 1
            for a in soup.select("a[href*='paged=']"):
                m = re.search(r'[?&]paged=(\d+)', a.get("href", ""))
                if m:
                    max_page = max(max_page, int(m.group(1)))
            return max_page
        except Exception:
            return 100

    # ---------- 详情 ----------

    def parse_detail(self, url, category=""):
        soup = self._soup(url)

        # 标题：<title> 标签（H1 是 JS 占位"加载中"）
        title_raw = ""
        title_tag = soup.find("title")
        if title_tag:
            title_raw = title_tag.get_text(strip=True)
        title = rewrite_title(title_raw)
        if not title:
            title = _SITE_SUFFIX_RE.sub('', title_raw).strip()

        # 正文容器
        content_el = soup.select_one("div.single-content")
        # 剔除「盖世模拟器」等模拟器按钮（也是百度链，站方提供的模拟器下载，非资源本体，
        # 用户 2026-09-24 反馈：真资源是旁边那个「百度网盘」按钮）
        if content_el:
            for a in content_el.select("a"):
                a_txt = a.get_text(strip=True)
                a_href = a.get("href", "") or ""
                if "模拟器" in a_txt and ("pan.baidu.com" in a_href or not a_href):
                    a.decompose()
        content = content_el.get_text(separator="\n", strip=True) if content_el else ""

        # 图片：只取正文容器内（演示视频是 <video> 标签，天然忽略）
        images = []
        if content_el:
            for img in content_el.select("img"):
                src = img.get("data-src") or img.get("src") or ""
                if not src or src.startswith("data:"):
                    continue
                low = src.lower()
                if any(k in low for k in ("logo", "avatar", "emoji", "qrcode", "loading", "98qy.com")):
                    continue
                if not src.startswith("http"):
                    src = self.base_url + src
                if src not in images:
                    images.append(src)

        # 网盘链接：只认百度（UC 按惯例不采集），平台由标题判定
        links = extract_links_multi(content)
        if not links.get("items"):
            links = extract_links_multi(str(content_el or soup))

        # 平台：改写后标题的【PC+安卓 758M】尾括号 + 原始标题兜底
        title_lower = title.lower()
        raw_lower = (title_raw or "").lower()
        if re.search(r'pc\s*[+＋&]\s*安卓|双端', title_lower + raw_lower):
            platform = "pc_android"
        elif re.search(r'安卓|android|apk', title_lower + raw_lower):
            platform = "android"
        else:
            platform = "pc"

        # 平台写进每条下载项（渲染层同 URL 会自动合并）
        items = links.get("items") or []
        for it in items:
            if it.get("provider") == "baidu" and it.get("platform") in (None, "unknown"):
                it["platform"] = platform

        # 解压密码：正文提取（防发布者改码，同 acgrx 口径），提不到用全站默认 twodog
        pwd_m = re.search(r'(?:解压密码|统一解压密码|解压码|密码)[：:\s]*([A-Za-z0-9]+)', content)
        unzip_code = f"解压码:{pwd_m.group(1) if pwd_m else 'twodog'}"

        # 发布日期：正文外元信息 "2026年9月22日"
        post_date = ""
        page_text = soup.get_text(" ", strip=True)
        dm = re.search(r'(\d{4})年(\d{1,2})月(\d{1,2})日', page_text)
        if dm:
            post_date = f"{dm.group(1)}-{int(dm.group(2)):02d}-{int(dm.group(3)):02d}"

        # source_id
        m = re.search(r'[?&]p=(\d+)', url)
        source_id = m.group(1) if m else url.rstrip('/').split('?')[0].split('/')[-1]

        # 下载图片
        proxy = None
        if self.config.get("proxy", {}).get("enabled"):
            proxy = self.config["proxy"]["http"]
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
            "download_items_json": json.dumps(items, ensure_ascii=False),
            "likes": 0,
            "comments": 0,
            "views": 0,
            "unzip_code": unzip_code,
            "cheat_code": extract_cheat_code(title, content),
            "baidu_link": links.get("baidu_link"),
            "baidu_code": links.get("baidu_code"),
            "mobile_link": None,
            "mobile_code": None,
            "images": json.dumps(images),
            "original_images": json.dumps(images),
            "post_date": post_date,
        }
