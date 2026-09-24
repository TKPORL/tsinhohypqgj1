"""HTML生成器"""
import html as html_lib
import json
import shutil
import zipfile
from datetime import datetime
from pathlib import Path

from database import sort_posts

OUTPUT_DIR = Path(__file__).parent.parent / "output"
IMAGES_DIR = Path(__file__).parent.parent / "images"


def _copy_image_to_output(img_path, output_images_dir):
    """将图片复制到output/images目录，返回相对路径"""
    if not img_path or img_path.startswith("http"):
        return img_path
    # 处理 images/xxx/file.jpg 路径
    full = IMAGES_DIR.parent / img_path
    if not full.exists():
        return ""
    # 用post_id/filename作为目标路径
    rel_path = img_path.replace("images/", "")
    dest = output_images_dir / rel_path
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.exists():
        shutil.copy2(str(full), str(dest))
    return f"images/{rel_path}"

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Playfair+Display:wght@300;400&family=Geist:wght@300;400;500&family=Roboto+Mono:wght@400;500&family=Noto+Serif+SC:wght@300;400&display=swap">
<style>
:root {{
    --iris: #847dff;
    --cyan: #00b3dd;
    --pale-iris: #d1c9ff;
    --deep-iris: #4b49aa;
    --orchid: #dd90d8;
    --obsidian: #0f1011;
    --abyss: #090a0b;
    --graphite: #2e2e2e;
    --steel: #3f4041;
    --fog: #6a6b6b;
    --ash: #9f9fa0;
    --cloud: #f5f5f7;
    --pure: #ffffff;
    --void: #000000;
    --danger: #c0574e;
    --border: rgba(255, 255, 255, 0.08);
    --border-accent: rgba(255, 255, 255, 0.2);
    --hairline: rgba(255, 255, 255, 0.12);
    --chip-bg: rgba(255, 255, 255, 0.12);
    --chip-border: rgba(255, 255, 255, 0.15);
    --font-display: 'Playfair Display', 'Noto Serif SC', Georgia, 'Songti SC', 'SimSun', serif;
    --font-ui: 'Geist', 'Inter', 'Segoe UI', system-ui, 'Microsoft YaHei', sans-serif;
    --font-mono: 'Roboto Mono', 'JetBrains Mono', Consolas, ui-monospace, monospace;
    --radius-btn: 8px;
    --radius-input: 8px;
    --radius-card: 16px;
    --radius-pill: 9999px;
    --ease: 0.2s ease;
}}
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
    background: var(--obsidian);
    color: var(--cloud);
    font-family: var(--font-ui);
    font-size: 14px;
    line-height: 1.5;
    -webkit-font-smoothing: antialiased;
    padding-bottom: 80px;
}}
.header {{
    max-width: 1200px;
    margin: 0 auto;
    padding: 48px 32px 24px;
    border-bottom: 1px solid var(--hairline);
}}
.header h1 {{
    font-family: var(--font-display);
    font-weight: 300;
    font-size: 38px;
    line-height: 0.9;
    color: var(--pure);
}}
.meta {{
    margin-top: 16px;
    font-family: var(--font-mono);
    font-size: 11px;
    letter-spacing: 0.182em;
    text-transform: uppercase;
    color: var(--fog);
}}
.grid {{
    max-width: 1200px;
    margin: 0 auto;
    padding: 32px;
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
    gap: 24px;
}}
.card {{
    background: var(--graphite);
    border: 1px solid rgba(255, 255, 255, 0.06);
    border-radius: var(--radius-card);
    overflow: hidden;
    display: flex;
    flex-direction: column;
    transition: background var(--ease), border-color var(--ease);
}}
.card:hover {{ background: #333334; border-color: var(--border-accent); }}
.card-imgs {{
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
    gap: 1px;
    background: rgba(255, 255, 255, 0.06);
    overflow: hidden;
    max-height: 250px;
}}
.card-imgs img {{ width: 100%; height: 100%; min-height: 110px; object-fit: cover; display: block; background: var(--abyss); cursor: zoom-in; }}
.card-imgs:has(img:nth-child(1):last-child) img {{ height: 280px; min-height: 280px; }}
.no-img {{
    height: 160px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: var(--abyss);
    font-family: var(--font-mono);
    font-size: 11px;
    letter-spacing: 0.182em;
    text-transform: uppercase;
    color: var(--fog);
}}
.card-body {{ padding: 16px; display: flex; flex-direction: column; flex: 1; }}
.card-title {{
    font-size: 14px;
    line-height: 1.5;
    color: var(--pure);
    margin-bottom: 12px;
    cursor: pointer;
    transition: opacity var(--ease);
}}
.card-title:hover {{ opacity: 0.75; }}
.card-meta {{
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 6px;
    margin-bottom: 12px;
    font-family: var(--font-mono);
    font-size: 11px;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--ash);
}}
.tag {{
    display: inline-flex;
    align-items: center;
    font-family: var(--font-mono);
    font-size: 10px;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    padding: 3px 10px;
    background: var(--chip-bg);
    border: 1px solid var(--chip-border);
    border-radius: var(--radius-pill);
    color: var(--cloud);
}}
.tag-android {{ color: var(--cloud); }}
.tag-source {{ color: var(--ash); }}
.card-links {{ display: flex; gap: 8px; flex-wrap: wrap; }}
.link-btn {{
    padding: 7px 14px;
    border: 1px solid rgba(255, 255, 255, 0.5);
    border-radius: var(--radius-btn);
    background: transparent;
    color: var(--pure);
    font-size: 12px;
    text-decoration: none;
    transition: background var(--ease), color var(--ease), border-color var(--ease);
}}
.link-btn:hover {{ background: var(--pure); color: var(--void); border-color: var(--pure); }}
.link-source {{ border-color: var(--border); color: var(--ash); }}
.card-footer {{
    margin-top: auto;
    padding: 12px 16px;
    background: rgba(0, 0, 0, 0.3);
    border-top: 1px solid var(--border);
}}
.copy-text {{
    cursor: pointer;
    padding: 5px 12px;
    background: var(--chip-bg);
    border: 1px solid var(--chip-border);
    border-radius: var(--radius-pill);
    color: var(--pure);
    font-family: var(--font-mono);
    font-size: 10px;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    transition: background var(--ease), border-color var(--ease);
}}
.copy-text::before {{ content: '⧉'; margin-right: 6px; opacity: 0.75; }}
.copy-text:hover {{ background: rgba(255, 255, 255, 0.22); }}
.copy-text:active {{ transform: translateY(1px); }}
.copy-text.copied {{ background: rgba(0, 179, 221, 0.2); border-color: var(--cyan); }}
.card-note {{
    margin-top: 12px;
    padding: 12px;
    background: rgba(0, 0, 0, 0.35);
    border: 1px solid var(--border);
    border-radius: var(--radius-input);
    transition: border-color var(--ease), background var(--ease);
}}
.card-note:hover {{ border-color: var(--border-accent); }}
.card-note.copied-note {{ border-color: var(--cyan); background: rgba(0, 179, 221, 0.06); }}
.note-head {{
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    font-family: var(--font-mono);
    font-size: 10px;
    letter-spacing: 0.182em;
    text-transform: uppercase;
    color: var(--fog);
    margin-bottom: 8px;
}}
.note-copy-hint {{ font-size: 10px; color: var(--fog); transition: color var(--ease); }}
.card-note:hover .note-copy-hint {{ color: var(--cloud); }}
.note-body {{
    font-size: 12px;
    line-height: 1.67;
    color: var(--ash);
    white-space: pre-wrap;
    word-break: break-word;
    overflow: hidden;
    cursor: pointer;
    display: -webkit-box;
    -webkit-line-clamp: 3;
    -webkit-box-orient: vertical;
}}
.note-body:hover {{ color: var(--cloud); }}
.note-body.expanded {{ -webkit-line-clamp: unset; display: block; }}
.note-toggle {{
    display: inline-flex;
    align-items: center;
    gap: 4px;
    margin-top: 8px;
    padding: 2px 4px;
    background: none;
    border: 0;
    border-radius: 4px;
    color: var(--ash);
    font-family: var(--font-mono);
    font-size: 10px;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    cursor: pointer;
    transition: color var(--ease);
}}
.note-toggle:hover {{ color: var(--pure); }}
.note-toggle:focus-visible {{ outline: 1px solid var(--pure); outline-offset: 2px; }}
.note-arrow {{ display: inline-block; font-size: 10px; transition: transform 0.22s ease; }}
.note-toggle[aria-expanded="true"] .note-arrow {{ transform: rotate(180deg); }}
.note-toggle[hidden] {{ display: none; }}
.lightbox-overlay {{
    position: fixed;
    inset: 0;
    background: rgba(9, 10, 11, 0.95);
    z-index: 2000;
    display: flex;
    align-items: center;
    justify-content: center;
}}
.lightbox-img {{ max-width: 92vw; max-height: 88vh; border-radius: var(--radius-btn); border: 1px solid var(--border); }}
.lightbox-close, .lightbox-nav {{
    background: rgba(255, 255, 255, 0.1);
    border: 1px solid var(--border-accent);
    border-radius: var(--radius-pill);
    color: var(--pure);
    cursor: pointer;
    transition: background var(--ease);
}}
.lightbox-close {{ position: absolute; top: 24px; right: 24px; width: 40px; height: 40px; font-size: 18px; }}
.lightbox-nav {{ position: absolute; top: 50%; transform: translateY(-50%); width: 44px; height: 44px; font-size: 18px; }}
.lightbox-close:hover, .lightbox-nav:hover {{ background: rgba(255, 255, 255, 0.2); }}
.lightbox-prev {{ left: 24px; }}
.lightbox-next {{ right: 24px; }}
.lightbox-counter {{
    position: absolute;
    bottom: 24px;
    left: 50%;
    transform: translateX(-50%);
    font-family: var(--font-mono);
    font-size: 11px;
    letter-spacing: 0.1em;
    color: var(--ash);
}}
@media (max-width: 640px) {{
    .header {{ padding: 32px 16px 20px; }}
    .header h1 {{ font-size: 26px; }}
    .grid {{ padding: 16px; grid-template-columns: 1fr; }}
}}
@media (prefers-reduced-motion: reduce) {{
    * {{ transition: none !important; }}
}}
</style>
</head>
<body>
<div class="header">
<h1>{title}</h1>
<div class="meta">生成时间: {gen_time} | 共 {count} 条资源</div>
</div>
<div class="grid">
{cards}
</div>
<script>
function copyText(el) {{
    var text = el.dataset.copy || el.textContent;
    navigator.clipboard.writeText(text).then(function() {{
        el.classList.add("copied");
        var orig = el.textContent;
        el.textContent = "已复制!";
        setTimeout(function() {{ el.classList.remove("copied"); el.textContent = orig; }}, 900);
    }});
}}
// 备注整块点击复制（复制完整备注，不是被折叠截断的那段）
function copyNote(el) {{
    var text = el.dataset.copy || el.textContent;
    navigator.clipboard.writeText(text).then(function() {{
        var box = el.closest(".card-note") || el;
        box.classList.add("copied-note");
        var hint = box.querySelector(".note-copy-hint");
        var orig = hint ? hint.textContent : "";
        if (hint) hint.textContent = "已复制!";
        setTimeout(function() {{
            box.classList.remove("copied-note");
            if (hint) hint.textContent = orig;
        }}, 900);
    }});
}}
function copyTitle(el) {{
    navigator.clipboard.writeText(el.textContent).then(function() {{
        var orig = el.textContent;
        el.textContent = "已复制!";
        setTimeout(function() {{ el.textContent = orig; }}, 800);
    }});
}}
// 备注折叠：量目标态真实高度后做高度动画，收尾清掉内联高度
function noteHeightWhen(body, expanded) {{
    var was = body.classList.contains("expanded");
    if (was !== expanded) body.classList.toggle("expanded", expanded);
    var h = body.offsetHeight;
    if (was !== expanded) body.classList.toggle("expanded", was);
    return h;
}}
function toggleNote(btn) {{
    var body = document.getElementById(btn.getAttribute("aria-controls"));
    if (!body) return;
    var next = btn.getAttribute("aria-expanded") !== "true";
    var start = body.offsetHeight;
    var target = noteHeightWhen(body, next);
    var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    body.style.transition = "none";
    body.style.maxHeight = start + "px";
    void body.offsetHeight;
    body.style.transition = reduce ? "none" : "max-height 0.22s ease";
    body.classList.toggle("expanded", next);
    body.style.maxHeight = target + "px";
    btn.setAttribute("aria-expanded", next ? "true" : "false");
    btn.setAttribute("aria-label", next ? "收起备注" : "展开备注");
    var t = btn.querySelector(".note-toggle-text");
    if (t) t.textContent = next ? "收起" : "展开";
    setTimeout(function() {{
        body.style.maxHeight = "";
        body.style.transition = "";
    }}, reduce ? 0 : 240);
}}
// 文字没超过折叠行数时不显示按钮
function initNotes() {{
    document.querySelectorAll(".card-note").forEach(function(box) {{
        var body = box.querySelector(".note-body");
        var btn = box.querySelector(".note-toggle");
        if (!body || !btn) return;
        var full = noteHeightWhen(body, true);
        var clamped = noteHeightWhen(body, false);
        btn.hidden = (full - clamped) <= 2;
    }});
}}
if (document.readyState === "loading") {{
    document.addEventListener("DOMContentLoaded", initNotes);
}} else {{
    initNotes();
}}
var lbState = {{ imgs: [], idx: 0, overlay: null }};
function openLightbox(sources, start) {{
    lbState.imgs = sources || [];
    lbState.idx = start || 0;
    if (!lbState.imgs.length) return;
    var ov = document.createElement("div");
    ov.className = "lightbox-overlay";
    var counter = document.createElement("div");
    counter.className = "lightbox-counter";
    var img = document.createElement("img");
    img.className = "lightbox-img";
    var closeBtn = document.createElement("button");
    closeBtn.className = "lightbox-close";
    closeBtn.textContent = "×";
    var prevBtn = document.createElement("button");
    prevBtn.className = "lightbox-nav lightbox-prev";
    prevBtn.textContent = "‹";
    var nextBtn = document.createElement("button");
    nextBtn.className = "lightbox-nav lightbox-next";
    nextBtn.textContent = "›";
    ov.appendChild(counter); ov.appendChild(img); ov.appendChild(closeBtn);
    if (lbState.imgs.length > 1) {{ ov.appendChild(prevBtn); ov.appendChild(nextBtn); }}
    document.body.appendChild(ov);
    document.body.style.overflow = "hidden";
    lbState.overlay = ov;
    function render() {{
        img.src = lbState.imgs[lbState.idx];
        counter.textContent = (lbState.idx + 1) + " / " + lbState.imgs.length;
        var multi = lbState.imgs.length > 1;
        prevBtn.style.display = multi ? "" : "none";
        nextBtn.style.display = multi ? "" : "none";
    }}
    function close() {{
        if (lbState.overlay) {{
            document.body.removeChild(lbState.overlay);
            document.body.style.overflow = "";
            lbState.overlay = null;
        }}
    }}
    function step(d) {{
        var n = lbState.imgs.length;
        if (!n) return;
        lbState.idx = (lbState.idx + d + n) % n;
        render();
    }}
    ov.addEventListener("click", function(e) {{ if (e.target === ov || e.target === img) close(); }});
    closeBtn.addEventListener("click", close);
    prevBtn.addEventListener("click", function(e) {{ e.stopPropagation(); step(-1); }});
    nextBtn.addEventListener("click", function(e) {{ e.stopPropagation(); step(1); }});
    document.addEventListener("keydown", function(e) {{
        if (!lbState.overlay) return;
        if (e.key === "Escape") close();
        else if (e.key === "ArrowLeft") step(-1);
        else if (e.key === "ArrowRight") step(1);
    }});
    render();
}}
document.addEventListener("click", function(e) {{
    var img = e.target.closest(".card-imgs img");
    if (!img) return;
    var container = img.closest(".card-imgs");
    if (!container) return;
    var sources = [];
    container.querySelectorAll("img").forEach(function(im) {{ if (im.src) sources.push(im.src); }});
    var idx = Array.prototype.indexOf.call(container.querySelectorAll("img"), img);
    openLightbox(sources, idx);
}});
</script>
</body>
</html>"""

CARD_TEMPLATE = """
<div class="card">
<div class="card-imgs">{images_html}</div>
<div class="card-body">
<div class="card-title" onclick="copyTitle(this)" title="点击复制标题">{title}</div>
<div class="card-meta">
<span>{platform_tag}</span>
<span class="tag tag-source">{source}</span>
<span>{date}</span>
<span><span style="color:var(--fog)">LIKE</span> {likes}</span>
</div>
<div class="card-links">
{links}
</div>
{note}
</div>
{footer}
</div>"""

def generate_html(posts, title, filename):
    """生成HTML文件，图片单独存放在output/images/目录（每次导出前清空旧图片）"""
    output_dir = OUTPUT_DIR / filename.replace(".html", "")
    output_images_dir = output_dir / "images"
    # 清空旧图片目录，避免上次导出的残留图片混入本次zip
    if output_images_dir.exists():
        shutil.rmtree(output_images_dir)
    output_images_dir.mkdir(parents=True, exist_ok=True)

    cards_html = ""
    for post in posts:
        # 图片 - 复制到output/images，使用相对路径
        images = []
        try:
            images = json.loads(post.get("images", "[]"))
        except:
            pass
        imgs_html = ""
        for raw_img in images:
            local_path = _copy_image_to_output(raw_img, output_images_dir)
            if local_path:
                imgs_html += f'<img src="{local_path}" alt="" onerror="this.style.display=\'none\'">'
            elif raw_img.startswith("http"):
                # 远程URL保留引用（离线时不可用）
                imgs_html += f'<img src="{raw_img}" alt="" onerror="this.style.display=\'none\'">'
        if not imgs_html:
            imgs_html = '<div class="no-img">No Image</div>'

        # 平台标签
        platform = post.get("platform", "unknown")
        platform_tags = {
            "pc": '<span class="tag tag-pc">PC</span>',
            "android": '<span class="tag tag-android">安卓</span>',
            "pc_android": '<span class="tag tag-pc">PC</span> <span class="tag tag-android">安卓</span>',
            "unknown": '<span class="tag tag-pc">未知</span>',
        }
        platform_tag = platform_tags.get(platform, platform_tags["unknown"])

        # 链接：优先用 download_items_json 多链接渲染，单网盘回退兼容字段
        links = []
        items = []
        raw_items = post.get("download_items_json")
        if raw_items:
            try:
                items = json.loads(raw_items) if isinstance(raw_items, str) else raw_items
            except Exception:
                items = []

        def _label_for(plat):
            return "PC" if plat == "pc" else ("安卓" if plat == "android" else "")

        def _code_suffix(code):
            return f" ({code})" if code else ""

        if items:
            # 按平台归类，单个网盘最多输出 2 个按钮
            for provider, label_zh in (("baidu", "百度网盘"), ("mobile", "移动云盘")):
                plats = [it for it in items if it.get("provider") == provider]
                if not plats:
                    continue
                seen_plats = set()
                for it in plats:
                    plat = it.get("platform") or "unknown"
                    if plat in seen_plats:
                        continue
                    seen_plats.add(plat)
                    suffix = _label_for(plat)
                    cls = "link-baidu" if provider == "baidu" else "link-mobile"
                    text = f"{label_zh}{suffix}" if suffix else label_zh
                    links.append(
                        f'<a href="{it.get("url", "#")}" class="link-btn {cls}" target="_blank">'
                        f'{text}{_code_suffix(it.get("code"))}</a>'
                    )
        else:
            # 兼容老数据：按 baidu_link / mobile_link 单条渲染
            if post.get("baidu_link"):
                code = post.get("baidu_code", "")
                links.append(f'<a href="{post["baidu_link"]}" class="link-btn link-baidu" target="_blank">百度网盘{(" ("+code+")") if code else ""}</a>')
            if post.get("mobile_link"):
                code = post.get("mobile_code", "")
                links.append(f'<a href="{post["mobile_link"]}" class="link-btn link-mobile" target="_blank">移动云盘{(" ("+code+")") if code else ""}</a>')
        links.append(f'<a href="{post.get("source_url", "#")}" class="link-btn link-source" target="_blank">原帖</a>')
        links_html = "\n".join(links)

        # 底部
        footer = ""
        parts = []
        if post.get("unzip_code"):
            _uc = html_lib.escape(str(post["unzip_code"]), quote=True)
            parts.append(f'<button class="copy-text" data-copy="解压码：{_uc}" title="解压码：{_uc}" onclick="copyText(this)">解压码</button>')
        if post.get("cheat_code"):
            _cc = html_lib.escape(str(post["cheat_code"]), quote=True)
            parts.append(f'<button class="copy-text" data-copy="作弊码：{_cc}" title="作弊码：{_cc}" onclick="copyText(this)">作弊码</button>')
        if parts:
            footer = f'<div class="card-footer">{"&nbsp;&nbsp;".join(parts)}</div>'

        # 备注（发布者说明）：折叠 3 行，超出才给展开按钮；整块点击复制
        # 仅鲲Galgame 需要（用户为主的站点才有发布者备注）；其余四站为管理员整理站，
        # 其 content 是游戏简介，不属于备注，卡片不展示（2026-09-23 用户确认恢复）
        note_html = ""
        note_text = (post.get("content") or "").strip()
        if note_text and post.get("source") == "鲲Galgame":
            shown = note_text[:2000] + "……" if len(note_text) > 2000 else note_text
            # 复制内容 = 完整备注（含"网盘大小"行，用户 2026-09-23 起要求带上）
            copy_text = note_text.strip()
            note_id = f"note-{post.get('id', 'x')}"
            note_html = (
                '<div class="card-note">'
                '<div class="note-head"><span>备注</span><span class="note-copy-hint">点击复制</span></div>'
                f'<div class="note-body" id="{note_id}" data-copy="{html_lib.escape(copy_text, quote=True)}" '
                f'title="点击复制备注" onclick="copyNote(this)">{html_lib.escape(shown)}</div>'
                f'<button class="note-toggle" type="button" aria-expanded="false" '
                f'aria-controls="{note_id}" aria-label="展开备注" onclick="toggleNote(this)">'
                '<span class="note-toggle-text">展开</span>'
                '<span class="note-arrow" aria-hidden="true">▾</span>'
                '</button>'
                '</div>'
            )

        card = CARD_TEMPLATE.format(
            images_html=imgs_html,
            title=post.get("title", ""),
            platform_tag=platform_tag,
            source=post.get("source", ""),
            date=post.get("post_date", ""),
            likes=post.get("likes", 0),
            links=links_html,
            note=note_html,
            footer=footer,
        )
        cards_html += card + "\n"

    html = HTML_TEMPLATE.format(
        title=title,
        gen_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        count=len(posts),
        cards=cards_html,
    )

    filepath = output_dir / filename
    filepath.write_text(html, encoding="utf-8")
    return str(filepath)

def export_posts_filtered(posts, source="all"):
    """按筛选条件导出帖子为单个zip（含所有平台）。

    用于"导出当前筛选"按钮：用户在结果页按来源/平台/搜索条件筛选后，
    一键导出所有匹配帖子（不分平台），生成单个zip文件。
    """
    posts = sort_posts(posts)
    tag = source if source and source != "all" else "全部来源"
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    base = f"筛选导出-{tag}-{ts}"
    title = f"ACG游戏资源 - {tag}筛选结果"
    html_file = generate_html(posts, title, f"{base}.html")
    zip_file = _zip_output(html_file, base)
    _cleanup_old_exports(keep=10)
    return {"filtered": zip_file}


def export_posts(posts, name_suffix=""):
    """导出为三个 zip：PC / PC+安卓 / 安卓。

    2026-09-23 起单安卓（platform='android'）不再并入 PC+安卓，三类互不重叠；
    unknown 归入 PC。某类无数据则该 zip 为 None（前端可据此禁用按钮）。
    """
    posts = sort_posts(posts)
    pc_posts = [p for p in posts if p.get("platform") in ("pc", "unknown")]
    pc_android_posts = [p for p in posts if p.get("platform") == "pc_android"]
    android_posts = [p for p in posts if p.get("platform") == "android"]

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")

    def _base(prefix):
        return f"{prefix}-{name_suffix}-{ts}" if name_suffix else f"{prefix}-{ts}"

    result = {}
    for key, title, group in (
        ("pc", "PC下载", pc_posts),
        ("pc_android", "PC+安卓下载", pc_android_posts),
        ("android", "安卓下载", android_posts),
    ):
        if not group:
            result[key] = ""
            continue
        base = _base(title)
        html_file = generate_html(group, f"ACG游戏资源 - {title}", f"{base}.html")
        result[key] = _zip_output(html_file, base)

    # 三个zip都完成后再清理旧导出，避免清理误删本次刚生成的临时目录
    _cleanup_old_exports(keep=10)
    result["mixed"] = result.get("pc_android") or ""   # 兼容旧前端/脚本
    return result


def _zip_output(html_path, zip_name):
    """将导出目录打包为zip，包含HTML和images"""
    if not html_path:
        return ""
    html_path = Path(html_path)
    output_dir = html_path.parent
    zip_path = OUTPUT_DIR / f"{zip_name}.zip"

    with zipfile.ZipFile(str(zip_path), 'w', zipfile.ZIP_DEFLATED) as zf:
        # 添加HTML文件
        zf.write(str(html_path), html_path.name)
        # 添加images目录
        images_dir = output_dir / "images"
        if images_dir.exists():
            for img_file in images_dir.rglob("*"):
                if img_file.is_file():
                    arcname = f"images/{img_file.relative_to(images_dir)}"
                    zf.write(str(img_file), arcname)

    return str(zip_path)


def _cleanup_old_exports(keep=10):
    """output/ 只保留最近 keep 个zip及其同名临时目录，其余删除。

    每次导出都会生成新时间戳文件，不清理会无限膨胀。
    删除失败（文件被占用等）仅跳过，不影响导出。
    """
    import shutil as _sh
    try:
        zips = sorted(
            (f for f in OUTPUT_DIR.glob("*.zip") if f.is_file()),
            key=lambda p: p.stat().st_mtime, reverse=True)
        for old_zip in zips[keep:]:
            try:
                old_zip.unlink()
            except Exception:
                pass
        # 与保留zip同名的临时目录保留，其余删除
        keep_stems = {p.stem for p in zips[:keep]}
        for d in OUTPUT_DIR.iterdir():
            if d.is_dir() and d.stem not in keep_stems:
                try:
                    _sh.rmtree(d)
                except Exception:
                    pass
    except Exception:
        pass  # 清理失败不影响导出主流程
