"""HTML生成器"""
import json
import shutil
import zipfile
from datetime import datetime
from pathlib import Path

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
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, "Microsoft YaHei", sans-serif; background: #0a0a0f; color: #e0e0e0; }}
.header {{ background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); padding: 24px; text-align: center; border-bottom: 1px solid #2a2a3e; }}
.header h1 {{ font-size: 24px; color: #4fc3f7; margin-bottom: 8px; }}
.header .meta {{ color: #888; font-size: 14px; }}
.grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(360px, 1fr)); gap: 20px; padding: 24px; max-width: 1400px; margin: 0 auto; }}
.card {{ background: #181825; border-radius: 12px; overflow: hidden; border: 1px solid #2a2a3e; transition: transform 0.2s; }}
.card:hover {{ transform: translateY(-3px); box-shadow: 0 12px 32px rgba(0,0,0,0.4); }}
.card-imgs {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(120px, 1fr)); gap: 2px; background: #0a0a0f; overflow: hidden; max-height: 250px; }}
.card-imgs img {{ width: 100%; height: 100%; min-height: 110px; object-fit: cover; }}
.card-imgs:has(img:nth-child(1):last-child) {{ grid-template-columns: 1fr; }}
.no-img {{ display: flex; align-items: center; justify-content: center; height: 180px; color: #555; font-size: 14px; background: #181825; }}
.card-body {{ padding: 16px; }}
.card-title {{ font-size: 14px; font-weight: 500; line-height: 1.6; margin-bottom: 12px; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }}
.card-meta {{ display: flex; gap: 16px; font-size: 12px; color: #888; margin-bottom: 12px; }}
.card-links {{ display: flex; gap: 8px; flex-wrap: wrap; }}
.link-btn {{ padding: 6px 14px; border-radius: 6px; font-size: 12px; text-decoration: none; color: #fff; }}
.link-baidu {{ background: linear-gradient(135deg, #2196F3, #1565c0); }}
.link-mobile {{ background: linear-gradient(135deg, #4CAF50, #2e7d32); }}
.link-source {{ background: #1e1e2e; color: #e0e0e0; border: 1px solid #2a2a3e; }}
.card-footer {{ padding: 10px 16px; background: rgba(0,0,0,0.25); font-size: 12px; color: #888; border-top: 1px solid #2a2a3e; }}
.copy-text {{ cursor: pointer; padding: 2px 6px; background: rgba(79,195,247,0.1); border-radius: 3px; font-family: monospace; }}
.copy-text:hover {{ background: rgba(79,195,247,0.2); }}
.tag {{ display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 500; }}
.tag-pc {{ background: rgba(79,195,247,0.15); color: #4fc3f7; }}
.tag-android {{ background: rgba(102,187,106,0.15); color: #66bb6a; }}
.tag-source {{ background: rgba(255,167,38,0.15); color: #ffa726; }}
.lightbox-overlay {{ position: fixed; inset: 0; background: rgba(4,4,8,0.92); z-index: 2000; display: flex; align-items: center; justify-content: center; animation: lbFade 0.15s ease; }}
@keyframes lbFade {{ from {{ opacity: 0; }} to {{ opacity: 1; }} }}
.lightbox-img {{ max-width: 88vw; max-height: 82vh; object-fit: contain; border-radius: 4px; box-shadow: 0 8px 48px rgba(0,0,0,0.6); cursor: zoom-out; user-select: none; }}
.lightbox-close {{ position: absolute; top: 16px; right: 20px; background: rgba(255,255,255,0.08); border: 1px solid rgba(255,255,255,0.15); color: #ddd; font-size: 22px; width: 40px; height: 40px; border-radius: 50%; cursor: pointer; line-height: 1; display: flex; align-items: center; justify-content: center; }}
.lightbox-close:hover {{ background: rgba(255,255,255,0.18); }}
.lightbox-counter {{ position: absolute; top: 24px; left: 24px; color: #ccc; font-size: 14px; background: rgba(0,0,0,0.5); padding: 4px 12px; border-radius: 12px; }}
.lightbox-nav {{ position: absolute; top: 50%; transform: translateY(-50%); background: rgba(255,255,255,0.08); border: 1px solid rgba(255,255,255,0.15); color: #ddd; font-size: 26px; width: 46px; height: 46px; border-radius: 50%; cursor: pointer; display: flex; align-items: center; justify-content: center; }}
.lightbox-nav:hover {{ background: rgba(255,255,255,0.18); }}
.lightbox-prev {{ left: 20px; }}
.lightbox-next {{ right: 20px; }}
.card-imgs img {{ cursor: zoom-in; }}
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
        el.style.background = "rgba(102,187,106,0.3)";
        setTimeout(function() {{ el.style.background = ""; }}, 500);
    }});
}}
function copyTitle(el) {{
    navigator.clipboard.writeText(el.textContent).then(function() {{
        var orig = el.textContent;
        el.textContent = "已复制!";
        setTimeout(function() {{ el.textContent = orig; }}, 800);
    }});
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
<span>❤ {likes}</span>
</div>
<div class="card-links">
{links}
</div>
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

        # 链接
        links = []
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
            parts.append(f'<button class="copy-text" data-copy="解压码：{post["unzip_code"]}" onclick="copyText(this)">解压码</button>')
        if post.get("cheat_code"):
            parts.append(f'<button class="copy-text" data-copy="作弊码：{post["cheat_code"]}" onclick="copyText(this)">作弊码</button>')
        if parts:
            footer = f'<div class="card-footer">{"&nbsp;&nbsp;".join(parts)}</div>'

        card = CARD_TEMPLATE.format(
            images_html=imgs_html,
            title=post.get("title", ""),
            platform_tag=platform_tag,
            source=post.get("source", ""),
            date=post.get("post_date", ""),
            likes=post.get("likes", 0),
            links=links_html,
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

def export_posts(posts):
    """导出帖子为HTML，android归入pc_android，打包zip含图片"""
    pc_posts = [p for p in posts if p.get("platform") == "pc"]
    # android全部归入pc_android
    mixed_posts = [p for p in posts if p.get("platform") in ("pc_android", "android")]

    pc_file = generate_html(pc_posts, "ACG游戏资源 - PC下载", "PC下载.html")
    mixed_file = generate_html(mixed_posts, "ACG游戏资源 - PC+安卓下载", "PC+安卓下载.html")

    # 打包为zip（HTML + images目录）
    pc_zip = _zip_output(pc_file, "PC下载")
    mixed_zip = _zip_output(mixed_file, "PC+安卓下载")

    return {"pc": pc_zip, "mixed": mixed_zip, "android": ""}


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
