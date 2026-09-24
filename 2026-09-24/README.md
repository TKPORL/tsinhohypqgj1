# ACG黄油资源聚合爬取工具

本地运行的ACG游戏资源聚合爬取工具，从多个站点抓取资源信息，提供Web界面预览，并支持导出离线HTML文件。

## 功能特性

- **多站点聚合**：支持5个ACG资源站点爬取
- **实时进度**：爬取过程中前端实时显示日志和进度
- **卡片预览**：爬取结果以卡片形式展示，含图片、网盘链接、解压码
- **平台分类**：自动识别PC/PC+安卓平台并分类
- **导出下载**：一键打包导出zip（HTML+图片），离线可浏览
- **批量操作**：支持批量删除、批量导出选中项

## 目标站点

| 站点 | 域名 | CMS | 登录 |
|------|------|-----|------|
| ACG游戏姬 | www.acgyxjvip.com | WordPress + Lolimeow | 不需要 |
| 萌幻ACG | bbs4.acgrx.com | Typecho + MiKu | 需要（已配置） |
| ACG图书馆 | acgll.xyz | WordPress + Zibll | 不需要 |
| ACG俱乐部 | www.acgjlb.cc | WordPress + Zibll | 不需要 |
| 鲲Galgame | www.kungal.com | Nuxt3 SSR + JSON API | 下载链接接口需要（已配置） |
| 二狗ACG | 2gouacg.com | WordPress + TouchGal 风格主题 | 不需要 |

## 快速开始

### 环境要求

- Python 3.9+
- pip

### 安装与启动

```bash
# 进入项目目录
cd acg_crawler

# 安装依赖
pip install -r requirements.txt

# 双击 start.bat（Windows，固定使用 C:/Python314/python.exe）
# 或手动运行
C:/Python314/python.exe app.py
```

浏览器自动打开 `http://127.0.0.1:5000`

### 依赖说明

| 包 | 用途 |
|----|------|
| flask | Web服务器 |
| requests | HTTP请求 |
| beautifulsoup4 | HTML解析 |
| lxml | HTML解析器 |
| pyyaml | 配置文件解析 |

## 配置说明

编辑 `config.yaml`：

```yaml
# 代理设置（可选）
proxy:
  enabled: false
  http: "http://127.0.0.1:7890"

# 爬虫设置
crawler:
  max_workers: 12          # 并发数
  request_delay_min: 0.2   # 最小请求间隔(秒)
  request_delay_max: 0.5   # 最大请求间隔(秒)
  timeout: 10              # 请求超时(秒)

# Flask设置
flask:
  host: "127.0.0.1"
  port: 5000
```

## 项目结构

```
acg_crawler/
├── app.py                 # Flask主程序，API路由
├── config.py              # 配置管理
├── config.yaml            # 配置文件
├── requirements.txt       # 依赖列表
├── start.bat              # Windows一键启动
├── crawler/               # 爬虫模块
│   ├── base.py            # 基础爬虫类
│   ├── acgyxj.py          # ACG游戏姬爬虫
│   ├── acgrx.py           # 萌幻ACG爬虫
│   ├── acgll.py           # ACG图书馆爬虫
│   ├── acgjlb.py          # ACG俱乐部爬虫
│   └── kungal.py          # 鲲Galgame爬虫（JSON API，需登录）
├── parser/                # 解析模块
│   ├── __init__.py        # 链接/云盘名提取
│   └── image_handler.py   # 图片下载处理
├── database/              # 数据库模块
│   └── __init__.py        # SQLite操作
├── generator/             # 导出模块
│   └── __init__.py        # HTML生成+zip打包
├── templates/             # 页面模板
│   └── index.html         # 主页面
├── static/                # 静态资源
│   ├── app.js             # 前端逻辑
│   └── style.css          # 样式
├── data/                  # 数据目录
│   └── crawler.db         # SQLite数据库
├── images/                # 下载的图片
│   └── {post_id}/         # 按帖子ID分目录
└── output/                # 导出目录（每次导出生成 `<类型>-<时间戳>/` 与同名 .zip，自动只留最近 10 次）
    ├── PC下载/            # PC导出（含 platform=unknown）
    ├── PC+安卓下载/       # 双平台导出
    └── 安卓下载/          # 单安卓导出（v14 起独立，不再并入 PC+安卓）
```

## 使用指南

### 1. 爬取资源

1. 打开浏览器访问 `http://127.0.0.1:5000`
2. 在「爬取控制」面板选择目标站点
3. 选择爬取模式：
   - **按页码**：指定起止页码范围
   - **按日期**：指定日期范围
   - **增量**：从上次位置继续
4. 点击「开始爬取」，实时查看进度
5. 完成后自动跳转到结果页

### 2. 查看结果

- 在「爬取结果」面板浏览卡片
- 支持按来源站点、平台类型筛选
- 点击图片可放大查看
- 点击网盘链接可直接跳转下载

### 3. 导出文件

1. 切换到「导出文件」面板
2. 按类型下载（**三类互不重叠**，某类无数据则不生成该 zip）：
   - **PC下载.zip**：PC 平台资源（`unknown` 归入此类）
   - **PC+安卓下载.zip**：双平台资源
   - **安卓下载.zip**：仅单安卓平台资源（v14 起从 PC+安卓中拆出）
3. 点击下载按钮，得到zip压缩包
4. 解压后双击HTML文件即可离线浏览（含图片）

### 4. 批量操作

- 勾选卡片前的复选框可多选
- 点击「批量删除」可删除选中项
- 点击「导出选中」可只导出勾选的资源

## API接口

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/posts` | GET | 获取帖子列表 |
| `/api/posts_grouped` | GET | 按平台分组获取 |
| `/api/start_crawl` | POST | 启动爬取任务 |
| `/api/stop_crawl` | POST | 停止爬取任务 |
| `/api/progress` | GET | 获取爬取进度 |
| `/api/export` | GET | 执行导出 |
| `/api/export_download` | GET | 下载导出文件 |
| `/api/redownload_images` | POST | 重新下载图片 |
| `/api/delete_post` | POST | 删除帖子 |
| `/api/batch_delete` | POST | 批量删除 |

## 常见问题

### 图片不显示

1. 点击「重新下载图片」按钮
2. 等待下载完成
3. 刷新页面

### 导出HTML图片不显示

导出为zip格式，解压后HTML和images目录在同一目录下，双击HTML即可看到图片。

### 代理设置

如果需要代理，在config.yaml中设置：
```yaml
proxy:
  enabled: true
  http: "http://127.0.0.1:7890"
```

### 爬取速度慢

调整config.yaml中的并发和延迟：
```yaml
crawler:
  max_workers: 12
  request_delay_min: 0.2
  request_delay_max: 0.5
```

## 更新日志

### 2026-09-24 (v21) 二狗剔除「盖世模拟器」按钮链接
- 站方每帖挂「盖世模拟器 / 百度网盘 / UC网盘」三个按钮，前两个都是百度链；模拟器那条不是资源本体（用户截图反馈：救生员狂热帖出两个百度按钮）
- `parse_detail` 剔除锚文本含「模拟器」且指向百度网盘的 `<a>`；删 20 条重爬第 1 页验证：17840 只剩真资源 `?pwd=8u2y`，残留 0，20/20 成功

### 2026-09-24 (v20) 二狗解压码改带前缀格式 + 正文提取兜底
- 解压码字段：`twodog`（纯码）→ `解压码:twodog`（与鲲一致，前端直接复制不加前缀）
- 不再写死：先从正文提取（正则同萌幻口径 `解压密码/解压码/密码`），提不到才回落全站默认 `twodog`（防发布者以后改码）
- 验证：临时实例（5099 端口）真量爬 1 页 = 20 帖，19 成功 1 失败；解压码/标题改写/平台/提取码/日期全对；导出 HTML 视觉核对正常

### 2026-09-24 (v19) 新增第 6 站：二狗ACG（2gouacg.com，四站 HTML 方案）
- 新爬虫 `crawler/ergouacg.py`（注册键 `2gou`，中文名「二狗ACG」），WordPress 明文链接，**不套鲲的 API 方案**
- 列表 `/?cat=3&paged=N`（第 1 页不带 paged），详情 `/?p=ID`；标题取 `<title>` 标签（H1 是 JS 占位"加载中"）
- 正文容器 `div.single-content`：全部图片（演示视频 `<video>` 天然忽略）+ 下载按钮区；只采百度，UC 按惯例不采集；百度提取码在链接 `?pwd=` 参数
- 解压密码全站固定 `twodog`
- **标题改写**（用户 2026-09-24 定稿两条标准样例为单测）：`【标签】名字 PC+安卓双端官方中文版 百度+UC/758M` → `【标签/官方中文版】名字 【PC+安卓 758M】`——"更新"前缀保留、描述词（官方中文版等）挪进开头标签、名字里 `/` 分隔换空格、平台词边界匹配（防误吃名字里的 PC）、网盘+体积收进尾括号
- 该站封旧版 Chrome UA（Chrome/120 实测 403），已覆盖为 Chrome/126
- 前端注册：`templates/index.html` 站点勾选框 + 来源筛选下拉、`static/app.js` SITE_NAMES
- 验证：标题改写 5 用例单测全过（含两条标准样例逐字比对）；离线列表解析 20 条/页、总页数 95；真实帖子冒烟 2 篇（`?p=17969` PC+安卓 2.48G、`?p=17962` 纯PC 219M）标题/平台/链接/提取码/日期全部正确
- 玖黎ACG（jiuliacg.com）：用户 2026-09-24 拍板**放弃接入**（下载链接回复可见，无法绕过；调研记录保留在【新站调研】文档）

### 2026-09-24 (v18) 鲲Galgame 适配站点重构（新 Go API /api/v1）+ 平台判定按百度区实际资源
- 站点已重构（kun-galgame-nuxt4，Go Fiber API），旧 `/api/galgame` 全部弃用（404"页面版本已过期"），爬虫全面迁移到 `/api/v1`
- 列表：`/api/v1/works?include_nsfw=true&page&limit`（默认排除 NSFW，必须带此参数；默认只列有资源的作品）
- 详情：`/api/v1/works/{id}`（display_name/aliases/intros/covers），资源：`/works/{id}/resources`（state=valid/expired、resource_platforms=win/and、content 为 slate 富文本）
- 下载链接改由 `POST /api/v1/galgame-resources/{rid}/downloads` 发放（download_urls/extraction_code/archive_password，匿名可用，cookie 不再是硬依赖）
- 页面 URL 仍为 `/galgame/{id}` 且 id 与旧 gid 对应，增量去重不受影响
- 备注（富文本→纯文本）沿用引流清洗 + 审计日志；仍只取百度网盘资源
- **平台判定**（用户 2026-09-24 确认）：由百度区全部有效资源平台的并集决定——全 PC / 全安卓 → 各选最新 1 条；凑齐 PC+安卓（单条双平台或多条各占一端）→ 划「PC+安卓」，PC/安卓各出 1 条下载链接。之前只看最新 1 条，分条资源会误判
- **发布者备注优先于平台标签**：备注写明"PC+安卓"（如"PC+安卓直装"）而资源标签只标一端的，按备注归「PC+安卓」
- 凑出的 PC+安卓两条资源 → 备注合并为一个【发布者备注】块（`PC：… / 安卓：…`）；解压密码不同时标注「解压码PC xxx ｜ 解压码安卓 xxx」

### 2026-09-24 (v17) 修复 4 项 bug + 移动云盘全面下线
- **修复**：纯安卓帖误显示"PC+安卓"双标签（`static/app.js` platformTags.android 原写成双标签）
- **修复**：卡片标题未转义直接进 innerHTML（前端 `escapeHtml()` + 导出侧 `html_lib.escape`，含 `<` 的标题不再破版）
- **修复**：自动备份改用 SQLite backup API（原来 shutil 直接拷运行中的 WAL 库，可能丢最近写入）
- **修复**：萌幻登录表单 action 相对路径转绝对 URL（urljoin）+ 详情页被踢回登录页时自动重登一次
- **移动云盘下线**：下载链接只获取百度网盘。解析器不再采集 139 链接（mobile_* 字段保留恒为 None）、鲲接口 `include_providers` 只拉 baidu、**五站"无有效链接→跳过"判断全部只认百度**、前端与导出 HTML 不再渲染移动云盘按钮/双网盘标签；数据库字段与历史数据不动，仅新增数据生效
- 顺带修正过期测试：`_test_site_pages.py` 站点勾选框 4→5（v9 加鲲后漏改）

### 2026-09-24 (推送) 备份仓库改名并同步最新改动
- **备份仓库 `TKPORL/-` 已在 GitHub 改名为 `TKPORL/tsinhohypqgj1`**（内容同一个，本地 remote `tsinho1` 已指向新址）
- 当日文档纠错（8 文件）提交为本地 master `0ed87ae`，并以 subtree merge 并入备份仓库 `2026-09-24/` 目录：main `72a401f` → `b287392`，完整提交历史保留
- 主仓库 `origin`（Tsinhohypqgj）本地仍领先 2 个提交未推送

### 2026-09-24 (文档) 文档纠错：导出说明补齐三份 + 萌幻域名统一
- **导出说明补齐**：v14 把导出拆成三份，但 README 的「使用指南 → 导出文件」与「项目结构 → output/」一直只写两份，本次补齐第三份「安卓下载」（并注明三类互不重叠、`unknown` 归 PC、时间戳命名、自动只留最近 10 次）
- **萌幻ACG 域名统一**：全项目 8 处 `bbs.acgrx.com` 改为 `bbs4.acgrx.com`（跨 README / 【项目全解】/【技术方案】/【项目架构】/【需求分析】/【git初始化】/ 需求文档）
  - 依据：代码自 `2416a66` 起一直用 `bbs4.acgrx.com`（`crawler/acgrx.py` + `config.yaml`）；`bbs.acgrx.com` 是 v0 早期错误假设，此前被文档误记为"主站"
- **顺带补记（同日早些时候）**：目标站点表补齐第 5 站**鲲Galgame**（kungal.com），特性描述 4 → 5 个站点，结构树 `crawler/` 补 `kungal.py`

### 2026-09-24 (备份) 代码与数据同步到备份仓库 TKPORL/-
- **归档 v14–v16 改动**：此前一批改动一直停留在工作区未提交，本次一次性提交到本地 master（`a4b1823`）。**未推送到原仓库 `Tsinhohypqgj`**，原仓库远端仍是 `5d59fbd`
- **新增备份仓库**：`git@github.com:TKPORL/-.git`，项目整体落在 **`2026-09-24/`**（日期命名）目录下，推送 commit `72a401f`
  - 做法：`git subtree add --prefix=2026-09-24 <本地仓库> master` —— **完整提交历史一并保留**（可回溯到 v0）
- **纳入备份**：全部源码 + 根目录 12 份 `.md` 文档 + `docs/`（含风格存档）+ `crawler/kungal.py` + `tools/` 5 个维护脚本 + 5 个回归测试 + `data/crawler.db`（11.9MB / 974 条）
- **排除**：`.env`（凭据）、`images/`（1.56GB）、`output/`（4.7GB）、`data/*.bak` 与 `data/backups/`、`logs/`、`__pycache__/`、`nul`（Windows 保留名，两处）、乱码名 `硬编码回退` / `纭紪鐮佸洖閫€`、一次性调试脚本与截图（`_dbg*` `_probe*` `_patch*` `_ui*.png` `_ex*.png` 等）、`.workbuddy/` `.freebuff/` `.ohmyagent/` `.monkeycode/`
- ⚠️ **注意（长期）**：`data/crawler.db` 已纳入版本控制（`.gitignore` 的 `acg_crawler/data/*.db` 被 `git add -f` 强制加入），今后每次数据库变动都会新增一份完整快照，仓库会持续变大 —— 建议只在需要备份节点时才提交数据库

### 2026-09-23 (v16) 修复：四站误加备注块 + 多图被挤压成一张
- **问题1（备注块）**：v11 加「备注折叠」时条件只写了 `if note_text`，**没加站点判断**，导致四个老站（`content` 装的是游戏简介）也显示备注块。用户明确：四站是管理员整理站，本来就没有备注；只有鲲Galgame（用户发帖型）才有发布者备注
  - 修复：`generator/__init__.py` 与 `static/app.js` 两处判定改为 `source == "鲲Galgame"`
  - ⚠️ 中间踩坑：第一版写成 `== "kungal"`（英文 key，永久不成立），因为数据库 `source` 存的是**中文名**
- **问题2（图片）**：v14 换 Origin 风格时把图片网格由 `auto-fill + max-height:250px` 改成 `auto-fit + height:220px`（去掉 max-height），多图被压成一条、**视觉上"只剩一张图"**。经查**图片一张没少**（图书馆 3.8 / 游戏姬 4.7 / 萌幻 12.1 张），是布局坏了
  - 修复：`generator/__init__.py` 与 `static/style.css` 两处恢复 `auto-fill` + `max-height:250px` + `height:100%`
- **验证**：重新导出全库 974 条 / 415 卡 —— 备注块仅 2 个且全属鲲Galgame（四站 0）；图片 3 张最多、最多 41 张；截图核对通过
- **新增文档**：`【项目全解】说明文档.md`、`【变更记录】修改日志.md`、旧风格存档 `docs/风格存档/旧版-粉紫渐变/`

### 2026-09-23 (v15) 备注引流清洗（通用规则）+ 清洗审计日志
- **问题**：鲲Galgame 发布者常在备注里塞引流——解压教程外链、网盘推广、QQ 群、推荐别的游戏列表，混在正式说明里影响阅读
- **清洗规则**（`crawler/kungal.py`，按特征组合识别而不是背句子，遇到新写法也能认）
  - `_promo_rule()` 7 类规则：①整行裸链接 ②命中外部站点域名（夸克/B站/docs.qq/slpeey/115/123pan 等）③社群·教程·工具汇总关键词 ④带链接 + 工具/教程类词 ⑤"请查看/详见/自取"收尾的引导句 ⑥纯 QQ 号 ⑦图片被丢弃后残留的单行"PC/安卓/游戏截图"
  - `_collapse_numbered_groups()`：编号列表整组丢弃，组上方引导句（"注：以下内容以推荐游玩顺序排列："）一并丢弃，避免留下半截话
  - `_strip_html()`：`<br />` 当换行、其余标签去掉、清零宽字符与方向控制符；简介字段同样过一遍
  - **零宽字符坑**：原文夹着 `\u200b`，`'PC\u200b'` 这类短行匹配不上 → 必须先清零宽/方向控制符再判断
- **复制剔除「网盘大小」**：备注块仍显示该行（给站长核对），但导出侧在 Python 里就把 `data-copy` 存成去掉该行的版本，前端 `copyNote` 再过滤一次
- **新增清洗审计日志** `logs/promo_clean/YYYY-MM-DD.jsonl`：每条记 `removed`（删了哪些行 + 命中的规则名）+ `suspect`（保留但仍含链接/长数字/联系方式的可疑行 = 漏删候选），用于复核误删漏删
  - 实测已抓到误删实例：含"苹果PC安装也有详细教程"的真实解压说明被规则③误杀，待调整阈值
- **新增回归测试** `_test_kungal_clean_audit.py`：覆盖文档样本表 + 规则名与布尔结果一致 + 审计内容 + 日志落盘
- **新增** `tools/recrawl_kungal_full.py`：重爬鲲Galgame，带 `--start` / `--end` 断点与范围控制（默认 1→342 全库，`--start 1 --end 10` 只跑 10 页）。**必须用脚本而不是界面按钮**——界面是常驻进程，Python 模块在启动时就加载完了，改了 `crawler/kungal.py` 后点按钮跑的还是旧代码
- **测试阶段口径**：当前是功能测试不是正式版——用户只需要看导出 HTML 的效果，**1 页足矣**，全库 342 页留到上线前
- **新增** `tools/export_kungal_preview.py`：按最新重爬批次取前 N 页导出预览（默认 1 页 20 条），用于查看清洗后的 HTML 效果
- **新增** `tools/list_output_cleanup.py` + `tools/trash_output_cleanup.py`：列出/清理 output/ 旧产物（白名单 + 干跑 + 分批 + 复核，一律走回收站可恢复）。本次清理实测 **3.2GB → 2.6MB**
- **澄清**：output/ 是可重建的导出产物，与 `data/crawler.db` / `images/` 无关；增量爬取的停止判断读数据库 `source`+`source_url`（连续 2 页全已入库才停），不读 output/

### 2026-09-23 (v14) 导出拆三份（PC / PC+安卓 / 安卓）+ 整体换深色编辑风
- **导出拆分为 3 个 HTML+zip**：`PC下载` / `PC+安卓下载` / `安卓下载`
  - 单安卓（`platform='android'`）**不再并入 PC+安卓**；三类互不重叠，`unknown` 归入 PC；某类无数据则不生成该 zip
  - 结果页平台筛选新增「安卓」页签；任务历史的「本批次安卓」按钮、分组色块上的「下载本组」同步支持
  - 实测：全库 993 条 → PC 512 / PC+安卓 427 / 安卓 54，计数与库内 `platform` 完全一致
- **整体视觉换成 Origin Financial 深色编辑风**（主界面 + 离线导出 HTML 同一套系统）
  - 表面色阶代替投影：`abyss #090a0b → obsidian #0f1011 → graphite #2e2e2e → steel #3f4041 → silver #cacaca`，**卡片不再有阴影**
  - 三声部字体：衬线（Playfair Display / Noto Serif SC）只做标题；无衬线（Geist / Inter）做 UI；等宽（Roboto Mono）做标签与数据，**一律大写带 0.182em 字距**
  - 彩色（`#847dff` iris / `#00b3dd` cyan / `#dd90d8` orchid / `#4b49aa` deep-iris）**只用于满幅分类色块**：平台分组头与导出卡片按 PC / PC+安卓 / 安卓 三色区分；cyan 只作进度条等数据信号
  - 主操作统一为**白底黑字**（带 → ），次操作为幽灵描边；输入框黑底细边；导航/芯片全部胶囊化
  - **删除**了原紫粉渐变（`#e056a0→#8b5cf6`）、发光描边、Emoji 统计（❤ → `LIKE`）、大圆角卡片
  - 顶栏改成吸顶玻璃条（`backdrop-filter: blur(24px)`），衬线上方加等宽大写眉标
  - 已按 390px / 560px / 900px 断点适配，并统一处理 `prefers-reduced-motion`

### 2026-09-23 (v13) 解压码标明所属网盘
- **问题**：鲲Galgame 一个游戏有百度/移动两条资源、两个人各自设了不同解压密码时，原来合成一串"open / afggacg"，看不出哪个密码对应哪个网盘
- **改法**（`KungalCrawler._build_unzip_code`）：
  - 两个网盘密码不同 → `百度网盘 open ｜ 移动云盘 afggacg`
  - 两个网盘密码相同 → `百度网盘/移动云盘 CC`（不重复写）
  - 只有一个网盘有 → `百度网盘 kungal`
- 复制出来即 `解压码：百度网盘 open ｜ 移动云盘 afggacg`；解压码/作弊码按钮加了 `title`，鼠标悬停也能先看到内容再决定要不要复制
- 已有 189 条鲲Galgame 记录重爬刷新

### 2026-09-23 (v12) 备注增强 + 排序口径改纯点赞降序
- **排序改口径**：全站（结果页 + 导出 HTML + 批次视图）由「双网盘置顶 → 点赞降序」改为**纯「点赞降序 → id 倒序」**
  - 原因：旧规则会让导出 HTML 到第 N 张时从高赞重新开始（用户看到"排到一半又重新排"），实为双网盘/单网盘两段拼接
  - 同步改了 `POST_ORDER_SQL` 与 `sort_posts`，`is_dual_netdisk` 保留但不再参与排序；`_test_sort_order.py` 已同步为新口径（全库断言"无分段重启"，全绿）
- **鲲Galgame 标题去掉大小**：标题只留【PC+安卓】这类平台标签，各网盘体积移到备注的「网盘大小」行
- **备注内容重排**：原名并入「别名」同一行（不再单列"其他名称"）；新增「网盘大小：百度网盘 9.09 GB ｜ 移动云盘 15 GB」一行
- **备注点击复制**：主界面与导出 HTML 的备注块整块可点，点击复制**完整备注**（含被折叠部分），右上角有"点击复制"提示，复制成功有反馈；键盘/鼠标均可
- **解压码按钮美化**（导出 HTML）：原来只有 2px 内边距 + 浏览器默认边框，看着像个裸框；现在是有复制图标、细边框、悬停高亮的按钮，点击后变绿并显示"已复制!"

### 2026-09-23 (v11) 卡片备注折叠 + kungal 末页/登录维护
- **卡片备注**：卡片新增可折叠的「备注」块（发布者说明：改后缀、解压工具、文件说明等），默认显示 3 行、超出才出现「展开」按钮；主界面（`static/app.js`）与离线导出 HTML（`generator/`）同步生效
  - 按组件规范实现：展开高度取实测值（不用固定 max-height 猜），收尾后清掉内联高度；箭头随状态旋转 180°；`aria-expanded` / `aria-label`（展开备注 / 收起备注）可读；键盘可触发；`prefers-reduced-motion` 下取消动画
  - 卡片在折叠分组里时量到高度为 0，改用 IntersectionObserver 等真正可见时再判定是否需要展开按钮
- **修复末页误判**：kungal 列表末页返回的空 JSON 太短，被基类"验证页检测"当成拦截页报错（`检测到验证页`）。kungal 改为自己发请求，不再套用该启发式
- **补漏**：结果页的「来源」筛选下拉此前漏了鲲Galgame（v9 只注册了爬取面板），已补上（实测筛选出 47 条）
- **登录维护**：新增 `tools/refresh_kungal_cookie.py`，一条命令自动走 NextMoe 登录并刷新 `.env` 里的 `KUNGAL_COOKIE`（42 秒跑通）。会话 cookie 约 90 天**滑动**有效，只要期间爬过就会自动续期
  - 已挂定时任务「刷新鲲Galgame登录cookie」：**每 60 天自动跑一次**（首次 2026-11-22 09:00，之后每 60 天），无需人工干预
- **说明**：kungal 列表本身不区分平台，抓的是"含百度/和彩云资源的全部游戏"，平台在解析时按资源标签划分（win→PC、and→安卓、两者都有→PC+安卓），结果页与导出按 PC / PC+安卓 分组（安卓沿用既有约定并入 PC+安卓）

### 2026-09-23 (v10) 鲲Galgame 改为 API 全量爬取（含需登录的下载链接）
- **背景**：v9 用游客身份解析 Nuxt payload，只能拿到"备注里明文写着"的链接，一半帖子被跳过
- **新数据链**（前三个接口公开，第四个需登录）：
  1. 列表 `/api/galgame?include_providers=baidu,caiyun&page=N&limit=20`（参数必须 snake_case，驼峰会被静默忽略）
  2. 游戏详情 `/api/galgame/{gid}` → 主名/原名/别名/主封面/简介/浏览/点赞
  3. 资源列表 `/api/galgame/{gid}/resource/all?galgame_id={gid}` → 每条资源的网盘、平台、大小、`status`(0有效/1失效)、备注、发布时间
  4. 下载详情 `/api/galgame-resource/{rid}/detail?galgame_resource_id={rid}` → `link[]`/`code`/`password`（**需登录**）
- **登录态**：账号体系是 NextMoe·未萌 OAuth，会话 cookie（`kungal_session`，约90天滑动有效）存在 `.env` 的 `KUNGAL_COOKIE`；失效时爬取日志会提示重新登录
- **挑选规则**：只保留百度网盘 / 和彩云(移动云盘)，每类只取一条——在"有效资源"里按发布时间取最新；两类都没有 → 跳过该游戏
- **标题**：主名 + 【平台 大小】（平台由所选资源的 `platforms` 推得：win→PC、and→安卓、两者都有→PC+安卓、模拟器→PC+安卓）
- **别名**：不进标题，写入正文（其他名称 + 别名列表）
- **解压密码**：取自接口的 `password` 字段，单独进"解压码"字段（卡片上就是复制按钮）；备注里对应的"解压密码"那行自动删除并重排序号，避免重复出现和删行留空位
- **备注**：动态原样保留（改后缀、用哪个解压工具、文件说明等），仅做轻度 markdown 清理（`**`、`###`、`> `、链接语法），语义不变
- **封面**：只取 1 张主封面（`effective_banner_url`）并下载到本地
- **失效链接**：`status==1` 的资源一律跳过
- **验证**：第1-2页 40 个游戏 → 40 条入库 / 0 跳过 / 0 失败，字段（双网盘链接、提取码、解压码、平台、大小、日期、封面）均正确

### 2026-09-23 (v9) 新增第5站点：鲲Galgame（kungal.com）
- **新增爬虫** `crawler/kungal.py`：鲲Galgame（kungal.com，开源 galgame 论坛）接入为第 5 个数据源
- **爬取方式与 WordPress 站点完全不同**：
  - 列表走公开 JSON API `/api/galgame?include_providers=baidu,caiyun&page=N&limit=20`，服务端已过滤"含百度网盘或移动云盘(彩云)资源的游戏"（约3400个）。注意参数是 snake_case，驼峰形式会被 API 静默忽略（不过滤）
  - 详情页是 Nuxt SSR，资源备注文本（含网盘链接+提取码）内嵌在 `<script id="__NUXT_DATA__">` 的扁平 JSON 中，直接抽取含 `pan.baidu.com` / `yun.139.com` 的字符串后复用 `extract_links_multi` 解析，**无需登录**
  - 总页数由 API total 计算（约171页），站内元数据（浏览量/点赞/平台/资源更新时间）直接来自列表 API，不再解析 DOM
- **平台映射**：kungal 的 `windows/mac→pc`、`app/android→android`、`emulator→pc_android`（多值组合取并集，模拟器归入PC+安卓）
- **URL 清洗**：资源备注常用 markdown 包裹链接（`<url>`、`[文字](url)`），提取后剥离尾部 `>)\]}` 等闭合字符
- **注册接入**：`crawler/__init__.py`（CRAWLERS + SITE_NAMES）、`templates/index.html`（站点勾选行）、`static/app.js`（面板名称）
- **验证**：第1页 20 帖 → 10 条入库（双网盘链接+提取码+图片本地化）、10 条跳过（游客可见资源只有夸克等非目标网盘）、0 失败。部分帖子在列表 API 匹配了 baidu/caiyun 但详情页游客视图拿不到对应链接，由引擎的"无链接跳过"逻辑兜底

### 2026-09-20 (v8) 结果排序：双网盘置顶 + 点赞降序
- **需求**：双网盘（百度 + 移动云盘都有）的帖子要排在最顶部，组内按点赞降序
- **最终规则**：`双网盘优先 → 点赞降序 → id 倒序`。注意这是**双网盘为第一优先**：双网盘最低 0 赞也排在 143 赞的单网盘前面（用户已确认此取舍）
- **统一口径**：新增 `database.DUAL_NETDISK_SQL` / `POST_ORDER_SQL` / `is_dual_netdisk()` / `sort_posts()`，SQL 侧与 Python 侧共用同一判定，避免两边排序不一致
- **改动位置**：
  - `app.py` → `api_posts_grouped`（结果页）、`_fetch_filtered_posts`（筛选导出取数）
  - `database/__init__.py` → `get_posts`、`get_posts_by_crawl_id`
  - `generator/__init__.py` → `export_posts` / `export_posts_filtered` 改用共享的 `sort_posts()`（原来是只按点赞排，会与页面不一致）
- **口径核对**：`baidu_link + mobile_link` 的判定与前端渲染网盘按钮的 `download_items_json` 口径全库 804 条**零出入**
- **验证**：`_test_sort_order.py` 全通过——全库形状、双网盘块边界、SQL 与 Python 一致、结果页三页每组有序且跨页连续无重复、批次视图、导出 HTML 卡片序列
- **遗留观察**：`萌幻ACG` 的 192 条 likes 全为 0（该站点点赞解析未生效），会永远沉底，见交接文档「八、风险与问题」

### 2026-09-20 (v7) 爬取控制：站点选择合并 + 每站独立页码
- **去掉重复的站点选择**：「页码范围」里那个 `全部站点/ACG游戏姬/…` 下拉是**废弃死控件**——`static/app.js` 从未读取它（全项目只在 index.html 出现过一次），点它没有任何作用。已删除该控件与整块 `#pageGroup`，站点选择现在只有一处
- **「目标站点」改造为每站一行**：`☑ 站点名` + `第 [起] 至 [止] 页`。勾选哪个就爬哪个，页码只对该行生效；非「按页码爬取」模式自动隐藏页码输入并切换说明文案
- **新功能：每站独立页码范围**（用户需求）——各站更新速度不同，把更新慢的站结束页调小，就不会翻到一堆旧内容。前端提交 `site_pages={siteKey:{start,end}}`；`crawler.crawl_by_page()` 签名由 `(sites, start_page, end_page)` 改为 `(site_pages, speed_name, skip_existing)`，逐站使用各自的 `range(start, end+1)`
- **修掉一个连带 bug**：`document.querySelectorAll('.checkbox-group input:checked')` 会把「跳过已入库的帖子」那个 checkbox 也当成站点（值 `"on"`）提交，后端 `_init_site_states` 据此建了 `on` 这个幽灵站点状态，前端多渲染一个空面板。已改为 `#targetSites .site-page-row` 作用域选择
- **后端加固**：`api_start_crawl` 新增站点白名单（只认 `SITE_NAMES` 四个 key）、页码夹到 `[1, 999]`、结束页早于起始页时按起始页处理、全非法站点直接返回 error 不启动线程、未知 `mode` 直接拒绝；`_parse_site_pages()` 同时兼容旧的 `sites + start_page/end_page` 调用形式
- **验证**：`_test_site_pages.py` 14 项断言全通过（按站传参 / 非法 key 丢弃 / 越界夹取 / 倒置修正 / 旧格式兼容 / 未知模式拒绝 / 引擎入口校验 / 死控件已移除）；浏览器实测 1280px、390px、320px 三个断点布局正常

### 2026-09-20 (v6) 结果页改为点赞降序
- **问题**：网页「爬取结果」面板的帖子顺序与点赞无关，点赞 15 和点赞 3 的帖子混在一起，看起来像随机排列
- **根因**：结果页数据接口 `GET /api/posts_grouped` 的 SQL 排序键是 `发布日期 DESC, id DESC`，全程没有用 `likes`
- **修复**：`api_posts_grouped` / `database.get_posts` / `database.get_posts_by_crawl_id` 三处 ORDER BY 统一改为 `COALESCE(likes,0) DESC, id DESC`（点赞高的在最上；同赞数按 id 倒序兜底，保证分页不跳条、不重复）
- **未改动**：离线导出 HTML（`generator.export_posts` / `export_posts_filtered`）本来就已按点赞降序，无需修改
- **验证**：Flask 测试客户端实测——全部/PC/PC+安卓三组点赞序列均为严格降序；第 2 页与第 1 页衔接连续（16→…→9）；批次视图（batch=56，197 条）同为降序

### 2026-09-08 (v5) 长期化健壮性
- **清理孤儿图片目录**：历史爬过又批量删除的帖子残留 375 个孤儿目录共 395.9MB，先备份到 `images/orphans-backup-20260908/` 后删除（备份可手动清理）
- **删除帖子同步清图片**：[api_delete_post](/D:/Tsinho%E6%96%87%E4%BB%B6%E5%A4%B9/%E6%96%B0Tsinho%E9%BB%84%E6%B2%B9%E7%88%AC%E5%8F%96%E5%B7%A5%E5%85%B7/acg_crawler/app.py) 和 [api_batch_delete](/D:/Tsinho%E6%96%87%E4%BB%B6%E5%A4%B9/%E6%96%B0Tsinho%E9%BB%84%E6%B2%B9%E7%88%AC%E5%8F%96%E5%B7%A5%E5%85%B7/acg_crawler/app.py) 删除 DB 行后同步清理对应 images/{source_id}/ 目录，从根因上阻止新孤儿产生
- **redownload 加进度与取消**：新增 `/api/redownload_status`（查询进度）与 `/api/cancel_redownload`（中途取消）；改为每 20 条事务批量 commit，扫描速度明显加快
- **API 限速**：[api_posts](/D:/Tsinho%E6%96%87%E4%BB%B6%E5%A4%B9/%E6%96%B0Tsinho%E9%BB%84%E6%B2%B9%E7%88%AC%E5%8F%96%E5%B7%A5%E5%85%B7/acg_crawler/app.py) 的 limit clamp 到 [1, 500]，非法值回落默认；[api_posts_grouped](/D:/Tsinho%E6%96%87%E4%BB%B6%E5%A4%B9/%E6%96%B0Tsinho%E9%BB%84%E6%B2%B9%E7%88%AC%E5%8F%96%E5%B7%A5%E5%85%B7/acg_crawler/app.py) 新增 offset/limit 分页
- **平台判定修复**：acgrx/acgll 从"列表页分类优先"改为"标题优先"，避免 PC+安卓 帖子被列表页分类误判为纯 PC
- **日志落盘**：所有 `log_callback` 同步追加到 `logs/{YYYY-MM-DD}.log`（保留 30 天），与 console log_store 并存
- **自动备份**：启动时距上次备份 > 7 天自动备份一次到 `data/backups/crawler-YYYYMMDD-HHMMSS.db`，保留最近 10 份
- **start.bat 修复**：直接使用 `C:/Python314/python.exe` + 启动前检查 .env/.gitignore/data 目录是否就绪
- **回归验证**：8 大项回归测试一次通过（py_compile / parser 单元 / Flask 接口 / 删除同步清理 / batch_delete 类型安全 / redownload 进度 / 日志落盘 / 自动备份）

### 2026-09-08 (v4) 多链接解析与云名规范化
- **多链接结构**：识别每个网盘下 PC / 安卓 双链接。原版 `extract_links` 全文只取一条百度 + 一条移动云盘，导致 ACG游戏姬 PC+安卓 帖子的安卓版链接丢失。新增 `extract_links_multi`：根据链接前面的 `PCC/AZC/PC/AZ` 云名标签识别平台，返回完整 `download_items_json` 列表（最多 4 条），保留旧字段向后兼容
- **数据库迁移**：posts 表新增 `download_items_json TEXT`，`init_db` 用 ALTER TABLE 兼容旧库；`insert_post` 同步新字段
- **标题云名规范化**：新增 `fix_title_cloud_name`，把 `【PCC数字】/【AZC数字】/【CCC数字】/【AC数字】/【PC数字】/【PCC 数字】` 等所有平台前缀变体统一为 `【C数字】`，不影响 `【PC+安卓 9.0G】` 平台标签和正文
- **四站爬虫接入**：ACG游戏姬/萌幻ACG/ACG图书馆/ACG俱乐部 全部改用 `extract_links_multi` 并写入 `download_items_json`
- **前端与导出卡片**：每个帖子最多渲染 4 个网盘按钮（百度PC / 百度安卓 / 移动PC / 移动安卓），缺哪个就少渲染哪个；主页面和离线导出HTML同步生效
- **历史数据回填**：609 条历史帖子的标题云名就地 UPDATE（75 条 PCC → C）；从本地 content 重新解析 `download_items_json`，577 条成功（其中 87 条拿到完整 4 项链接）。备份保留为 `data/crawler.db.pre-multi`
- **根因**：用户截图（4 项链接只显示 1 项）= 数据模型 + 单条解析的双重限制，不是平台识别错

### 2026-09-08 (v3) 大修版
- **四站并行 + 独立窗口**：选择几个站点就显示几个独立状态面板，各自展示状态/进度/成功/跳过/失败/独立日志，同时爬取互不干扰
- **速度档位**：新增稳定/平衡/快速三档（默认平衡），非法值自动回落
- **站内详情并发**：每站详情页并发解析（ACG游戏姬3、其余站点2），明显提速
- **图片灯箱**：主界面和离线导出HTML均支持点击图片放大、左右切换、键盘导航、Esc关闭
- **数据清理**：修复萌幻ACG 261条无网盘链接历史脏数据（备份后清理，卡片不再缺下载按钮）
- **平台修复**：ACG俱乐部unknown平台按正文标签回退识别，全库unknown归零
- **任务状态**：异常退出重启后遗留running任务自动标记为"已中断"，前端显示全部6种状态
- **导出修复**：每次导出前清空旧图片目录，不再混入历史残留图片（744MB→1.06MB）
- **链接提取**：支持HTML实体反转义（&amp;等），正则覆盖更全
- **稳定性**：SQLite启用WAL+写入锁+锁重试；连续失败指数退避+熔断；验证页检测
- **安全**：图片代理接口增加SSRF防护（拒绝环回/私有/file协议）；Flask默认关闭debug重载

### 2026-09-07 (v2)
- 标题括号统一：所有标题[]改为【】，包括标签、大小、云名
- 标签自动检测：标题中平台/大小前的额外标签（官中版、AI汉化、步兵版等）自动移到开头【】
- 图片高度增大：卡片图片从160px增加到250px
- 解压码/作弊码改为按钮：点击按钮复制"解压码：xxx"到剪贴板
- 双网盘排序优化：所有双网盘帖子置顶显示，移除"低热度下沉"规则
- 置顶帖过滤：各站自动跳过教程、合集、工具等置顶帖
- 残留斜杠修复：【PC/3.87G】→【PC 3.87G】
- 萌幻ACG标题自动补平台：【12.53GB】→【PC 12.53GB】
- 移动云盘链接修复：正则支持完整URL（含/#/参数）
- 导出修复：copyText按钮现在正确复制data-copy内容（而非按钮文字）
- 导出修复：导出"全部"平台时返回PC+安卓文件（而非仅PC）
- 数据库修复：get_posts_by_crawl_id排序和平台过滤与主查询一致
- 全项目审查：修复parser中fix_title_tags对【】括号的处理

### 2026-09-07 (v1)
- 修复标题双[PC+安卓]和PCC前缀问题
- 修复评论数据提取
- 移除"仅安卓"分类，全部归入PC+安卓
- 导出改为zip格式（HTML+图片打包）
- 优化图片下载（直连优先）
- 添加ACG俱乐部爬虫支持

### 2026-09-06
- 实现4个站点爬虫
- 实现Web界面
- 实现导出功能
- 添加图片下载和本地存储

## 许可证

仅供个人学习研究使用，请勿用于商业用途。
