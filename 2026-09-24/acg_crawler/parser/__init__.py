"""网盘链接提取模块"""
import re
import html as _html

BAIDU_PATTERNS = [
    r'https?://pan\.baidu\.com/s/[A-Za-z0-9_-]+(?:\?[^\s<"\']*)?',
    r'https?://pan\.baidu\.com/share/init\?[^\s<"\']+',
    r'https?://yun\.baidu\.com/s/[A-Za-z0-9_-]+',
]

CODE_PATTERNS = [
    r'(?:提取码|提取密码|密码|pwd)[：:=\s]*([A-Za-z0-9]{4})',
    r'[?&]pwd=([A-Za-z0-9]{4})',
]

CLOUD_NAME_PATTERNS = [
    # 匹配 "分享文件：XXXX" 和 "通过网盘分享的文件：XXXX" 格式
    re.compile(r'分享文件[：:]\s*([A-Za-z0-9]+)', re.IGNORECASE),
    re.compile(r'通过(?:百度|移动|阿里)?网盘分享的文件[：:]\s*([A-Za-z0-9]+)', re.IGNORECASE),
    re.compile(r'分享的文件[：:]\s*([A-Za-z0-9]+)', re.IGNORECASE),
    # 百度网盘：XXXX（排除URL，只匹配纯文件名）
    re.compile(r'(?:百度网盘|移动云盘|百度云|移动云)\s*[:：]\s*(?!https?://)([A-Za-z0-9]{4,})', re.IGNORECASE),
    re.compile(r'文件[名码称]\s*[:：]?\s*(?!https?://)([A-Za-z0-9]{4,})', re.IGNORECASE),
]

CHEAT_CODE_PATTERN = re.compile(
    r'作弊码[：:\s]*[\n\r\s|]*(\d{4,})',
    re.IGNORECASE,
)

def extract_links(text):
    """从文本中提取百度网盘链接（自动反转义HTML实体）。

    保留旧接口语义：从全文中取**一条**百度链接（取最先匹配到的）。
    新代码建议改用 :func:`extract_links_multi`，可以保留每个网盘下 PC/安卓双链接。
    移动云盘已于 2026-09-24 下线，不再采集（mobile_* 字段保留但恒为 None）。
    """
    if not text:
        return {}

    # 处理HTML转义：& " 等
    text = _html.unescape(text)

    result = {
        "baidu_link": None,
        "baidu_code": None,
        "mobile_link": None,
        "mobile_code": None,
    }

    # 提取百度网盘链接
    for pattern in BAIDU_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            url = match.group(0)
            # 标准化链接格式
            if "/share/init?" in url:
                # 从 init 链接提取 surl
                surl_match = re.search(r'surl=([A-Za-z0-9_-]+)', url)
                if surl_match:
                    url = f"https://pan.baidu.com/s/{surl_match.group(1)}"
            result["baidu_link"] = url
            break

    # 提取百度提取码
    if result["baidu_link"]:
        # 从链接本身提取
        pwd_match = re.search(r'[?&]pwd=([A-Za-z0-9]{4})', result["baidu_link"])
        if pwd_match:
            result["baidu_code"] = pwd_match.group(1)
        else:
            # 从文本中提取
            for pattern in CODE_PATTERNS:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    result["baidu_code"] = match.group(1)
                    break

    return result


# 云名前缀：用于识别每条链接对应的平台标记
# 形如 PCC148888 / AZC148888 / PCC148888 / PCCC148888 / AC148888 / PC148888 等
_CLOUD_NAME_TOKEN_RE = re.compile(
    r'\b(?P<prefix>(?:PCC|PC|pc|Pc|AZC|AZ|az|Az|ACC|AC|ac)(?:C|c)?)'
    r'(?P<num>\d{4,})\b'
)


def _split_link_blocks(text):
    """将正文按"链接 + 紧邻上文云名标签"切成块。

    站点的常见排版是::

        百度网盘：PCC148888
        链接:
        https://pan.baidu.com/s/xxx
        提取码: e3th
        百度网盘：AZC148888
        ...

    返回 ``[{"label": str|None, "url": str, "code": str|None, "start": int, "end": int}, ...]``。
    """
    if not text:
        return []

    blocks = []
    for pattern in BAIDU_PATTERNS:
        for m in re.finditer(pattern, text, re.IGNORECASE):
            blocks.append({"url": m.group(0), "start": m.start(), "end": m.end()})

    if not blocks:
        return []

    blocks.sort(key=lambda b: b["start"])
    deduped = []
    seen = set()
    for b in blocks:
        if b["url"] in seen:
            continue
        seen.add(b["url"])
        deduped.append(b)

    for b in deduped:
        # 标签行：从 URL 前 ~120 字符里找最近的云名
        ctx_start = max(0, b["start"] - 120)
        context = text[ctx_start:b["start"]]
        label = None
        for lm in _CLOUD_NAME_TOKEN_RE.finditer(context):
            label = lm.group(0).upper()
        b["label"] = label

        # 提取码：先看链接自身 pwd=xxx，再从 URL 之后 30 字符里找"提取码: xxxx"
        # 注意窗口要小，避免跨段误取上一条链接的提取码
        code = None
        pwd_match = re.search(r'[?&]pwd=([A-Za-z0-9]{4})', b["url"])
        if pwd_match:
            code = pwd_match.group(1)
        else:
            after_ctx = text[b["end"]:b["end"] + 40]
            cm = re.search(r'提取(?:码|密码)?\s*[:：]?\s*([A-Za-z0-9]{4})', after_ctx)
            if cm:
                code = cm.group(1)
        b["code"] = code

    return deduped


def _classify_platform_by_label(label):
    """根据云名标签分类平台：``PC/CPC/PCC`` → ``pc``，``AZ/AZC`` → ``android``，其他 ``unknown``。"""
    if not label:
        return "unknown"
    upper = label.upper()
    if upper.startswith("PC"):
        return "pc"
    if upper.startswith("AZ"):
        return "android"
    return "unknown"


def _is_baidu(url):
    if not url:
        return False
    u = url.lower()
    return ("pan.baidu.com" in u) or ("yun.baidu.com" in u)


def extract_links_multi(text):
    """提取帖子中**全部**百度云盘下载项并标记每条链接对应的平台。

    移动云盘已于 2026-09-24 下线，不再采集（mobile_* 字段保留但恒为 None）。

    返回结构::

        {
            "items": [
                {"provider": "baidu",
                 "url": "...",
                 "code": "..." | None,
                 "platform": "pc"|"android"|"unknown",
                 "label": "PCC148888" | None},
                ...
            ],
            "baidu_link": ...,   "baidu_code": ...,
            "baidu_pc": ...,     "baidu_pc_code": ...,
            "baidu_android": ..., "baidu_android_code": ...,
            "mobile_link": ...,  "mobile_code": ...,
            "mobile_pc": ...,    "mobile_pc_code": ...,
            "mobile_android": ..., "mobile_android_code": ...,
        }
    """
    if not text:
        return _empty_multi_result()

    text = _html.unescape(text)
    blocks = _split_link_blocks(text)

    items = []
    seen = set()
    for b in blocks:
        url = b["url"]
        if "/share/init?" in url:
            surl_match = re.search(r'surl=([A-Za-z0-9_-]+)', url)
            if surl_match:
                url = f"https://pan.baidu.com/s/{surl_match.group(1)}"

        if not _is_baidu(url):
            continue

        key = ("baidu", url)
        if key in seen:
            continue
        seen.add(key)

        platform = _classify_platform_by_label(b.get("label"))
        items.append({
            "provider": "baidu",
            "url": url,
            "code": b.get("code"),
            "platform": platform,
            "label": b.get("label"),
        })

    return _aggregate_multi(items)


def _empty_multi_result():
    return {
        "items": [],
        "baidu_link": None, "baidu_code": None,
        "baidu_pc": None, "baidu_pc_code": None,
        "baidu_android": None, "baidu_android_code": None,
        "mobile_link": None, "mobile_code": None,
        "mobile_pc": None, "mobile_pc_code": None,
        "mobile_android": None, "mobile_android_code": None,
    }


def _aggregate_multi(items):
    """从 items 中汇总出兼容字段（每个网盘保留一条链接 + 每平台各一条）。"""
    result = _empty_multi_result()
    result["items"] = items

    buckets = {
        "baidu": {"pc": [], "android": [], "unknown": []},
    }
    for it in items:
        bucket = buckets.get(it["provider"])
        if not bucket:
            continue
        bucket[it["platform"]].append(it)

    first_baidu = next((i for i in items if i["provider"] == "baidu"), None)
    if first_baidu:
        result["baidu_link"] = first_baidu["url"]
        result["baidu_code"] = first_baidu["code"]

    for provider, key, code_key in [
        ("baidu", "baidu_pc", "baidu_pc_code"),
        ("baidu", "baidu_android", "baidu_android_code"),
    ]:
        plat = "pc" if key.endswith("_pc") else "android"
        candidates = buckets[provider][plat] or buckets[provider]["unknown"]
        if candidates:
            first = candidates[0]
            result[key] = first["url"]
            result[code_key] = first["code"]

    return result


def has_valid_link(text):
    """检查文本是否包含有效的百度网盘链接（移动云盘已下线）"""
    res = extract_links(text)
    return bool(res.get("baidu_link"))


def extract_cloud_name(text):
    """从内容中提取网盘文件名（如 C156222, 24917, A1326）"""
    if not text:
        return ""
    for pattern in CLOUD_NAME_PATTERNS:
        match = pattern.search(text)
        if match:
            name = match.group(1).strip()
            if len(name) >= 3:
                return name
    return ""


def extract_cheat_code(title, content):
    """从内容中提取作弊码（标题含'作弊码'时才提取）"""
    if not content:
        return ""
    if "作弊码" not in (title or ""):
        return ""
    match = CHEAT_CODE_PATTERN.search(content)
    if match:
        return match.group(1).strip()
    return ""


# 标签词：标题中平台/大小前面需要移到开头[]的词
EXTRA_TAG_PATTERNS = [
    r'(?:动态)?AI汉化(?:版)?',
    r'动态(?:AI)?喊话(?:版)?',
    r'官中(?:步兵)?(?:版)?',
    r'步兵(?:版)?',
    r'存档(?:版)?',
    r'全CG',
    r'生肉',
    r'汉化(?:版)?',
    r'官中',
    r'动态(?:版)?',
    r'内嵌(?:AI)?汉化(?:版)?',
    r'steam版',
    r'DLC',
    r'中文(?:版)?',
]
_EXTRA_TAG_RE = re.compile('|'.join(f'(?:{p})' for p in EXTRA_TAG_PATTERNS), re.IGNORECASE)


def fix_title_slash(title):
    """修复标题中平台和大小之间的斜杠：[PC/3.87G]→[PC 3.87G]"""
    if not title:
        return title
    # 同时处理【】和[]，支持MG/GM等变体
    title = re.sub(
        r'([\[【])(PC\+安卓|PC|安卓|android)/(\d+\.?\d*\s*[GMgm][Bb]?[Bb]?)([\]】])',
        r'\1\2 \3\4',
        title,
        flags=re.IGNORECASE
    )
    return title


def fix_title_brackets(title):
    """把标题中所有 [] 改为 【】"""
    if not title:
        return title
    title = title.replace('[', '【').replace(']', '】')
    return title


# 匹配形如 【PCC148888】 / 【AZC148888】 / 【PCC 148888】 / 【CCC148888】 / 【C148888】 / 【AC148888】
# 前面会被替换为统一格式 【C148888】（去掉 PC/AZ/CC 等平台/网盘前缀）
_CLOUD_NAME_BRACKET_RE = re.compile(
    r'[\[【]\s*'
    r'(?P<prefix>(?:PCC|PC|pc|Pc|AZC|AZ|az|Az|ACC|AC|ac|CCC|cc)(?:C|c)?)'
    r'\s*'
    r'(?P<num>\d{4,})'
    r'\s*[\]】]'
)


def fix_title_cloud_name(title):
    """规范化标题中的网盘云名标签：``【PCC148888】/【AZC148888】 → 【C148888】``。

    原站点的命名规则是把平台前缀拼到云名前：PC 版本前缀是 ``PCC``，安卓版本前缀是 ``AZC``。
    标题里只需要保留纯云名 ``C148888``，避免显示冗余的平台信息。
    """
    if not title:
        return title

    def _replace(m):
        num = m.group("num")
        return f"【C{num}】"

    title = _CLOUD_NAME_BRACKET_RE.sub(_replace, title)
    return title


def fix_title_tags(title):
    """自动检测标题中平台/大小前面的额外标签，移到开头【】。

    例: 【SLG/动态】游戏名 官中版【PC 548M】 → 【SLG/动态/官中版】游戏名【PC 548M】
    也处理: 游戏名 步兵版】PC+安卓/517MG】 → 【步兵版】游戏名【PC+安卓 517MG】
    """
    if not title:
        return title

    # 修复格式: "标签名】平台/大小】" → 把标签移到开头【】
    # 匹配: 中文词+】+平台信息
    stray_tag = re.search(r'([\u4e00-\u9fff]{2,6}(?:版|CG)?)[】\]]\s*([\[【]?)', title)
    if stray_tag:
        tag_text = stray_tag.group(1)
        before = title[:stray_tag.start()]

        # 检查】是否在【...】括号对内部（统计未闭合的【数量）
        open_count = before.count('【') - before.count('】')
        is_inside_bracket = open_count > 0

        # 检查】后面是否紧跟平台信息（真正的游离标签）
        after_pos = stray_tag.end()
        has_platform_after = bool(re.match(r'(?:PC|安卓|android)', title[after_pos:], re.IGNORECASE))

        if not is_inside_bracket and has_platform_after:
            # 这是一个游离的标签，移到开头
            tag_match = re.match(r'([\[【][^]】]+[\]】])', title)
            if tag_match:
                inner = tag_match.group(1).strip('[]【】')
                if tag_text not in inner:
                    inner = inner.rstrip('/') + '/' + tag_text
                new_tag = f'【{inner}】'
                # 移除游离标签
                rest = title[:stray_tag.start()] + title[stray_tag.end():]
                # 清理开头标签（同时支持【】和[]）
                rest = re.sub(r'^[[【][^]】]+[]】]\s*', '', rest)
                title = new_tag + ' ' + rest.strip()

    # 找大小括号位置（支持【】和[]，支持G/M/GB/MG）
    size_match = re.search(r'[\[【](PC\+安卓|PC|安卓|android)[/\s](\d+\.?\d*\s*[GMgm][Bb]?[Bb]?)\s*[\]】]', title, re.IGNORECASE)
    if not size_match:
        return title

    # 找开头标签括号
    tag_match = re.match(r'([\[【][^]】]+[\]】])', title)
    if not tag_match:
        return title

    tag_bracket = tag_match.group(1)
    between = title[tag_match.end():size_match.start()]

    # 在 between 中查找标签词
    found_tags = []
    remaining = between
    for m in _EXTRA_TAG_RE.finditer(between):
        tag = m.group(0)
        if len(tag) < 2:
            continue
        found_tags.append(tag)
        remaining = remaining.replace(m.group(0), '', 1)

    if not found_tags:
        return title

    # 把标签加到开头[]里
    inner = tag_bracket.strip('[]【】')
    for tag in found_tags:
        if tag not in inner:
            inner = inner.rstrip('/') + '/' + tag
    new_tag_bracket = f'【{inner}】'

    # 重建标题：清理between中的多余空格
    clean_between = re.sub(r'\s+', ' ', remaining).strip()
    clean_between = re.sub(r'^[\s\-–—·.。、]+', '', clean_between).strip()

    result = new_tag_bracket + clean_between + title[size_match.start():]
    return result
