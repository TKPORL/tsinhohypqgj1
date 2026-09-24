# 旧版视觉风格存档 —— 「粉紫渐变」深色主题

> 存档时间：2026-09-23
> 来源：git 提交 `5d59fbd`（2026-09-08 之前使用的风格）
> 替换为：Origin 深色编辑风（2026-09-23）

## 这份存档是什么

2026-09-23 之前，整个项目（主界面 + 离线导出 HTML）用的是**粉紫渐变深色主题**。
当天被整体替换成 **Origin 深色编辑风**，用户随后表示新风格不合适，希望换回旧风格。
但当时**没有把旧风格完整记录下来**，导致"想换回去却不知道旧的长什么样"。

这份存档就是为了解决这个问题：把旧风格的完整源文件固化下来，随时可取。

## 文件清单

| 文件 | 作用 | 说明 |
|------|------|------|
| `主界面-style.css` | 主界面样式（旧版） | 完整可用，覆盖回 `acg_crawler/static/style.css` 即可 |
| `主界面-index.html` | 主界面模板（旧版） | 仅作参考；含旧版的 DOM 结构 |
| `主界面-app.js` | 主界面前端逻辑（旧版） | ⚠️ 仅作参考，**不要直接覆盖**，会丢掉后来的功能（备注折叠等） |
| `导出模块-generator.py` | 导出模块（旧版） | ⚠️ 仅作参考，**不要直接覆盖**，会丢掉后来的功能（三份拆分、备注过滤等） |

## 旧风格的视觉规格（关键参数）

```css
/* 调色板 */
--bg-deep:        #08080c   /* 最底层背景 */
--bg-primary:     #0e0e14   /* 面板背景 */
--bg-card:        #14141e   /* 卡片背景 */
--bg-card-hover:  #1a1a28
--bg-input:       #1c1c2a
--bg-sidebar:     #0b0b10
--text-primary:   #c8c8d4
--text-muted:     #6a6a80
--text-dim:       #4a4a5e
--accent:         #e056a0   /* ★ 粉红主色 */
--accent-soft:    rgba(224, 86, 160, 0.12)
--accent-glow:    rgba(224, 86, 160, 0.25)   /* 发光效果 */
--blue:  #5b8def   --green: #4ecb71   --orange: #e8943a   --red: #d94848
--border:         #1e1e30
--border-accent:  #2a2a42
--grad-1: linear-gradient(135deg, #e056a0, #8b5cf6)   /* ★ 粉→紫渐变（主按钮/标题） */
--grad-2: linear-gradient(135deg, #5b8def, #4ecb71)   /* 蓝→绿渐变 */

/* 字体 */
font-family: "Inter", "SF Pro Display", -apple-system, "Microsoft YaHei", sans-serif;
letter-spacing: -0.01em;

/* 特征 */
- 标题 h1：15px / weight 600 / 颜色 = --accent（粉色）
- 卡片 hover：transform: translateY(-3px) + box-shadow（有投影、会上浮）
- 卡片圆角：12px（大圆角）
- 图片网格：grid auto-fill minmax(120px,1fr)，max-height: 250px
- 滚动条：5px 细条

/* 离线导出 HTML（旧版独立一套） */
body      { background: #0a0a0f; color: #e0e0e0; }
.header   { background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); }
.header h1{ color: #4fc3f7; }   /* 蓝青 */
.card     { background: #181825; border: 1px solid #2a2a3e; }
.card:hover { transform: translateY(-3px); box-shadow: 0 12px 32px rgba(0,0,0,0.4); }
```

## 怎么切回旧风格

⚠️ **不要直接 `git checkout HEAD -- <文件>` 全量覆盖**，因为 `app.js` / `generator.py` 里除了样式还有今天新增的**功能逻辑**（备注折叠、三份拆分等），全量覆盖会把功能也一起回退。

正确做法分两步：

### 主界面（`acg_crawler/static/style.css`）

这个文件是**纯样式**，可以直接覆盖：

```bash
cd "D:/Tsinho文件夹/新Tsinho黄油爬取工具"
cp "docs/风格存档/旧版-粉紫渐变/主界面-style.css" "acg_crawler/static/style.css"
```

### 离线导出 HTML（样式内嵌在 `acg_crawler/generator/__init__.py` 的 `HTML_TEMPLATE` 字符串里）

**只能手工替换 CSS 段**，不能覆盖整个文件。步骤：

1. 打开 `docs/风格存档/旧版-粉紫渐变/导出模块-generator.py`
2. 找到 `HTML_TEMPLATE = """..."""` 里的 `<style> ... </style>` 整段
3. 复制这段 `<style>`，替换 `acg_crawler/generator/__init__.py` 里 `HTML_TEMPLATE` 中对应的 `<style>` 段
4. **保留当前版本里的功能部分**（`{note}` 备注占位符、卡片模板结构、JS 里的备注折叠函数）

> 更稳的做法：先 `git stash` 或整目录备份，再动手。

### 只换主界面、导出 HTML 保持新风格

如果只想改主界面，上面「主界面」一步就够了，导出 HTML 会继续用 Origin 风格，两边会不一致 —— 按需选择。

## 相关文档

- 视觉系统新旧对照与决策记录：`【项目全解】说明文档.md` → 「五、视觉系统」
- 风格变更的来龙去脉：`【变更记录】修改日志.md`
