"""鲲Galgame（kungal.com）爬虫

四个接口（前三个公开，第四个需登录 cookie）：

1. 列表      GET /api/galgame?include_providers=baidu,caiyun&page=N&limit=20
   - 参数必须 snake_case；驼峰 includeProviders 会被 API 静默忽略（不过滤）
2. 游戏详情  GET /api/galgame/{gid}
   - name / name_original / alias[] / effective_banner_url / intro_text / view / like_count
3. 资源列表  GET /api/galgame/{gid}/resource/all?galgame_id={gid}
   - 每条资源：provider_names[] / platform / platforms[] / size / status(0有效 1失效) / note / created / user
4. 资源下载  GET /api/galgame-resource/{rid}/detail?galgame_resource_id={rid}   ← 需登录
   - link[]（真实下载链接）/ code（提取码）/ password（解压密码）/ note

挑选规则（用户确认）：
- 只保留 百度网盘 / 和彩云(移动云盘) 两类，每类只取一条：在"有效(status==0)"里按 created 取最新
- 两类都没有 → 整个游戏跳过
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


class CookieExpiredError(RuntimeError):
    """kungal 登录 cookie 失效"""


class KungalCrawler(BaseCrawler):
    """鲲Galgame爬虫（JSON API，资源下载链接需登录 cookie）"""

    PAGE_LIMIT = 20

    def __init__(self, config):
        super().__init__(config)
        self.site_name = "鲲Galgame"
        self.base_url = "https://www.kungal.com"
        self._total_pages = None
        # 登录 cookie：config.py 已把 .env 注入 os.environ
        cookie = os.environ.get("KUNGAL_COOKIE", "").strip()
        if cookie:
            self.session.headers["Cookie"] = cookie
        else:
            print("[鲲Galgame] 未配置 KUNGAL_COOKIE（.env），下载链接会取不到")

    # ---------- 基础请求 ----------

    def _api(self, path, need_login=False):
        """请求 JSON 接口并校验业务码

        自己发请求而不用 BaseCrawler._request：后者带"验证页检测"（响应体 <200 字符
        视为被拦截），而本站在列表末页会返回极短的空 JSON，会被误判成拦截页。
        """
        url = self.base_url + path
        timeout = self.config.get("crawler", {}).get("timeout", 15)
        last_err = None
        for attempt in range(3):
            self._check_pause()
            try:
                self._delay()
                resp = self.session.get(url, timeout=timeout)
                if resp.status_code == 401:
                    raise CookieExpiredError(
                        "kungal 登录 cookie 已失效，请重新登录后更新 .env 里的 KUNGAL_COOKIE")
                resp.raise_for_status()
                self._reset_failures()
                data = resp.json()
                break
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
                        resp = self.session.get(url, timeout=timeout)
                        resp.raise_for_status()
                        data = resp.json()
                        self.session.proxies = old
                        break
                    except Exception:
                        self.session.proxies = old
                if attempt == 2:
                    raise RuntimeError(f"接口请求失败: {path} ({last_err})")
                time.sleep(self.config.get("crawler", {}).get("retry_delay", 2) * (attempt + 1))

        if data.get("code") != 0:
            msg = data.get("message") or ""
            if data.get("code") == 205 or "登录" in msg:
                raise CookieExpiredError(
                    "kungal 登录 cookie 已失效，请重新登录后更新 .env 里的 KUNGAL_COOKIE")
            raise RuntimeError(f"接口返回异常: {path} -> {msg}")
        return data.get("data")

    # ---------- 列表 ----------

    def _fetch_list(self, page_num):
        return self._api(f"/api/galgame?include_providers=baidu,caiyun"
                         f"&page={page_num}&limit={self.PAGE_LIMIT}")

    def get_list_page(self, page_num):
        data = self._fetch_list(page_num) or {}
        return [{"url": f"{self.base_url}/galgame/{g['id']}", "category": ""}
                for g in (data.get("galgames") or [])]

    def get_total_pages(self):
        if self._total_pages is None:
            data = self._fetch_list(1) or {}
            total = int(data.get("total") or 0)
            self._total_pages = max(1, math.ceil(total / self.PAGE_LIMIT))
        return self._total_pages

    # ---------- 资源挑选 ----------

    @staticmethod
    def _bucket(provider_names):
        """资源归属：baidu / mobile / None（其他网盘一律忽略）"""
        names = provider_names or []
        if any(any(h in n for h in _BAIDU_HINTS) for n in names):
            return "baidu"
        if any(any(h in n for h in _MOBILE_HINTS) for n in names):
            return "mobile"
        return None

    @staticmethod
    def _created_key(resource):
        return resource.get("created") or ""

    def _pick_newest_valid(self, resources):
        """每个网盘取"有效资源里发布时间最新"的一条"""
        picked = {}
        for r in resources:
            if r.get("status") != 0:          # status 1 = 已失效，跳过
                continue
            bucket = self._bucket(r.get("provider_names"))
            if not bucket:
                continue
            old = picked.get(bucket)
            if old is None or self._created_key(r) > self._created_key(old):
                picked[bucket] = r
        return picked

    # ---------- 平台 ----------

    @staticmethod
    def _platform_set(resource):
        """把单条资源的平台标签转成 {pc|android} 集合"""
        codes = set(resource.get("platforms") or [])
        label = resource.get("platform") or ""
        result = set()
        if "win" in codes or label in ("windows", "mac", "linux"):
            result.add("pc")
        if "and" in codes or label in ("app", "android"):
            result.add("android")
        if label == "emulator":          # 模拟器版本 PC / 安卓模拟器都能跑
            result.update({"pc", "android"})
        return result

    @classmethod
    def _platform_info(cls, resources):
        """合并多条资源的平台 → (本工具平台值, 中文标签)"""
        merged = set()
        for r in resources:
            merged |= cls._platform_set(r)
        if merged == {"android"}:
            return "android", "安卓"
        if merged == {"pc"}:
            return "pc", "PC"
        if merged:
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
        """把各网盘的解压密码标注上网盘名，方便分辨（百度在前）

        - 两个网盘密码相同 → "百度网盘/移动云盘 CC"
        - 不同 → "百度网盘 open ｜ 移动云盘 afggacg"
        - 只有一个 → "百度网盘 open"
        """
        pairs = []
        for bucket, label in (("baidu", "百度网盘"), ("mobile", "移动云盘")):
            pw = ((details.get(bucket) or {}).get("password") or "").strip()
            if pw:
                pairs.append((label, pw))
        if not pairs:
            return None
        if len(pairs) > 1 and len({pw for _, pw in pairs}) == 1:
            return f"{'/'.join(label for label, _ in pairs)} {pairs[0][1]}"
        return " ｜ ".join(f"{label} {pw}" for label, pw in pairs)

    def _build_content(self, galgame, notes, sizes):
        """正文 = 各网盘大小 + 别名 + 发布者备注 + 简介

        大小放最前：别名往往很长，会把大小挤到卡片备注的折叠线以下（需展开才可见）。
        sizes 元素为 (label, size, plat_tag)，plat_tag 是"-PC"/"-安卓"，无则为空串
        （用户 2026-09-23 要求区分同一游戏不同网盘对应的平台，如 PC+安卓 游戏）。
        """
        parts = []
        if sizes:
            parts.append("网盘大小：" + " ｜ ".join(
                f"{label}{tag} {size}" for label, size, tag in sizes))
        name = (galgame.get("name") or "").strip()
        # 原名与别名合并成一行，不再单独列"其他名称"
        aliases = []
        for candidate in [(galgame.get("name_original") or ""), *(galgame.get("alias") or [])]:
            c = (candidate or "").strip()
            if c and c != name and c not in aliases:
                aliases.append(c)
        if aliases:
            parts.append("别名：" + " / ".join(aliases[:8]))
        for label, note in notes:
            if note:
                parts.append(f"【{label} 发布者备注】\n{note}")
        intro = _strip_html((galgame.get("intro_text") or "").strip())
        intro = re.sub(r"\n{3,}", "\n\n", intro)
        if intro:
            parts.append("【简介】\n" + intro[:600])
        return "\n\n".join(parts)[:5000]

    # ---------- 详情 ----------

    def parse_detail(self, url, category=""):
        gid = url.rstrip("/").split("/")[-1].split("?")[0]

        galgame = self._api(f"/api/galgame/{gid}") or {}
        resources = self._api(f"/api/galgame/{gid}/resource/all?galgame_id={gid}") or []
        picked = self._pick_newest_valid(resources)

        name = (galgame.get("name") or "").strip()
        if not picked:
            # 百度/移动云盘的有效资源都没有 → 交给引擎按"跳过"处理
            return {
                "source": self.site_name, "source_id": gid, "source_url": url,
                "title": name, "platform": "unknown", "content": "",
                "images": "[]", "original_images": "[]", "post_date": "",
            }

        # 体积上限：任一网盘超过 10GB 就整个游戏跳过（用户 2026-09-23 要求）。
        # 用列表接口自带的 size 预判，省掉详情接口请求。
        oversize = []
        for bucket, res in picked.items():
            gb = _size_to_gb(res.get("size") or "")
            if gb is not None and gb > MAX_SIZE_GB:
                oversize.append((("百度网盘" if bucket == "baidu" else "移动云盘"),
                                 res.get("size")))
        if oversize:
            desc = "、".join(f"{lb} {sz}" for lb, sz in oversize)
            return {
                "source": self.site_name, "source_id": gid, "source_url": url,
                "title": name, "platform": "unknown", "content": "",
                "images": "[]", "original_images": "[]", "post_date": "",
                "skip_reason": f"超过 {MAX_SIZE_GB:g}GB 上限（{desc}）",
            }

        # 逐个取真实下载链接（需登录）
        details, notes, sizes = {}, [], []
        audit = []
        for bucket, res in picked.items():
            detail = self._api(f"/api/galgame-resource/{res['id']}/detail"
                               f"?galgame_resource_id={res['id']}") or {}
            details[bucket] = detail
            label = "百度网盘" if bucket == "baidu" else "移动云盘"
            note_audit = {"label": label}
            note = self._optimize_note(detail.get("note") or "", detail.get("password") or "",
                                       note_audit)
            audit.append(note_audit)
            notes.append((label, note))
            size_text = (detail.get("size") or res.get("size") or "").strip()
            if size_text:
                # 该网盘支持的平台 → 标注为"-PC"/"-安卓"；两端都支持则不标
                plats = self._platform_set(res)
                tag = ""
                if plats == {"pc"}:
                    tag = "-PC"
                elif plats == {"android"}:
                    tag = "-安卓"
                sizes.append((label, size_text, tag))
        # 百度在前，移动在后
        sizes.sort(key=lambda x: 0 if x[0] == "百度网盘" else 1)

        platform, platform_label = self._platform_info(picked.values())

        # 标题：只留平台（各网盘体积写在备注里的"网盘大小"行，用户 2026-09-23 确认）
        title = f"{name} 【{platform_label}】"

        # 下载项 + 主字段：一条资源支持 PC 和安卓时，按两个平台各出一个按钮
        items = []
        for bucket, detail in details.items():
            res = picked[bucket]
            plats = sorted(self._platform_set(res)) or ["unknown"]
            for link in (detail.get("link") or []):
                if not link:
                    continue
                # 百度常把提取码写在链接的 pwd 参数里，code 字段为空时从中兜底
                code = detail.get("code") or None
                if not code:
                    m = re.search(r"[?&]pwd=([A-Za-z0-9]{4,})", link)
                    if m:
                        code = m.group(1)
                for plat in plats:
                    items.append({
                        "provider": bucket,
                        "url": link,
                        "code": code,
                        "platform": plat,
                        "label": (detail.get("provider_names") or [None])[0],
                    })

        def first(bucket, key):
            d = details.get(bucket) or {}
            if key == "url":
                links = d.get("link") or []
                return links[0] if links else None
            if key == "code":
                code = d.get("code") or None
                if not code:
                    links = d.get("link") or []
                    if links:
                        m = re.search(r"[?&]pwd=([A-Za-z0-9]{4,})", links[0])
                        if m:
                            code = m.group(1)
                return code
            return d.get(key) or None

        # 解压密码：按网盘区分标注（用户反馈"open / afggacg"看不出哪个属于哪个网盘）
        unzip_code = self._build_unzip_code(details)

        # 封面：只取 1 张主封面
        images = []
        cover = (galgame.get("effective_banner_url") or "").strip()
        if not cover:
            covers = galgame.get("covers") or []
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
        created_values = [self._created_key(r) for r in picked.values() if self._created_key(r)]
        if created_values:
            m = DATE_PATTERN.search(max(created_values))
            if m:
                post_date = m.group(0)
        if not post_date:
            m = DATE_PATTERN.search(str(galgame.get("resource_update_time") or ""))
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
            "content": self._build_content(galgame, notes, sizes),
            "download_items_json": json.dumps(items, ensure_ascii=False),
            "likes": int(galgame.get("like_count") or 0),
            "comments": 0,
            "views": int(galgame.get("view") or 0),
            "unzip_code": unzip_code,
            "cheat_code": None,
            "baidu_link": first("baidu", "url"),
            "baidu_code": first("baidu", "code"),
            "mobile_link": first("mobile", "url"),
            "mobile_code": first("mobile", "code"),
            "images": json.dumps(images),
            "original_images": json.dumps(images),
            "post_date": post_date,
        }
