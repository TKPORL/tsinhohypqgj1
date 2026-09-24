# 鲲 Galgame（kungal.com）备注引流清洗方案

## 一、问题背景

### 1.1 发现的问题
用户在发布资源到鲲 Galgame 论坛时，常在备注中添加引流内容，例如：
- ⚠️ 教程链接 + 网盘推广：`◆！先看解压教程【pan.quark.cn/s/b85f2556d1dc】`
- 📱 社群引导：`欢迎加群 581561231(工具&教程&汇总群)`
- 🔗 外链导流：`关于游戏的详细介绍请查看 <https://www.slpeey.com/...>`
- 🎮 其他游戏推荐列表：`1. Role player：XXX！（链接）`, `2. 山掛姐妹：XXX!`
- 💻 零宽字符干扰：`PC\u200b`、`安卓\u3000` 等不可见字符伪装

这些内容混在正式备注里，影响用户体验，且可能带来安全风险。

### 1.2 需求目标
1. **自动过滤引流内容**：识别并删除所有形式的引流行
2. **保留有用信息**：保留版本说明、解压方式等真正有价值的备注
3. **兼容性强**：能够识别新的引流方式，不依赖硬编码句子
4. **用户可控**：备注块中显示「网盘大小」供核对，但复制时不包含该行

---

## 二、技术实现

### 2.1 核心函数 `_is_promo_line()`

> 实现说明（2026-09-23 更新）：为支持清洗审计，实际判定逻辑已抽到 `_promo_rule()`，
> 命中返回规则名（如 `②外部域名`），未命中返回 `None`；
> `_is_promo_line(line)` 只是 `return _promo_rule(line) is not None` 的兼容壳。
> 下面伪代码里的 `return True` 对应 `return "②外部域名"`。

#### 2.1.1 设计思路
使用 **特征组合识别** 而非背诵具体句子，通过以下 7 类通用规则判断：

| 规则编号 | 检测目标 | 判定逻辑 |
|---------|---------|---------|
| ① | 整行裸链接 | 匹配 `<url>`/`(url)` 包裹的纯 URL |
| ② | 非目标域名 | 命中夸克、B 站、docs.qq、slpeey、kungal-resource 等外部站点 |
| ③ | 社群关键词 | 包含"加群/QQ 群/微信群/交流群/粉丝群/群号" |
| ④ | 工具/教程类 | 域名是目标网盘但附带"工具/教程/模拟器/汇总"等词 |
| ⑤ | 引导句 | 以"请查看/详见/如下/自取"收尾的句子 |
| ⑥ | QQ 号码 | 匹配 `[1-9]\d{6,11}` 格式的数字串 |
| ⑦ | 残留平台名 | 图片被丢弃后单行的"PC/安卓/游戏截图" |

#### 2.1.2 特殊处理
- **零宽字符清除**：先移除 `\u200b-\u200f` 等不可见字符，避免短行匹配失效
- **编号列表整组删除**：如果列表中某项命中，则整组连同上方的引导句（如"注：以下内容以推荐游玩顺序排列："）一并删除

```python
def _is_promo_line(line):
    """判断一行是否是发布者引流内容（通用规则）"""
    # 清除零宽字符和方向控制符
    s = re.sub(r"[\u200b-\u200f\u202a-\u202e\ufeff]", "", line or "")
    s = re.sub(r"[\u00a0\u3000]", " ", s).strip()
    if not s:
        return False
    
    # 规则 ①：整行裸链接
    if _BARE_LINK.match(s):
        return True
    
    # 规则 ②：命中外部域名
    low = s.lower()
    if any(d in low for d in _PROMO_DOMAINS):
        return True
    
    # 规则 ③/④：社群 + 工具/教程类词
    if any(h in low for h in _PROMO_HINTS):
        return True
    
    # 规则 ⑤：引导句收尾
    if _LINK_CTX.search(s) and any(w in low for w in _LINK_CTX_WORDS):
        return True
    if _LEADOUT_TAIL.search(s):
        return True
    
    # 规则 ⑥：QQ 号
    if re.fullmatch(r"[1-9]\d{6,11}", s):
        return True
    
    # 规则 ⑦：残留平台名
    if _BARE_PLATFORM.match(s):
        return True
        
    return False
```

#### 2.1.3 待过滤的外部域名列表
```python
_PROMO_DOMAINS = (
    "pan.quark.cn", "quark.cn", "aliyundrive.com", "alipan.com",
    "115.com", "115cdn", "123pan.com", "lanzou", "xunlei.com",
    "uc.cn", "tianyiyun", "cloud.189", "slpeey", "kungal.com/galgame-resource",
    "bilibili.com", "b23.tv", "youtube.com", "youtu.be", "docs.qq.com",
)
```
> 以上为 `crawler/kungal.py` 中的实际值（2026-09-23 核对一致）。
> 注意目标网盘（baidu.com、yun.139.com）**不在**列表里，不会被误伤。

### 2.2 编号列表整组处理 `_collapse_numbered_groups()`

#### 2.2.1 问题场景
发布者常这样推广其他游戏：
```
1. 某游戏 A（链接）✓ 已过滤
2. 某游戏 B（链接）✓ 已过滤
3. 某游戏 C          ✗ 没有链接，单看不像引流
注：以下内容以推荐游玩顺序排列： ← 这句单独留着很奇怪
```

#### 2.2.2 解决方案
遍历整个编号列表，只要有一项命中引流规则，就标记整组为「需删除」，并额外删除组上方的引导句：

```python
def _collapse_numbered_groups(lines, keep):
    i = 0
    while i < len(lines):
        if not _NUMBERED_LINE.match(lines[i]):
            i += 1
            continue
        j = i
        while j < len(lines) and _NUMBERED_LINE.match(lines[j]):
            j += 1
        # 检查组内是否有任一需要删除的行
        if any(not keep[k] for k in range(i, j)):
            for k in range(i, j):
                keep[k] = False
            # 顺便删除上方的引导句
            k = i - 1
            while k >= 0 and not lines[k].strip():
                k -= 1
            if k >= 0 and _GROUP_LEADIN.search(lines[k]):
                keep[k] = False
        i = j
```

### 2.3 HTML 标签清理 `_strip_html()`

#### 2.3.1 问题
原版备注可能夹带：
- `<br />` 换行符
- `<span>`、`<div>` 等标签
- 零宽字符导致文本异常

#### 2.3.2 处理
- `<br />` → 转为实际换行符
- 其余 HTML 标签 → 直接删除
- 零宽字符 → 统一清理

```python
def _strip_html(text):
    text = re.sub(r"<br\s*/?>", "\n", text or "", flags=re.IGNORECASE)
    text = re.sub(r"</?[a-zA-Z][^>]*>", "", text)
    text = re.sub(r"[\u200b-\u200f\u202a-\u202e\ufeff]", "", text)
    return text
```

### 2.4 清洗审计日志 `_audit_clean()`

#### 2.4.1 为什么需要
爬完一次全库几千条，只看结果分不清"删对了"还是"删过头"。清洗是**不可逆**的（删掉的行不入库），
没有审计就没有调整规则的依据。

#### 2.4.2 实现
把 `_is_promo_line()` 拆成 `_promo_rule()`（返回命中的规则名，如 `②外部域名`）+
`_is_promo_line()`（`_promo_rule() is not None`）。`_optimize_note(note, password, audit)` 多接一个
可选 `audit` 字典，逐行记下：

| 字段 | 内容 | 用途 |
|------|------|------|
| `removed` | `{rule, line}` 列表 —— 被丢掉的行 + 命中的规则名 | 复核**误删**：一眼看出是哪条规则下手过重 |
| `suspect` | `{line}` 列表 —— 保留但仍含链接 / 邮箱微信 / 6-12 位数字 / 群·公众号·联系·推广 等特征的行 | 复核**漏删**：可能是新增的引流写法还没被规则覆盖 |

`parse_detail()` 里每个网盘备注各建一个 `audit`（带 `label` 区分百度/移动），
一条记录一处写到 `logs/promo_clean/YYYY-MM-DD.jsonl`：

```json
{"time":"2026-09-23 12:32:23","gid":"66","title":"…【安卓】","notes":[
  {"label":"移动云盘","removed":[
     {"rule":"⑤引导句收尾","line":"lz4解压工具如下"},
     {"rule":"①整行裸链接","line":"https://yun.139.com/shareweb/#/w/i/…"}],
   "suspect":[]}]}
```

设计约束：
- **只写日志，不参与业务判断**，写失败（`OSError`）只打一行提示，不能拖垮整轮爬取
- `suspect` 每条备注最多记 `_SUSPECT_MAX = 5` 行，防止个别超长备注把日志撑爆
- 多线程写入用 `_clean_log_lock` 串行化，追加模式，不覆盖历史

#### 2.4.3 真机首次发现（2026-09-23，gid=66）
规则 ③ 把两条**真实的解压说明**误杀（因为它们含"教程"二字）：

```
✅ 注意‼️网课MP4就是游戏！无视网盘里的无关文件，遇到文件夹就打开！
   解压码在教程里有文档标注‼️KR/ONS模拟器版均支持苹果/安卓！
✅ 先选择"无损/原画"下载后将后缀MP4改成zip再解压‼️苹果PC安装也有详细教程，小白也能玩！
```

这两行对用户是有用信息（139 云盘把游戏伪装成 MP4 是常态），属于**误删**。
判定规则是否放宽需要先看全库统计，故暂不改动，先让审计日志把实例攒下来。

---

## 三、应用范围

### 3.1 爬虫层（crawler/kungal.py）
- `_optimize_note()` 函数调用 `_is_promo_line()` 进行实时过滤
- `_build_content()` 中对简介字段也应用 `_strip_html()` 清理

### 3.2 前端展示（static/app.js + templates/index.html）
- 备注块折叠显示，默认 3 行
- 点击备注可复制完整内容
- **「网盘大小」行可见但不可复制**（满足站长核对需求）

### 3.3 导出 HTML（generator/__init__.py）
- Python 侧预处理 `data-copy` 属性，剔除「网盘大小」行
- 前端 copyNote 函数二次校验
- HTML 标签全部清理完毕

---

## 四、验证结果

### 4.1 样本测试
| 类型 | 示例 | 处理结果 |
|-----|------|---------|
| 引流行 | `◆！先看解压教程【pan.quark.cn/s/b85f2556d1dc】` | ❌ 删除 |
| QQ 群引导 | `欢迎加群 581561231` | ❌ 删除 |
| 外部链接 | `<https://www.slpeey.com/%E3%80%90PC+%E5%AE%89%E5%8D%93%E3%80%91>` | ❌ 删除 |
| 编号游戏列表 | `1.xxx ！（链接）\n2.xxx！（链接）\n3.xxx` | ❌ 整组删除 |
| 有用信息 | `推荐使用 Bandizip` | ✅ 保留 |
| 版本说明 | `甜蜜夏日系列合集，包含以下内容` | ✅ 保留 |
| 解压方式 | `lz4 解压工具` | ✅ 保留 |

### 4.2 真机测试
重爬 **5 条含引流痕迹的真实条目**，对比前后：
- 旧脏行：**24 条**
- 新残留：**0 条** ✓

预览文件：`output/预览-备注清洗/预览 - 备注清洗.html`

### 4.3 回归测试（2026-09-23 新增）
`acg_crawler/_test_kungal_clean_audit.py`，运行方式：

```bash
cd acg_crawler && C:/Python314/python.exe _test_kungal_clean_audit.py
```

覆盖 33 项断言，全绿：

| 组别 | 断言内容 |
|------|---------|
| 样本表 | 文档 4.1 的删除/保留样本逐条核对 |
| 一致性 | `_is_promo_line()` 的布尔值与 `_promo_rule()` 是否返回 `None` 完全对应 |
| 编号组 | 整组连坐 + 组上方引导句丢弃；正常编号列表（章节）不误删 |
| 审计内容 | 被删行都有规则标注；`suspect` 不含被删行；全保留时 `removed` 为空 |
| 已知缺口 | 编号列表里挂**域名库外**的外部链接 → 规则不覆盖，行会被保留（固化为漏删候选，防止以后误判已覆盖） |
| 日志落盘 | JSONL 生成、含本次记录、带网盘分级、含删除明细 |

其中「已知缺口」那条是本次测试逼出来的真实发现，不是设计遗漏的掩饰：
`1. 某游戏A https://某站/video/BV1xx` 这种**不在域名库、又不以引导词收尾**的行，
现有规则判不出来。这类行现在会进 `suspect`，留待人工复核。

---

## 五、限制与注意事项

### 5.1 已知限制
- **简介段落中的 `<br />`**：已通过 `_strip_html()` 处理，但部分原始数据可能仍残留
- **封面选择**：本方案仅处理文字备注，游戏封面是否露点需另行筛选
- **数据库依赖**：功能依赖爬虫爬取并入库，新爬数据才会生效
- **★ 规则 ③ 偏激进（待定）**：只要行内出现"教程/工具汇总/模拟器"等词就整行丢弃，
  会误杀混在里面的真实解压说明（见 2.4.3 的 gid=66 实例）。
  是否放宽（例如"命中 ③ 但行内不含链接且不含社群词则保留"）需要全库统计后再定，
  **当前保持原规则不动**，避免一边爬一边改口径导致数据前后不一致。
- **★ 域名库外链接不覆盖**：不在 `_PROMO_DOMAINS` 里、又不以引导词收尾的外部链接判不出来，
  这类行现在会进 `suspect` 日志，需人工复核（测试已固化该缺口）。
- **审计日志只写不读**：`logs/promo_clean/*.jsonl` 目前只累积，尚无自动汇总脚本；
  误删/漏删率需要人工或用脚本统计。

### 5.2 扩展建议
1. **动态更新域名库**：将 `_PROMO_DOMAINS` 提取到配置文件或数据库表中
2. **用户自定义规则**：允许用户添加额外的引流模式正则表达式
3. **黑白名单机制**：对某些域名/关键词设置白名单豁免
4. **审计汇总脚本**：把 `removed` 按规则名和出现频次聚合，直接输出"哪条规则删得最多、
   哪些行反复出现"，比逐条翻 JSONL 高效得多

---

## 六、相关文件清单

| 路径 | 功能 |
|-----|------|
| `acg_crawler/crawler/kungal.py` | 核心爬虫逻辑，含 `_promo_rule`/_is_promo_line/_collapse_numbered_groups/_strip_html/_audit_clean |
| `acg_crawler/_test_kungal_clean_audit.py` | 清洗规则 + 审计日志回归测试（33 项断言） |
| `acg_crawler/tools/recrawl_kungal_full.py` | 全库重爬脚本（1→342 页，`--start` 断点续爬，`--speed` 选档） |
| `acg_crawler/logs/promo_clean/YYYY-MM-DD.jsonl` | 清洗审计日志（removed / suspect） |
| `acg_crawler/logs/recrawl_kungal_*.log` | 重爬过程日志 |
| `static/app.js` | 前端备注折叠与复制逻辑 |
| `static/style.css` | 备注块样式定义 |
| `generator/__init__.py` | 导出 HTML 生成器，含 data-copy 预处理 |
| `tools/refresh_kungal_cookie.py` | 刷新登录 cookie 脚本 |
| `output/预览 - 备注清洗/预览 - 备注清洗.html` | 清洗效果预览（含 NSFW 示例） |

---

## 七、后续待办

> **测试阶段口径**（2026-09-23 用户明确）：当前是功能测试，**不是正式版**。
> 用户原话："我只需要看一下爬取后生成的 HTML 效果如何即可"，**1 页足矣**。
> 全库重爬（342 页 / 6840 游戏）留到正式上线前再做。

1. [已完成 2026-09-23] 测试用重爬鲲 Galgame
   - 实际跑到第 161 页（入库 2932 条）时按用户要求停止；远超 10 页需求，但不影响测试结论
   - 这 2932 条全为新清洗规则产物，可直接用于封面筛选与预览版生成
   - 只跑 10 页的命令：`--start 1 --end 10`（脚本已支持 `--end`，0=站点末页）
   - **不要用界面按钮**：5000 端口的 Flask 进程是 08:42 启动的，早于 `kungal.py` 的 10:55 改动，
     点按钮跑的是旧清洗代码
   - 中断后：`--start <下一页>` 续爬（入库是 `INSERT OR REPLACE`，不会重复）
   - 速度实测：balanced 1.83 秒/条；fast 0.98 秒/条
2. [x] 生成清洗效果预览 HTML（2026-09-23 完成，用户已确认"这样没有问题"）
   - 命令：`C:/Python314/python.exe tools/export_kungal_preview.py --pages 1`（默认 1 页 = 20 条）
   - 用户口径：**只需看效果，1 页足矣**，不必 10 页更不必全库
   - 交付：`output/PC下载-测试预览-20260923-141555/`（HTML + zip）
   - 自检结果：夸克/B站/docs.qq/115/蓝奏/迅雷残留全 0，邮箱 0，QQ 号 0
3. [x] 清理 output/ 下旧产物（2026-09-23 完成）
   - 实测 output/ 原为 **3.2GB**（非此前记录的 1.2GB），18 项旧测试产物全部移入回收站
   - 清理后 output/ **2.6MB**，保留 `PC下载-测试预览-141555`（效果基准）+ `PC.html`/`仅安卓.html`（9/6 老 demo）
   - 工具：`tools/list_output_cleanup.py`（出清单）+ `tools/trash_output_cleanup.py`（移回收站，白名单+干跑+分批）
   - **重要澄清**：output/ 是可重建的导出产物，与原始数据（`data/crawler.db` + `images/`）无关；
     增量爬取判断依据是数据库里的 `source` + `source_url`（见 `crawler/__init__.py` `_url_exists`），不读 output/
   - 清单存档：`logs/output_cleanup_20260923-142429.md`
4. [已完成 2026-09-23] 补充错误日志记录，方便追踪误删/漏删案例
   - 交付物：`_audit_clean()` + `logs/promo_clean/*.jsonl` + 回归测试 33 项全绿
   - **顺序说明**：原排在最后，实际提前到重爬之前做——日志必须在爬的时候产生，
     否则爬完 6840 条才发现没记"删了什么"，要再爬一遍才能拿到审计数据
5. [新增] 汇总审计日志，给出各条规则的删除频次与误删实例，据此决定规则 ③ 是否放宽（见 5.1 ★）
6. [新增] 把 `output/` 旧产物与 `logs/promo_clean/` 的保留策略写进文档（目前都无限增长）
7. [待正式上线前] 全库重爬 342 页，让新规则覆盖全部存量数据

---

*文档版本：v1.2  
最后更新：2026-09-23  
维护者：Tsinho*

## 更新记录

| 版本 | 日期 | 改动 |
|------|------|------|
| v1.0 | 2026-09-23 | 初版：7 类通用规则 + 编号列表整组处理 + HTML/零宽清理 + 复制剔除网盘大小 |
| v1.1 | 2026-09-23 | 新增 2.4 清洗审计日志（`_promo_rule`/`_audit_clean`，removed+suspect）；补 4.3 回归测试；5.1 增补两条已知限制（规则③偏激进、域名库外链接不覆盖）；六 文件清单补 3 项；七 待办更新状态并调换 #4 的执行顺序 |
| v1.2 | 2026-09-23 | 更正测试口径为 **1 页足矣**（用户原话）；#2 改为"生成清洗效果预览 HTML"（新增 `tools/export_kungal_preview.py`），#3 完成 output/ 清理（实测 3.2GB→2.6MB，18 项移入回收站，新增 list/trash 两个脚本），并澄清 output/ 与原始数据、增量爬取的判断依据无关 |
