"""鲲Galgame（kungal.com）爬虫

★ 2026-09-24 站点重构为 Go API（kun-galgame-nuxt4），前缀改为 /api/v1，旧 /api/galgame 路由已弃用
  （请求会 404 + "页面版本已过期"）。新接口（鉴权仍是 kungal_session cookie，匿名单独可用）：

1. 列表      GET /api/v1/works?page=N&limit=20&include_nsfw=true
   - 默认排序 resource_updated_desc；默认排除 NSFW，必须带 include_nsfw=true
   - 默认只列"至少有一条资源"的 work
2. 作品详情  GET /api/v1/works/{gid}?include_nsfw=true
   - display_name / aliases[] / intros[{locale,value}] / covers / like_count / view_count
3. 资源列表  GET /api/v1/works/{gid}/resources?page=1&limit=50   （valid 优先、newest 次之）
   - 每条：provider_names[]（由链接域名推导，如"百度网盘"）/ resource_platforms[]（win/and/...）
     / size / state(valid|expired) / content(slate 文档=发布者备注) / created_at
4. 下载发放  POST /api/v1/galgame-resources/{rid}/downloads   ← 匿名可调（每次计数一次下载）
   - download_urls[]（真实下载链接）/ extraction_code（提取码）/ archive_password（解压密码）

挑选规则（用户确认）：
- 只保留 百度网盘 一类（移动云盘 2026-09-24 起不再采集），只取一条：在"有效(state==valid)"里按 created_at 取最新
- 没有百度资源 → 整个游戏跳过
- 解压密码单独进 unzip_code 字段，备注里对应那行自动去掉并重排序号（避免重复与空位）
"""
import json
import math
import os
import re
import threading
import time
from datetime import datetime
from pathlib import Path

from crawler.base import BaseCrawler
from parser.image_handler import download_images

# provider_names 里出现这些词就归入对应网盘
_BAIDU_HINTS = ("百度",)
_MOBILE_HINTS = ("彩云", "移动")

DATE_PATTERN = re.compile(r"(20\d{2})-(\d{2})-(\d{2})")
# 备注里"解压密码/解压码"这类行（密码已单独成字段，不需要在正文重复）
_PASSWORD_LINE = re.compile(r"(解压)?(密码|暗号|pass\s*word|pwd)", re.IGNORECASE)
_NUMBERED_LINE = re.compile(r"^\s*(\d+)\s*[.、)]\s*")

# 单个体积上限（GB）：超过则整个游戏跳过不入库（用户 2026-09-23 要求）
MAX_SIZE_GB = 10.0
# 从 "10.8 GB" / "900 MB" / "1.15GB" 这类文本里取数值+单位
_SIZE_RE = re.compile(r"([\d.]+)\s*(TB|GB|MB|KB)", re.IGNORECASE)
_UNIT_GB = {"TB": 1024.0, "GB": 1.0, "MB": 1 / 1024.0, "KB": 1 / 1024.0 / 1024.0}


def _size_to_gb(text):
    """"10.8 GB" → 10.8；解析不出来返回 None。"""
    m = _SIZE_RE.search(text or "")
    if not m:
        return None
    try:
        return float(m.group(1)) * _UNIT_GB[m.group(2).upper()]
    except (ValueError, KeyError):
        return None

# ---------- 引流内容识别（通用规则，不依赖具体句子） ----------
# 思路：发布者的"引流"本质上就是三种东西 —— ①引流到别的网盘/外部站点
# ②引流到他的社群（QQ群/微信群）③引流到他的教程/工具汇总页。
# 所以按"域名 + 结构特征 + 社群词"判断，而不是背句子，遇到新句子也能识别。

# 非目标网盘的推广域名 / 发布者外部站点（目标网盘 baidu、139 不在此列，不会被误伤）
_PROMO_DOMAINS = (
    "pan.quark.cn", "quark.cn", "aliyundrive.com", "alipan.com",
    "115.com", "115cdn", "123pan.com", "lanzou", "xunlei.com",
    "uc.cn", "tianyiyun", "cloud.189", "slpeey", "kungal.com/galgame-resource",
    "bilibili.com", "b23.tv", "youtube.com", "youtu.be", "docs.qq.com",
)
# 社群引导 / 教程 / 工具汇总类关键词
_PROMO_HINTS = (
    "加群", "qq群", "微信群", "交流群", "粉丝群", "群号",
    "教程", "工具汇总", "常用工具", "常用模拟器",
    "问题解答", "更多汇总", "更多问题", "安装问题", "不会用",
)
# 「带链接 + 这些词」也判为引流：例 "lz4解压工具如下 https://yun.139.com/..."，
# 域名本身是目标网盘，靠域名判断不了，改看"链接 + 工具/教程"这个组合特征。
_LINK_CTX = re.compile(r"https?://|www\.", re.IGNORECASE)
_LINK_CTX_WORDS = ("工具", "教程", "模拟器", "汇总", "群", "补丁", "说明文档")
# 单独成行的平台名/截图说明（图片被丢弃后留下的残句）
_BARE_PLATFORM = re.compile(r"^(游戏截图|截图|PC|安卓|Android|Win|Windows)$", re.IGNORECASE)
# 句子以这些词收尾，通常后面跟着一条被丢弃的外链，整行一并丢弃
_LEADOUT_TAIL = re.compile(r"(请查看|请访问|详见|详情请|请到|自取|见下方|如下|见下)[：:！!。\s]*$", re.IGNORECASE)
# 编号列表的引导句（如"注：以下内容以推荐游玩顺序排列："），组被丢弃时一并丢弃
_GROUP_LEADIN = re.compile(r"(以下内容|顺序排列|推荐游玩|游玩顺序|列表如下|如下|注\s*[：:])", re.IGNORECASE)
# 整行就是一个链接（可被 <...>、（...）包裹）
_BARE_LINK = re.compile(r"^[<（(\[\s]*https?://\S+[>）)\]\s]*$", re.IGNORECASE)


def _promo_rule(line):
    """判断一行是否是发布者引流内容，命中则返回规则名，否则返回 None

    只丢弃真正跟游戏无关的引流，不动游戏本身的信息：
    - "推荐使用 Bandizip" / "用 lz4 解压" 这类没有链接的说明 → 保留
    - "甜蜜夏日系列合集，包含以下内容" 这类版本说明 → 保留

    返回规则名而不是 bool，是为了把"删了什么、按哪条规则删的"写进清洗日志，
    方便复核误删（详见 _audit_clean）。
    """
    # 先干掉看不见的字符：原文常夹着零宽空格/方向控制符，
    # 会让"PC"这种短行匹配不上（实测 'PC\u200b' 就漏过）
    s = re.sub(r"[\u200b-\u200f\u202a-\u202e\ufeff]", "", line or "")
    s = re.sub(r"[\u00a0\u3000]", " ", s).strip()
    if not s:
        return None
    # ① 整行只有一个链接 → 引流（正常说明不会只丢一个裸链接）
    if _BARE_LINK.match(s):
        return "①整行裸链接"
    # ② 命中非目标网盘 / 外部站点域名 → 引流
    low = s.lower()
    if any(d in low for d in _PROMO_DOMAINS):
        return "②外部域名"
    # ③ 社群引导 / 教程汇总 / 工具推荐
    if any(h in low for h in _PROMO_HINTS):
        return "③社群或教程关键词"
    # ④ 带链接 + 工具/教程类词
    if _LINK_CTX.search(s) and any(w in low for w in _LINK_CTX_WORDS):
        return "④链接+工具教程词"
    # ⑤ 以"请看/详见/自取"等收尾的引导句（后面的链接已被上面规则丢弃，这半句也没意义）
    if _LEADOUT_TAIL.search(s):
        return "⑤引导句收尾"
    # ⑥ 纯数字（QQ 号之类的联系方式）
    if re.fullmatch(r"[1-9]\d{6,11}", s):
        return "⑥QQ号"
    # ⑦ 图片被丢弃后残留的平台名/截图说明
    if _BARE_PLATFORM.match(s):
        return "⑦残留平台名"
    return None


def _is_promo_line(line):
    """判断一行是否是发布者引流内容（通用规则）"""
    return _promo_rule(line) is not None


# ---------- 清洗日志（误删 / 漏删复核用） ----------
# 爬完一次全库几千条，光看结果分不清"删对了还是删过头"，所以留一份审计：
#   removed  = 被丢掉的行 + 命中的规则（复核误删：规则打错的行一眼能看出来）
#   suspect  = 被保留但仍然可疑的行（复核漏删：可能是新增的引流写法没被规则覆盖）
# 只写日志，不参与业务判断；写失败也不能影响爬取。

_CLEAN_LOG_DIR = Path(__file__).resolve().parent.parent / "logs" / "promo_clean"
_clean_log_lock = threading.Lock()

# 保留下来但看着像引流的特征：链接 / 邮箱微信 / 长数字 / 拉群联系推广
_SUSPECT_KEPT = re.compile(
    r"https?://|www\.|\S+@\S+|\b\d{6,12}\b"
    r"|群|公众号|加我|联系|推广|商务|合作",
    re.IGNORECASE,
)
# 单条备注最多记几行可疑内容（避免个别长备注把日志撑爆）
_SUSPECT_MAX = 5


def _excerpt(line, limit=120):
    """截断长行，日志只保留能辨认的片段"""
    s = re.sub(r"\s+", " ", (line or "").strip())
    return s if len(s) <= limit else s[:limit] + "…"


def _looks_suspicious(line):
    """保留行里是否藏着"可能是引流但规则没覆盖"的特征"""
    return bool(_SUSPECT_KEPT.search(line or ""))


def _audit_clean(gid, title, audit):
    """把本次备注清洗结果追加到 logs/promo_clean/YYYY-MM-DD.jsonl

    audit: [{"label": "百度网盘", "removed": [{rule, line}], "suspect": [{line}]}, ...]
    """
    if not audit:
        return
    entries = []
    for item in audit:
        removed = item.get("removed") or []
        suspect = item.get("suspect") or []
        if not removed and not suspect:
            continue
        entries.append({
            "label": item.get("label", ""),
            "removed": removed,
            "suspect": suspect[:_SUSPECT_MAX],
        })
    if not entries:
        return
    now = datetime.now()
    record = {
        "time": now.strftime("%Y-%m-%d %H:%M:%S"),
        "gid": str(gid),
        "title": title,
        "notes": entries,
    }
    try:
        _CLEAN_LOG_DIR.mkdir(parents=True, exist_ok=True)
        with _clean_log_lock:
            with (_CLEAN_LOG_DIR / f"{now:%Y-%m-%d}.jsonl").open("a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError as e:
        # 日志写不进去不能拖垮整轮爬取
        print(f"[鲲Galgame] 清洗日志写入失败: {e}")


def _strip_html(text):
    """去掉混进来的 HTML 标签和零宽字符（<br /> 当换行，其余标签直接去掉）"""
    text = re.sub(r"<br\s*/?>", "\n", text or "", flags=re.IGNORECASE)
    text = re.sub(r"</?[a-zA-Z][^>]*>", "", text)
    text = re.sub(r"[\u200b-\u200f\u202a-\u202e\ufeff]", "", text)
    return text


def _doc_to_text(node):
    """把新 API 的 slate 富文本文档（{object: document/paragraph/text, children: [...]}）转成纯文本"""
    if isinstance(node, str):
        return node
    if not isinstance(node, dict):
        return ""
    if node.get("object") == "text":
        return node.get("value") or ""
    parts = []
    for child in node.get("children") or []:
        parts.append(_doc_to_text(child))
    if node.get("object") == "paragraph":
        return "\n".join(p for p in "\n".join(parts).split("\n") if p) if parts else ""
    return "".join(parts)


def _collapse_numbered_groups(lines, keep):
    """编号列表整组处理

    发布者常这么推别的东西：
        1. 某游戏A（链接）
        2. 某游戏B（链接）
        3. 某游戏C          <- 这行自己没有链接，单看不像引流
    组内只要有一项命中了引流，整组一起丢弃，避免留下没头没尾的孤行。
    就地修改 keep 列表。
    """
    i = 0
    while i < len(lines):
        if not _NUMBERED_LINE.match(lines[i]):
            i += 1
            continue
        j = i
        while j < len(lines) and _NUMBERED_LINE.match(lines[j]):
            j += 1
        if any(not keep[k] for k in range(i, j)):
            for k in range(i, j):
                keep[k] = False
            # 组上方紧挨着的引导句（"注：以下内容以推荐游玩顺序排列："）也一并丢弃，
            # 否则会留下一句没有下文的半截话
            k = i - 1
            while k >= 0 and not lines[k].strip():
                k -= 1
            if k >= 0 and _GROUP_LEADIN.search(lines[k]):
                keep[k] = False
        i = j


_KANA_RE = re.compile(r"[\u3040-\u30ff\u31f0-\u31ff]")
_HAN_RE = re.compile(r"[\u4e00-\u9fff]")


def _alias_values(galgame):
    """取别名列表（兼容新 API [{value}] 与测试用旧字段 [str]）"""
    raw = galgame.get("aliases") or []
    if raw and isinstance(raw[0], dict):
        raw = [a.get("value") or a.get("name") or "" for a in raw]
    return [(a or "").strip() for a in raw]


class CookieExpiredError(RuntimeError):
    """kungal 登录 cookie 失效"""


class KungalCrawler(BaseCrawler):
    """鲲Galgame爬虫（/api/v1 JSON API，下载发放匿名可用，cookie 仅作身份补充）"""

    PAGE_LIMIT = 20
    # 资源列表单页上限（API 默认 50，超出会 LIMIT_TOO_LARGE）
    RESOURCE_PAGE_LIMIT = 50
    # 单个作品最多拉几页资源（一个作品几十条资源已到顶）
    RESOURCE_MAX_PAGES = 5

    def __init__(self, config):
        super().__init__(config)
        self.site_name = "鲲Galgame"
        self.base_url = "https://www.kungal.com"
        self._total_pages = None
        # 登录 cookie：config.py 已把 .env 注入 os.environ
        # 新 API 下载发放匿名可用，cookie 只用于后续可能的登录态接口，失效不影响爬取
        cookie = os.environ.get("KUNGAL_COOKIE", "").strip()
        if cookie:
            self.session.headers["Cookie"] = cookie

    # ---------- 基础请求 ----------

    def _api(self, path, method="GET", payload=None):
        """请求 /api/v1 JSON 接口（新 Go API：业务错误走 HTTP 状态码，body 是 RFC problem 或 {code,message}）"""
        url = self.base_url + path
        timeout = self.config.get("crawler", {}).get("timeout", 15)
        last_err = None
        for attempt in range(3):
            self._check_pause()
            try:
                self._delay()
                if method == "POST":
                    resp = self.session.post(url, json=payload or {}, timeout=timeout)
                else:
                    resp = self.session.get(url, timeout=timeout)
                if resp.status_code == 401:
                    raise CookieExpiredError(
                        "kungal 登录 cookie 已失效，请重新登录后更新 .env 里的 KUNGAL_COOKIE")
                resp.raise_for_status()
                self._reset_failures()
                return resp.json()
            except CookieExpiredError:
                raise
            except Exception as e:
                last_err = e
                self._throttle_on_failure()
                # 代理失败时退回直连再试一次
                if self._proxy_enabled and attempt == 0:
                    old = self.session.proxies.copy()
                    try:
                        self.session.proxies = {}
                        if method == "POST":
                            resp = self.session.post(url, json=payload or {}, timeout=timeout)
                        else:
                            resp = self.session.get(url, timeout=timeout)
                        resp.raise_for_status()
                        result = resp.json()
                        self.session.proxies = old
                        return result
                    except Exception:
                        self.session.proxies = old
                if attempt == 2:
                    raise RuntimeError(f"接口请求失败: {path} ({last_err})")
                time.sleep(self.config.get("crawler", {}).get("retry_delay", 2) * (attempt + 1))

    def _error_message(self, resp):
        """从错误响应里尽量抠出人话（problem JSON 的 detail/message/title 都试一遍）"""
        try:
            d = resp.json()
        except Exception:
            return f"HTTP {resp.status_code}"
        for key in ("message", "detail", "title"):
            if d.get(key):
                return f"HTTP {resp.status_code} {d[key]}"
        return f"HTTP {resp.status_code}"

    # ---------- 列表 ----------

    def _fetch_list(self, page_num):
        return self._api(f"/api/v1/works?include_nsfw=true"
                         f"&page={page_num}&limit={self.PAGE_LIMIT}")

    def get_list_page(self, page_num):
        data = self._fetch_list(page_num) or {}
        return [{"url": f"{self.base_url}/galgame/{g['id']}", "category": ""}
                for g in (data.get("items") or [])]

    def get_total_pages(self):
        if self._total_pages is None:
            data = self._fetch_list(1) or {}
            total = int(data.get("total") or 0)
            self._total_pages = max(1, math.ceil(total / self.PAGE_LIMIT))
        return self._total_pages

    # ---------- 资源挑选 ----------

    @staticmethod
    def _bucket(provider_names):
        """资源归属：baidu / None（移动云盘等其余网盘一律忽略，2026-09-24 起只收百度）"""
        names = provider_names or []
        if any(any(h in n for h in _BAIDU_HINTS) for n in names):
            return "baidu"
        return None

    @staticmethod
    def _created_key(resource):
        return resource.get("created_at") or ""

    def _pick_newest_valid(self, resources):
        """按百度区全部有效资源判定平台并挑选下载链接（用户 2026-09-24 确认）：

        平台 = 百度区全部有效资源平台的并集：
        - 全是 PC → 选最新 1 条，平台 pc
        - 全是安卓 → 选最新 1 条，平台 android
        - 同时含 PC 与安卓（单条双平台或多条各占一端）→ PC/安卓各选最新 1 条
          （同一条双平台只留一条），平台 pc_android
        返回 (选中的资源列表, 平台并集 set)；无百度有效资源返回 ([], set())
        """
        valid = [r for r in resources
                 if r.get("state") == "valid"      # expired = 已失效，跳过
                 and self._bucket(r.get("provider_names")) == "baidu"]
        union = set()
        for r in valid:
            union |= self._platform_set(r)
        if not valid or not union:
            return [], set()

        def newest(subset):
            return max(subset, key=self._created_key)

        def note_boost(subset, u):
            """发布者备注优先于平台标签（用户 2026-09-24：备注写明"PC+安卓"的按备注归 PC+安卓）"""
            for r in subset:
                if re.search(r"PC\s*[＋+]\s*安卓", _doc_to_text(r.get("content") or {}), re.I):
                    return {"pc", "android"}
            return u

        if union in ({"pc"}, {"android"}):
            best = newest(valid)
            return [best], note_boost([best], union)
        # pc+android：两端各选最新一条；同一条双平台只留一条
        selected = []
        for plat in ("pc", "android"):
            best = newest([r for r in valid if plat in self._platform_set(r)])
            if best is not None and not any(best is s for s in selected):
                selected.append(best)
        # PC 资源备注写明"PC+安卓"（如"PC+安卓直装"）→ 该条已覆盖两端，不再另选安卓包，
        # 否则 PC 链接本身就直装安卓、再配一条安卓包 = 双安卓（用户 2026-09-24）
        if len(selected) > 1:
            pc_res = next((r for r in selected if self._platform_set(r) == {"pc"}), None)
            if pc_res and re.search(r"PC\s*[＋+]\s*安卓",
                                    _doc_to_text(pc_res.get("content") or {}), re.I):
                selected = [pc_res]
        return selected, note_boost(selected, union)

    def _fetch_all_resources(self, gid):
        """拉取作品全部资源（新 API 是分页集合，默认 valid 优先、newest 次之）"""
        out = []
        total = None
        for page in range(1, self.RESOURCE_MAX_PAGES + 1):
            data = self._api(f"/api/v1/works/{gid}/resources?page={page}"
                             f"&limit={self.RESOURCE_PAGE_LIMIT}") or {}
            items = data.get("items") or []
            out.extend(items)
            total = int(data.get("total") or 0)
            if len(out) >= total or not items:
                break
        return out

    # ---------- 平台 ----------

    @staticmethod
    def _display_name(galgame):
        """标题名（用户 2026-09-24）：display_name 常是日文原名，
        别名里有中文名（含汉字、无假名）时优先当中文名用。
        返回 (标题名, 原名)；原名非空时进别名行。"""
        name = ((galgame.get("display_name") or galgame.get("name") or "")).strip()
        for a in _alias_values(galgame):
            if a and a != name and _HAN_RE.search(a) and not _KANA_RE.search(a):
                return a, name
        return name, ""

    @staticmethod
    def _platform_set(resource):
        """把单条资源的平台标签转成 {pc|android} 集合（新 API：resource_platforms，win/and/ios/swi/dvd）"""
        codes = set(resource.get("resource_platforms") or resource.get("platforms") or [])
        result = set()
        if "win" in codes:
            result.add("pc")
        if "and" in codes:
            result.add("android")
        return result

    @staticmethod
    def _platform_label(union):
        """百度区平台并集 → (本工具平台值, 中文标签)"""
        if union == {"android"}:
            return "android", "安卓"
        if union == {"pc"}:
            return "pc", "PC"
        if union:
            return "pc_android", "PC+安卓"
        return "pc", "PC"   # 拿不到平台标签时按 PC 兜底，避免整条丢失

    # ---------- 备注处理 ----------

    @staticmethod
    def _optimize_note(note, password="", audit=None):
        """备注优化：摘出解压密码行 + 剔除发布者引流内容，并重排序号。

        密码已单独成字段，正文不再重复；引流内容（教程/社群/外部站点/工具汇总）
        按通用规则识别后丢弃，保留真正跟游戏有关的说明（版本、解压方式等）。

        audit 传入 dict 时，会把"删了哪些行、按哪条规则删、留下哪些可疑行"写进去，
        供 _audit_clean 落盘复核（不影响清洗结果）。
        """
        if not note:
            return ""
        note = note.replace("\\\n", "\n").replace("\\:", ":")
        lines = note.split("\n")
        # 第一阶段：逐行标记（密码行 + 引流行），同时记下命中的规则名
        keep = []
        tags = []
        for line in lines:
            s = line.strip()
            if not s:
                keep.append(True)
                tags.append(None)
                continue
            if _PASSWORD_LINE.search(s):
                keep.append(False)
                tags.append("解压密码行")
                continue
            # 链接残头：slate 链接节点只留文字不留 URL，行尾只剩"xxx链接："标签的整行丢弃
            # （用户 2026-09-24：避免用户误以为有工具链接却没发出来）
            if re.search(r"链接\s*[：:]\s*$", s):
                keep.append(False)
                tags.append("链接残头")
                continue
            rule = _promo_rule(s)
            keep.append(rule is None)
            tags.append(rule)
        # 第二阶段：编号列表整组处理（"1./2./3. 推荐别的游戏"这类，末项常无链接）
        _collapse_numbered_groups(lines, keep)
        # 被整组连坐丢掉的行（自己没命中规则）标一下，方便区分是不是误伤
        for i, kept in enumerate(keep):
            if not kept and tags[i] is None and lines[i].strip():
                tags[i] = "编号列表连坐"
        if audit is not None:
            audit["removed"] = [
                {"rule": tags[i], "line": _excerpt(lines[i])}
                for i, kept in enumerate(keep) if not kept and lines[i].strip()
            ]
            audit["suspect"] = [
                {"line": _excerpt(lines[i])}
                for i, kept in enumerate(keep) if kept and _looks_suspicious(lines[i])
            ]

        dropped = any(not k and lines[i].strip() for i, k in enumerate(keep))
        text = "\n".join(l for l, k in zip(lines, keep) if k)
        # 丢弃后重排序号，避免出现 1、2、4 这种断号
        if dropped:
            counter = 0
            out = []
            for line in text.split("\n"):
                m = _NUMBERED_LINE.match(line)
                if m:
                    counter += 1
                    line = _NUMBERED_LINE.sub(f"{counter}. ", line)
                out.append(line)
            text = "\n".join(out)
        # 清掉混进来的 HTML 标签和零宽字符（<br /> 当换行，其余标签去掉）
        text = _strip_html(text)
        text = re.sub(r"[ \t]+\n", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        # 轻微清理 markdown 标记，保持语义不变（站点前端也是按纯文本渲染的）
        text = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r"\1（\2）", text)
        text = text.replace("**", "")
        text = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"\1", text)   # 斜体标记
        text = re.sub(r"^\s*#{1,6}\s*", "", text, flags=re.M)
        text = re.sub(r"^\s*>\s?", "", text, flags=re.M)
        return text.strip()

    @staticmethod
    def _build_unzip_code(details):
        """解压密码文本（前端直接复制这段，不再加前缀，用户 2026-09-24）

        details 元素为 (资源, 下载详情)：
        - 只有一条密码（或全部相同）→ "解压码:open"
        - 多条密码不同（凑出的 PC+安卓两条链接）→ "PC解压码:open ｜ 安卓解压码:afggacg"
        """
        entries = []
        for res, detail in details:
            pw = (detail.get("password") or "").strip()
            if not pw or any(p == pw for _, p in entries):
                continue
            entries.append((KungalCrawler._platform_set(res) if res else set(), pw))
        if not entries:
            return None
        if len(entries) == 1:
            return f"解压码:{entries[0][1]}"
        labels = []
        for plats, pw in entries:
            if plats == {"pc"}:
                labels.append(f"PC解压码:{pw}")
            elif plats == {"android"}:
                labels.append(f"安卓解压码:{pw}")
            else:
                labels.append(f"解压码:{pw}")
        return " ｜ ".join(labels)

    def _build_content(self, galgame, notes, sizes):
        """正文 = 各网盘大小 + 别名 + 发布者备注 + 简介

        大小放最前：别名往往很长，会把大小挤到卡片备注的折叠线以下（需展开才可见）。
        sizes 元素为 (label, size, plat_tag)，plat_tag 是"-PC"/"-安卓"，无则为空串
        （用户 2026-09-23 要求区分同一游戏不同网盘对应的平台，如 PC+安卓 游戏）。
        兼容新 API 字段（display_name/aliases/intros）与测试用旧字段（name/alias/intro_text）。
        """
        parts = []
        if sizes:
            parts.append("网盘大小：" + " ｜ ".join(
                f"{label}{tag} {size}" for label, size, tag in sizes))
        name, name_original = self._display_name(galgame)
        # 别名行：原名（多为日文）+ 其余别名；标题已占用的名字剔除
        candidates = ([name_original] if name_original else []) + _alias_values(galgame)
        aliases = []
        for candidate in candidates:
            c = (candidate or "").strip()
            if c and c != name and c not in aliases:
                aliases.append(c)
        if aliases:
            parts.append("别名：" + " / ".join(aliases[:8]))
        note_items = [(tag, note) for tag, note in notes if note]
        if len(note_items) > 1 and all(tag for tag, _ in note_items):
            # 凑出的 PC+安卓（两条资源各带备注）→ 合并成一个块（用户 2026-09-24：要简短）
            parts.append("【发布者备注】\n" +
                         "\n".join(f"{tag}：{note}" for tag, note in note_items))
        else:
            for _, note in note_items:
                parts.append(f"【百度网盘 发布者备注】\n{note}")
        intro = self._intro_text(galgame)
        if intro:
            parts.append("【简介】\n" + intro[:600])
        return "\n\n".join(parts)[:5000]

    @staticmethod
    def _intro_text(galgame):
        """作品简介：新 API 是 intros[{locale,value}]，优先中文；兼容旧 intro_text 字段"""
        intros = galgame.get("intros") or []
        if intros and isinstance(intros[0], dict):
            pick = None
            for it in intros:
                if it.get("locale") in ("zh-Hans", "zh-cn", "zh"):
                    pick = it.get("value")
                    break
            if not pick:
                pick = intros[0].get("value")
            intro = _strip_html((pick or "").strip())
            return re.sub(r"\n{3,}", "\n\n", intro)
        intro = _strip_html((galgame.get("intro_text") or "").strip())
        return re.sub(r"\n{3,}", "\n\n", intro)

    # ---------- 详情 ----------

    @staticmethod
    def _is_baidu_url(url):
        u = (url or "").lower()
        return "pan.baidu.com" in u or "yun.baidu.com" in u

    def parse_detail(self, url, category=""):
        gid = url.rstrip("/").split("/")[-1].split("?")[0]

        work = self._api(f"/api/v1/works/{gid}?include_nsfw=true") or {}
        resources = self._fetch_all_resources(gid)
        selected, plat_union = self._pick_newest_valid(resources)

        name, _ = self._display_name(work)
        if not selected:
            # 百度网盘的有效资源都没有 → 交给引擎按"跳过"处理
            return {
                "source": self.site_name, "source_id": gid, "source_url": url,
                "title": name, "platform": "unknown", "content": "",
                "images": "[]", "original_images": "[]", "post_date": "",
            }

        # 体积上限：超过 10GB 就整个游戏跳过不入库（用户 2026-09-23 要求）
        oversize = []
        for res in selected:
            gb = _size_to_gb(res.get("size") or "")
            if gb is not None and gb > MAX_SIZE_GB:
                oversize.append(("百度网盘", res.get("size")))
        if oversize:
            desc = "、".join(f"{lb} {sz}" for lb, sz in oversize)
            return {
                "source": self.site_name, "source_id": gid, "source_url": url,
                "title": name, "platform": "unknown", "content": "",
                "images": "[]", "original_images": "[]", "post_date": "",
                "skip_reason": f"超过 {MAX_SIZE_GB:g}GB 上限（{desc}）",
            }

        # 逐个资源发下载请求拿真实链接（新 API：POST downloads 发放，匿名可用）
        details = []   # [(资源, 下载详情), ...]，PC 在前安卓在后
        notes, sizes = [], []
        audit = []
        for res in selected:
            dl = self._api(f"/api/v1/galgame-resources/{res['id']}/downloads",
                           method="POST") or {}
            # 只保留百度链接（用户 2026-09-24：移动云盘等其余网盘不要了）
            links = [u for u in (dl.get("download_urls") or []) if self._is_baidu_url(u)]
            detail = {
                "link": links,
                "code": (dl.get("extraction_code") or "").strip() or None,
                "password": (dl.get("archive_password") or "").strip() or None,
                "provider_names": res.get("provider_names"),
            }
            label = "百度网盘"
            plats = self._platform_set(res)
            # 备注行的平台前缀：纯 PC → "PC："，纯安卓 → "安卓："，双平台不标
            note_tag = "PC" if plats == {"pc"} else ("安卓" if plats == {"android"} else None)
            note_audit = {"label": label}
            note = self._optimize_note(
                _doc_to_text(res.get("content") or {}), detail["password"], note_audit)
            audit.append(note_audit)
            notes.append((note_tag, note))
            size_text = (res.get("size") or "").strip()
            if size_text:
                # 该资源支持的平台 → 标注为"-PC"/"-安卓"；两端都支持则不标
                tag = ""
                if plats == {"pc"}:
                    tag = "-PC"
                elif plats == {"android"}:
                    tag = "-安卓"
                sizes.append((label, size_text, tag))
            details.append((res, detail))
        # PC 资源排前，安卓在后
        details.sort(key=lambda x: 0 if self._platform_set(x[0]) == {"pc"} else 1)

        platform, platform_label = self._platform_label(plat_union)

        # 标题：只留平台（各网盘体积写在备注里的"网盘大小"行，用户 2026-09-23 确认）
        # 资源自带标签（如【PC/盖世/Winator】附全CG存档+特典）拼在标题后（用户 2026-09-24，同其他站风格）
        res_titles = []
        for res in selected:
            t = (res.get("title") or "").strip()
            if t and t not in res_titles:
                res_titles.append(t)
        title = f"{name} 【{platform_label}】" + "".join(f"【{t}】" for t in res_titles)

        # 下载项 + 主字段：一条链接只出一个按钮（用户 2026-09-24：
        # 单条资源本身 PC+安卓 通吃时不再拆成两个同链接按钮，标签标"百度网盘(PC+安卓)"）
        items = []
        for res, detail in details:
            plats = sorted(self._platform_set(res)) or ["unknown"]
            if plats == ["android", "pc"]:
                plat_key = "pc_android"
            else:
                plat_key = plats[0]
            for link in detail.get("link") or []:
                if not link:
                    continue
                # 百度常把提取码写在链接的 pwd 参数里，code 字段为空时从中兜底
                code = detail.get("code") or None
                if not code:
                    m = re.search(r"[?&]pwd=([A-Za-z0-9]{4,})", link)
                    if m:
                        code = m.group(1)
                items.append({
                    "provider": "baidu",
                    "url": link,
                    "code": code,
                    "platform": plat_key,
                    "label": (detail.get("provider_names") or [None])[0],
                })

        # 同 URL 合并：不同资源贴了同一个百度链接时只留一个按钮，平台取并集
        # （用户 2026-09-24：同一条链接不该按资源拆成"PC/安卓"两个按钮）
        merged = {}
        for it in items:
            cur = merged.get(it["url"])
            if cur is None:
                merged[it["url"]] = dict(it)
                continue
            plats = {cur["platform"], it["platform"]} - {"unknown"}
            if cur["platform"] == "pc_android" or it["platform"] == "pc_android" \
                    or plats == {"pc", "android"}:
                cur["platform"] = "pc_android"
            elif len(plats) == 1:
                cur["platform"] = plats.pop()
        items = list(merged.values())

        # 主链接字段：取第一条百度链接（PC 排前）
        baidu_link = baidu_code = None
        for res, detail in details:
            links = detail.get("link") or []
            if links:
                baidu_link = links[0]
                baidu_code = detail.get("code") or None
                if not baidu_code:
                    m = re.search(r"[?&]pwd=([A-Za-z0-9]{4,})", baidu_link)
                    if m:
                        baidu_code = m.group(1)
                break

        # 解压密码：多条密码不同时按资源平台标注（"百度网盘-PC open ｜ 百度网盘-安卓 afggacg"）
        unzip_code = self._build_unzip_code(details)

        # 封面：只取 1 张主封面
        images = []
        cover_obj = work.get("cover") or work.get("banner") or {}
        if isinstance(cover_obj, dict):
            cover = (cover_obj.get("url") or "").strip()
        else:
            cover = ""
        if not cover:
            covers = work.get("covers") or []
            if covers and isinstance(covers[0], dict):
                cover = covers[0].get("url") or ""
        if cover:
            images = [cover]

        proxy = self.config["proxy"]["http"] if self.config.get("proxy", {}).get("enabled") else None
        local_images = download_images(images, gid, proxy=proxy)
        if local_images:
            images = local_images

        # 发布日期：取所选资源里最新的一条（离现在最近）
        post_date = ""
        created_values = [self._created_key(r) for r in selected if self._created_key(r)]
        if created_values:
            m = DATE_PATTERN.search(max(created_values))
            if m:
                post_date = m.group(0)
        if not post_date:
            m = DATE_PATTERN.search(str(work.get("resource_updated_at") or ""))
            if m:
                post_date = m.group(0)

        # 清洗审计：删了什么 / 留下什么可疑，落盘供人工复核（不影响入库内容）
        _audit_clean(gid, title, audit)

        return {
            "source": self.site_name,
            "source_id": gid,
            "source_url": url,
            "title": title,
            "platform": platform,
            "content": self._build_content(work, notes, sizes),
            "download_items_json": json.dumps(items, ensure_ascii=False),
            "likes": int(work.get("like_count") or 0),
            "comments": 0,
            "views": int(work.get("view_count") or 0),
            "unzip_code": unzip_code,
            "cheat_code": None,
            "baidu_link": baidu_link,
            "baidu_code": baidu_code,
            "mobile_link": None,
            "mobile_code": None,
            "images": json.dumps(images),
            "original_images": json.dumps(images),
            "post_date": post_date,
        }
