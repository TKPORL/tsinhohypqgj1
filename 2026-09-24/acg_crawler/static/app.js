document.addEventListener("DOMContentLoaded", function() {
    // 导航切换
    const navBtns = document.querySelectorAll(".nav-btn");
    const panels = document.querySelectorAll(".panel");
    navBtns.forEach(btn => {
        btn.addEventListener("click", function() {
            navBtns.forEach(b => b.classList.remove("active"));
            panels.forEach(p => p.classList.remove("active"));
            this.classList.add("active");
            document.getElementById("panel-" + this.dataset.panel).classList.add("active");

            if (this.dataset.panel === "result") loadPosts();
            if (this.dataset.panel === "history") loadHistory();
            if (this.dataset.panel === "export") loadExportInfo();
            if (this.dataset.panel === "cleanup") loadCleanupInfo();
        });
    });

    // 爬取模式切换
    const modeRadios = document.querySelectorAll('input[name="crawlMode"]');
    const dateGroup = document.getElementById("dateGroup");
    const targetSites = document.getElementById("targetSites");
    const siteHelp = document.getElementById("siteHelp");
    const incrementalGroup = document.getElementById("incrementalGroup");
    const dedupGroup = document.getElementById("dedupGroup");
    const SITE_HELP_BY_PAGE = "勾选哪个站点就爬哪个，页码范围只对勾选的站点生效。各站更新速度不同，把更新慢的站点结束页调小，就不会翻到旧内容。";
    const SITE_HELP_NO_PAGE = "当前模式下页码设置不生效，只需勾选要爬的站点。";
    modeRadios.forEach(radio => {
        radio.addEventListener("change", function() {
            dateGroup.classList.add("hidden");
            incrementalGroup.classList.add("hidden");
            targetSites.classList.add("pages-hidden");
            // 去重开关只对按页码/按日期生效，增量模式自带去重
            dedupGroup.classList.remove("hidden");
            if (this.value === "by_date") {
                dateGroup.classList.remove("hidden");
                siteHelp.textContent = SITE_HELP_NO_PAGE;
            } else if (this.value === "by_page") {
                targetSites.classList.remove("pages-hidden");
                siteHelp.textContent = SITE_HELP_BY_PAGE;
            } else if (this.value === "incremental") {
                incrementalGroup.classList.remove("hidden");
                dedupGroup.classList.add("hidden");
                siteHelp.textContent = SITE_HELP_NO_PAGE;
            }
        });
    });

    // 开始爬取
    const startBtn = document.getElementById("startBtn");
    const stopBtn = document.getElementById("stopBtn");
    var userStopped = false;
    const progressSection = document.getElementById("progressSection");
    const progressFill = document.getElementById("progressFill");
    const progressText = document.getElementById("progressText");
    const logBox = document.getElementById("logBox");
    const statusDot = document.getElementById("statusDot");
    const statusText = document.getElementById("statusText");
    const sitePanelsContainer = document.getElementById("sitePanels");
    let pollTimer = null;

    const SITE_NAMES = {
        acgyxj: "ACG游戏姬",
        acgrx: "萌幻ACG",
        acgll: "ACG图书馆",
        acgjlb: "ACG俱乐部",
        kungal: "鲲Galgame",
        "2gou": "二狗ACG"
    };
    const STATUS_LABELS = {
        waiting: "等待中",
        running: "运行中",
        completed: "完成",
        failed: "失败",
        cancelled: "已停止"
    };

    function renderSitePanels(siteStates, siteLogs) {
        if (!sitePanelsContainer || !siteStates) return;
        var keys = Object.keys(siteStates);
        if (!keys.length) return;

        keys.forEach(function(siteKey) {
            var state = siteStates[siteKey];
            var panel = sitePanelsContainer.querySelector('[data-site="' + siteKey + '"]');
            if (!panel) {
                panel = document.createElement("div");
                panel.className = "site-panel";
                panel.dataset.site = siteKey;
                panel.innerHTML =
                    '<div class="site-panel-header">' +
                    '<span class="site-panel-name">' + (SITE_NAMES[siteKey] || siteKey) + '</span>' +
                    '<span class="site-panel-status">等待中</span>' +
                    '</div>' +
                    '<div class="site-panel-stats">' +
                    '<span>进度: <strong class="sp-progress">0/0</strong></span>' +
                    '<span>✓ <strong class="sp-success">0</strong></span>' +
                    '<span>跳过 <strong class="sp-skipped">0</strong></span>' +
                    '<span>✗ <strong class="sp-error">0</strong></span>' +
                    '</div>' +
                    '<div class="site-panel-progress"><div class="site-panel-progress-fill"></div></div>' +
                    '<div class="site-panel-logs"></div>';
                sitePanelsContainer.appendChild(panel);
            }

            var statusEl = panel.querySelector(".site-panel-status");
            statusEl.textContent = STATUS_LABELS[state.status] || state.status;
            statusEl.className = "site-panel-status " + (state.status || "");

            panel.querySelector(".sp-progress").textContent = (state.current || 0) + "/" + (state.total || 0);
            panel.querySelector(".sp-success").textContent = state.success || 0;
            panel.querySelector(".sp-skipped").textContent = state.skipped || 0;
            panel.querySelector(".sp-error").textContent = state.error || 0;

            var pct = state.total > 0 ? Math.round((state.current / state.total) * 100) : 0;
            panel.querySelector(".site-panel-progress-fill").style.width = pct + "%";

            var logsEl = panel.querySelector(".site-panel-logs");
            var logs = (siteLogs && siteLogs[siteKey]) || [];
            logsEl.innerHTML = "";
            logs.slice(-15).forEach(function(log) {
                var line = document.createElement("div");
                line.className = "log-line" + (log.level === "error" ? " error" : "");
                line.textContent = log.text;
                logsEl.appendChild(line);
            });
            logsEl.scrollTop = logsEl.scrollHeight;
        });
    }

    // 读取「目标站点」区：每个勾选站点带上它自己那一行的页码范围
    function collectSitePages() {
        const sitePages = {};
        document.querySelectorAll("#targetSites .site-page-row").forEach(function(row) {
            const cb = row.querySelector('input[type="checkbox"]');
            if (!cb || !cb.checked) return;
            let start = parseInt(row.querySelector(".site-start").value, 10);
            let end = parseInt(row.querySelector(".site-end").value, 10);
            if (!(start >= 1)) start = 1;
            if (!(end >= 1)) end = 1;
            if (end < start) end = start;   // 结束页早于起始页时按起始页处理
            sitePages[cb.value] = {start: start, end: end};
        });
        return sitePages;
    }

    startBtn.addEventListener("click", function() {
        const sitePages = collectSitePages();
        const sites = Object.keys(sitePages);
        if (sites.length === 0) {
            alert("请至少选择一个站点");
            return;
        }

        const mode = document.querySelector('input[name="crawlMode"]:checked').value;
        const speed = document.querySelector('input[name="speedMode"]:checked').value || "balanced";
        const body = { mode: mode, sites: sites, site_pages: sitePages, speed: speed };
        if (mode !== "incremental") {
            body.skip_existing = document.getElementById("skipExisting").checked;
        }

        if (mode === "by_date") {
            body.start_date = document.getElementById("startDate").value;
            body.end_date = document.getElementById("endDate").value;
        }

        fetch("/api/start_crawl", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify(body)
        })
        .then(r => r.json())
        .then(data => {
            if (data.status === "ok") {
                startBtn.classList.add("hidden");
                stopBtn.classList.remove("hidden");
                progressSection.classList.remove("hidden");
                statusDot.classList.add("running");
                statusText.textContent = "爬取中...";
                logBox.innerHTML = "";
                sitePanelsContainer.innerHTML = "";
                pollProgress();
            } else {
                alert(data.message || "启动失败");
            }
        });
    });

    stopBtn.addEventListener("click", function() {
        var choice = confirm(
            "确定：保留本次已爬数据并停止爬取\n取消：继续爬取"
        );
        if (!choice) return;  // 取消 = 什么都不做，继续爬
        fetch("/api/confirm_cancel", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({discard: false})
        });
        userStopped = true;
        statusDot.classList.remove("running");
        statusText.textContent = "正在停止...";
        stopBtn.classList.add("hidden");
    });

    function pollProgress() {
        pollTimer = setInterval(function() {
            fetch("/api/progress")
                .then(r => r.json())
                .then(data => {
                    const pct = data.total > 0 ? Math.round((data.current / data.total) * 100) : 0;
                    progressFill.style.width = pct + "%";
                    progressText.textContent = data.current + " / " + data.total;
                    document.getElementById("statSuccess").textContent = data.success;
                    document.getElementById("statSkipped").textContent = data.skipped;
                    document.getElementById("statError").textContent = data.error;

                    // 四站独立窗口
                    renderSitePanels(data.site_states, data.site_logs);

                    if (data.recent_logs) {
                        // 只在用户已经在底部时才自动滚动
                        var wasAtBottom = logBox.scrollHeight - logBox.scrollTop - logBox.clientHeight < 50;
                        logBox.innerHTML = "";
                        data.recent_logs.forEach(function(log) {
                            var line = document.createElement("div");
                            line.className = "log-line" + (log.level === "error" ? " error" : "");
                            line.textContent = log.text;
                            logBox.appendChild(line);
                        });
                        if (wasAtBottom) {
                            logBox.scrollTop = logBox.scrollHeight;
                        }
                    }

                    if (!data.running) {
                        clearInterval(pollTimer);
                        startBtn.classList.remove("hidden");
                        stopBtn.classList.add("hidden");
                        statusDot.classList.remove("running");
                        statusText.textContent = userStopped ? "已停止" : "完成";
                        userStopped = false;
                        // 自动跳转到结果页
                        setTimeout(function() {
                            document.querySelectorAll(".nav-btn").forEach(function(b) { b.classList.remove("active"); });
                            document.querySelectorAll(".panel").forEach(function(p) { p.classList.remove("active"); });
                            document.querySelector('[data-panel="result"]').classList.add("active");
                            document.getElementById("panel-result").classList.add("active");
                            loadPosts();
                        }, 500);
                    }
                });
        }, 1000);
    }

    // ========== 结果面板 - 分组 + 多选 + 批量操作 ==========
    const selectedIds = new Set();
    const PAGE_SIZE = 60;
    var currentOffset = 0;
    var currentTotal = 0;
    var currentBatch = 0;  // 非0时只看该批次数据（从历史记录跳转）

    function loadPosts(resetToFirst) {
        if (resetToFirst !== false) currentOffset = 0;
        selectedIds.clear();
        updateBatchBar();
        var source = document.getElementById("filterSource").value;
        var keyword = document.getElementById("searchInput").value.trim();
        var platTab = document.querySelector(".plat-tab.active");
        var platform = platTab ? platTab.dataset.plat : "all";
        fetch("/api/posts_grouped?source=" + encodeURIComponent(source)
            + "&platform=" + platform
            + "&q=" + encodeURIComponent(keyword)
            + (currentBatch ? "&batch=" + currentBatch : "")
            + "&limit=" + PAGE_SIZE + "&offset=" + currentOffset)
            .then(function(r) { return r.json(); })
            .then(function(data) {
                currentTotal = data.total || 0;
                document.getElementById("resultCount").textContent = currentTotal;
                renderGroups(data.groups);
                renderPager();
            });
    }

    function renderPager() {
        var pager = document.getElementById("resultPager");
        if (!pager) return;
        if (currentTotal <= PAGE_SIZE) { pager.innerHTML = ""; return; }
        var page = Math.floor(currentOffset / PAGE_SIZE) + 1;
        var totalPages = Math.ceil(currentTotal / PAGE_SIZE);
        var html = "";
        if (page > 1) {
            html += '<button class="btn btn-sm" onclick="gotoPage(' + (page - 1) + ')">上一页</button> ';
        }
        var start = Math.max(1, page - 3);
        var end = Math.min(totalPages, start + 6);
        if (start > 1) html += '<button class="btn btn-sm" onclick="gotoPage(1)">1</button> ';
        if (start > 2) html += '<span class="pager-ellipsis">…</span> ';
        for (var i = start; i <= end; i++) {
            if (i === page) {
                html += '<button class="btn btn-sm btn-primary">' + i + '</button> ';
            } else {
                html += '<button class="btn btn-sm" onclick="gotoPage(' + i + ')">' + i + '</button> ';
            }
        }
        if (end < totalPages - 1) html += '<span class="pager-ellipsis">…</span> ';
        if (end < totalPages) html += '<button class="btn btn-sm" onclick="gotoPage(' + totalPages + ')">' + totalPages + '</button> ';
        if (page < totalPages) {
            html += '<button class="btn btn-sm" onclick="gotoPage(' + (page + 1) + ')">下一页</button>';
        }
        pager.innerHTML = '<span class="pager-info">第 ' + page + ' / ' + totalPages + ' 页</span> ' + html;
    }

    window.gotoPage = function(p) {
        currentOffset = (p - 1) * PAGE_SIZE;
        loadPosts(false);
        document.getElementById("panel-result").scrollIntoView({behavior: "smooth"});
    };

    // 搜索：300ms防抖
    var searchTimer = null;
    document.getElementById("searchInput").addEventListener("input", function() {
        clearTimeout(searchTimer);
        searchTimer = setTimeout(function() { loadPosts(true); }, 300);
    });

    document.getElementById("filterSource").addEventListener("change", loadPosts);

    window.switchPlatTab = function(btn) {
        document.querySelectorAll(".plat-tab").forEach(function(b) { b.classList.remove("active"); });
        btn.classList.add("active");
        loadPosts();
    };

    var currentGroups = [];

    function renderGroups(groups) {
        currentGroups = groups;
        const container = document.getElementById("groupedResults");
        container.innerHTML = "";
        const stickyBtns = document.getElementById("stickyBtns");
        stickyBtns.innerHTML = "";

        groups.forEach((group, idx) => {
            // 吸顶按钮
            const btn = document.createElement("button");
            btn.className = "sticky-date-btn";
            btn.textContent = group.label + " (" + group.total + ")";
            btn.dataset.group = idx;
            btn.addEventListener("click", function() {
                const targetGroup = document.getElementById("group-" + idx);
                const wasExpanded = targetGroup.classList.contains("expanded");
                document.querySelectorAll(".date-group").forEach(g => g.classList.remove("expanded"));
                document.querySelectorAll(".sticky-date-btn").forEach(b => b.classList.remove("active"));
                if (!wasExpanded) {
                    targetGroup.classList.add("expanded");
                    this.classList.add("active");
                    targetGroup.scrollIntoView({ behavior: "smooth", block: "start" });
                }
            });
            stickyBtns.appendChild(btn);

            // 分组容器
            const groupEl = document.createElement("div");
            groupEl.className = "date-group";
            groupEl.id = "group-" + idx;

            // 该分组涉及哪些来源站（同一平台分组可能含多站数据）
            var sourcesInGroup = [];
            var sourceSeen = {};
            group.posts.forEach(function(p) {
                if (!sourceSeen[p.source]) { sourceSeen[p.source] = true; sourcesInGroup.push(p.source); }
            });
            var sourceLabel = sourcesInGroup.join(' / ');

            const headerEl = document.createElement("div");
            headerEl.className = "date-group-header";
            headerEl.dataset.plat = group.label === "PC" ? "pc" : (group.label === "安卓" ? "android" : (group.label === "PC+安卓" ? "pc_android" : "other"));
            headerEl.innerHTML = '<div class="group-title-wrap"><span class="date-label">' + group.label + '</span><span class="group-source">' + sourceLabel + '</span></div>'
                + '<span class="date-count">' + group.total + ' 条</span>'
                + '<div class="group-actions"><button class="btn btn-sm btn-primary" onclick="downloadGroup(' + idx + ', this)" title="只导出这个分组的数据">下载本组</button>'
                + '<button class="btn btn-sm toggle-btn" onclick="toggleGroup(' + idx + ')">展开</button></div>';
            groupEl.appendChild(headerEl);
            groupEl.dataset.sources = sourcesInGroup.join(',');

            const gridEl = document.createElement("div");
            gridEl.className = "card-grid group-cards";
            group.posts.forEach(function(post) {
                gridEl.appendChild(createCard(post));
            });
            groupEl.appendChild(gridEl);

            container.appendChild(groupEl);
        });
    }

    window.toggleGroup = function(idx) {
        const group = document.getElementById("group-" + idx);
        const wasExpanded = group.classList.contains("expanded");
        document.querySelectorAll(".date-group").forEach(function(g) { g.classList.remove("expanded"); });
        document.querySelectorAll(".sticky-date-btn").forEach(function(b) { b.classList.remove("active"); });
        if (!wasExpanded) {
            group.classList.add("expanded");
            var btn = document.querySelector('.sticky-date-btn[data-group="' + idx + '"]');
            if (btn) btn.classList.add("active");
        }
    };

    // 下载本分组：按当前筛选（来源选择器不影响分组内站名，用组内实际来源）
    window.downloadGroup = function(idx, btnEl) {
        var groupEl = document.getElementById("group-" + idx);
        if (!groupEl) return;
        var group = currentGroups[idx];
        if (!group) return;
        var platTab = document.querySelector(".plat-tab.active");
        var platform = platTab ? platTab.dataset.plat : "all";
        var keyword = document.getElementById("searchInput").value.trim();
        var source = document.getElementById("filterSource").value;
        var type = group.platform === "PC" ? "pc" : (group.platform === "安卓" ? "android" : "mixed");
        if (btnEl) { btnEl.disabled = true; btnEl.textContent = "导出中..."; }
        fetch("/api/export_download?type=" + type
            + "&source=" + encodeURIComponent(source)
            + "&platform=" + encodeURIComponent(platform)
            + "&q=" + encodeURIComponent(keyword))
            .then(function(r) {
                if (!r.ok) throw new Error("导出失败");
                return r.blob();
            })
            .then(function(blob) {
                var a = document.createElement("a");
                a.href = URL.createObjectURL(blob);
                a.download = "";
                document.body.appendChild(a);
                a.click();
                a.remove();
                URL.revokeObjectURL(a.href);
            })
            .catch(function(e) { alert("导出失败: " + e.message); })
            .finally(function() {
                if (btnEl) { btnEl.disabled = false; btnEl.textContent = "下载本组"; }
            });
    };

    // 备注文本转义（发布者备注常含 < > & 等字符，不能直接塞进 HTML）
    function escapeHtml(str) {
        return String(str == null ? "" : str)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#39;");
    }

    // 备注折叠：量目标态的真实高度（不用猜的固定值），供高度动画使用
    function noteHeightWhen(body, expanded) {
        var was = body.classList.contains("expanded");
        if (was !== expanded) body.classList.toggle("expanded", expanded);
        var h = body.offsetHeight;
        if (was !== expanded) body.classList.toggle("expanded", was);
        return h;
    }

    // 展开/收起：容器高度随文字实际高度变化，箭头同步旋转，键盘可触发
    window.toggleNote = function(btn) {
        var body = document.getElementById(btn.getAttribute("aria-controls"));
        if (!body) return;
        var next = btn.getAttribute("aria-expanded") !== "true";
        var start = body.offsetHeight;
        var target = noteHeightWhen(body, next);
        var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

        body.style.transition = "none";
        body.style.maxHeight = start + "px";
        void body.offsetHeight;                 // 强制重排，让起始高度先生效
        body.style.transition = reduce ? "none" : "max-height 0.22s ease";
        body.classList.toggle("expanded", next);
        body.style.maxHeight = target + "px";

        btn.setAttribute("aria-expanded", next ? "true" : "false");
        btn.setAttribute("aria-label", next ? "收起备注" : "展开备注");
        var textEl = btn.querySelector(".note-toggle-text");
        if (textEl) textEl.textContent = next ? "收起" : "展开";

        window.setTimeout(function() {
            // 收尾后清掉内联高度，保证高度与真实文字高度一致
            body.style.maxHeight = "";
            body.style.transition = "";
        }, reduce ? 0 : 240);
    };

    // 文字没超过折叠行数时不显示按钮（避免"点了没变化"）
    // 卡片初始在折叠的分组里，量到的高度是 0，所以等它真正可见时再量
    var noteObserver = null;
    function measureNote(body) {
        var box = body.closest(".card-note");
        var btn = box && box.querySelector(".note-toggle");
        if (!btn) return;
        var full = noteHeightWhen(body, true);
        var clamped = noteHeightWhen(body, false);
        if (clamped <= 0) return;      // 不可见时不判断，保持按钮可用
        btn.hidden = (full - clamped) <= 2;
    }

    function setupNote(card) {
        var body = card.querySelector(".note-body");
        var btn = card.querySelector(".note-toggle");
        if (!body || !btn) return;
        if (!window.IntersectionObserver) return;   // 老浏览器保持按钮可用
        if (!noteObserver) {
            noteObserver = new IntersectionObserver(function(entries) {
                entries.forEach(function(en) {
                    if (!en.isIntersecting) return;
                    measureNote(en.target);
                    noteObserver.unobserve(en.target);
                });
            }, { threshold: 0.01 });
        }
        noteObserver.observe(body);
    }

    function createCard(post) {
        const card = document.createElement("div");
        card.className = "card";

        var images = [];
        try { images = JSON.parse(post.images || "[]"); } catch(e) {}

        // 构建图片网格：本地路径加/前缀，远程URL走代理
        var imgsHtml = "";
        if (images.length > 0) {
            images.forEach(function(rawImg) {
                var imgSrc = "";
                if (rawImg.indexOf("images/") === 0) {
                    imgSrc = "/" + rawImg;
                } else if (rawImg.indexOf("http") === 0) {
                    imgSrc = "/api/proxy_image?url=" + encodeURIComponent(rawImg);
                }
                if (imgSrc) {
                    imgsHtml += '<img src="' + imgSrc + '" alt="" onerror="this.style.display=\'none\'">';
                }
            });
        }

        var platformTags = {
            pc: '<span class="tag tag-pc">PC</span>',
            android: '<span class="tag tag-android">安卓</span>',
            pc_android: '<span class="tag tag-pc">PC</span><span class="tag tag-android">安卓</span>',
            unknown: '<span class="tag tag-pc">未知</span>'
        };
        var platformTag = platformTags[post.platform] || platformTags.unknown;

        var linksHtml = "";
        // 多链接渲染：优先 download_items_json（按平台分别按钮）
        var items = [];
        if (post.download_items_json) {
            try { items = JSON.parse(post.download_items_json) || []; } catch(e) { items = []; }
        }
        function labelFor(p) { return p === "pc" ? "PC" : (p === "android" ? "安卓" : (p === "pc_android" ? "PC+安卓" : "")); }
        function codeSuffix(c) { return c ? " (" + c + ")" : ""; }
        if (items && items.length) {
            // 移动云盘 2026-09-24 起下线，只渲染百度网盘
            // 同 URL 只出一个按钮（用户 2026-09-24：一条链接不该拆成 PC/安卓 两个按钮），平台取并集
            ["baidu"].forEach(function(provider) {
                var plats = items.filter(function(it){ return it.provider === provider; });
                if (!plats.length) return;
                var seenUrl = {};
                plats.forEach(function(it) {
                    var u = it.url;
                    if (seenUrl[u]) return;
                    seenUrl[u] = true;
                    var set = {};
                    plats.forEach(function(o){ if (o.url === u) set[o.platform || "unknown"] = true; });
                    var p = set.pc_android || (set.pc && set.android ? "pc_android" : (set.pc ? "pc" : (set.android ? "android" : "unknown")));
                    var suffix = labelFor(p);
                    var cls = "link-baidu";
                    var text = "百度网盘" + (suffix ? "(" + suffix + ")" : "");
                    linksHtml += '<a href="' + u + '" class="link-btn ' + cls + '" target="_blank">' + text + codeSuffix(it.code) + '</a>';
                });
            });
        } else {
            // 兼容老数据
            if (post.baidu_link) {
                linksHtml += '<a href="' + post.baidu_link + '" class="link-btn link-baidu" target="_blank">百度网盘' + (post.baidu_code ? ' ('+post.baidu_code+')' : '') + '</a>';
            }
        }
        linksHtml += '<a href="' + post.source_url + '" class="link-btn link-source" target="_blank">原帖</a>';

        var footerHtml = "";
        if (post.unzip_code || post.cheat_code) {
            footerHtml = '<div class="card-footer"><div class="footer-left">';
            if (post.unzip_code) {
                // 解压码文本由爬虫端生成完整格式（如"PC解压码:xxx"），前端不再加前缀
                footerHtml += '<button class="btn btn-sm btn-unzip" data-copy="' + escapeHtml(post.unzip_code) + '" title="' + escapeHtml(post.unzip_code) + '" onclick="copyText(this)">解压码</button>';
            }
            if (post.cheat_code) {
                footerHtml += '<button class="btn btn-sm btn-unzip" data-copy="作弊码：' + escapeHtml(post.cheat_code) + '" title="作弊码：' + escapeHtml(post.cheat_code) + '" onclick="copyText(this)">作弊码</button>';
            }
            footerHtml += '</div></div>';
        }

        // 备注（发布者说明）：折叠 3 行，超出才给展开按钮；整块可点击复制
        // 仅鲲Galgame 需要；其余四站是管理员整理站，content 为游戏简介，不算备注（2026-09-23 用户确认）
        var noteHtml = "";
        var noteText = (post.content || "").trim();
        if (noteText && post.source === "鲲Galgame") {
            // 复制时去掉开头的"网盘大小"行（用户 2026-09-24：界面保留显示，复制不含）
            var copyText2 = noteText.replace(/^网盘大小：[^\n]*\n+/, "");
            var noteShown = noteText.length > 2000 ? noteText.slice(0, 2000) + "……" : noteText;
            var noteId = "note-" + post.id;
            noteHtml = '<div class="card-note">' +
                '<div class="note-head"><span>备注</span><span class="note-copy-hint">点击复制</span></div>' +
                '<div class="note-body" id="' + noteId + '" data-copy="' + escapeHtml(copyText2) + '"' +
                ' title="点击复制备注" onclick="copyNote(this)">' + escapeHtml(noteShown) + '</div>' +
                '<button class="note-toggle" type="button" aria-expanded="false" aria-controls="' + noteId + '" aria-label="展开备注" onclick="toggleNote(this)">' +
                '<span class="note-toggle-text">展开</span>' +
                '<span class="note-arrow" aria-hidden="true">▾</span>' +
                '</button>' +
                '</div>';
        }

        var displayTitle = escapeHtml(post.title).replace(/【([^】]*)\/([^】]*)】/g, '【$1 $2】');

        var statsHtml = '<div class="card-stats"><span class="stat-item"><span class="stat-key">LIKE</span>' + (post.likes || 0) + '</span></div>';

        card.innerHTML = '<div class="card-header"><div class="card-select"><input type="checkbox" data-id="' + post.id + '" onchange="toggleSelect(this)"></div><div class="card-tags">' + platformTag + '<span class="tag tag-source">' + post.source + '</span></div><span class="tag tag-date">' + (post.post_date || '') + '</span></div><div class="card-images">' + imgsHtml + '</div><div class="card-body"><div class="card-title" onclick="copyTitle(this)" title="点击复制标题">' + displayTitle + '</div>' + statsHtml + '<div class="card-links">' + linksHtml + '</div>' + noteHtml + '</div>' + footerHtml + '<div class="card-actions"><button class="btn btn-sm" onclick="downloadPost(' + post.id + ', this)" title="只导出这一条帖子">下载</button><button class="btn btn-sm btn-danger" onclick="deletePost(' + post.id + ')">删除</button></div>';
        // 入 DOM 后再量高度，决定要不要显示展开按钮
        window.requestAnimationFrame(function() { setupNote(card); });
        return card;
    }

    function formatNumber(n) {
        if (n >= 10000) return (n / 10000).toFixed(1) + "w";
        if (n >= 1000) return (n / 1000).toFixed(1) + "k";
        return n;
    }

    // 全选/取消全选
    document.getElementById("selectAll").addEventListener("change", function() {
        var checked = this.checked;
        document.querySelectorAll(".card-select input[type='checkbox']").forEach(function(cb) {
            cb.checked = checked;
            var id = parseInt(cb.dataset.id);
            if (checked) { selectedIds.add(id); } else { selectedIds.delete(id); }
        });
        updateBatchBar();
    });

    function updateBatchBar() {
        var bar = document.getElementById("batchBar");
        var count = selectedIds.size;
        document.getElementById("selectedCount").textContent = count;
        bar.classList.toggle("active", count > 0);
    }

    // 单选切换
    window.toggleSelect = function(cb) {
        var id = parseInt(cb.dataset.id);
        if (cb.checked) { selectedIds.add(id); } else { selectedIds.delete(id); }
        updateBatchBar();
    };

    // 下载单条：只导出这一条帖子为zip
    window.downloadPost = function(id, btnEl) {
        if (btnEl) { btnEl.disabled = true; btnEl.textContent = "导出中..."; }
        fetch("/api/export_download?type=selected&ids=" + id)
            .then(function(r) {
                if (!r.ok) throw new Error("导出失败");
                return r.blob();
            })
            .then(function(blob) {
                var a = document.createElement("a");
                a.href = URL.createObjectURL(blob);
                a.download = "";
                document.body.appendChild(a);
                a.click();
                a.remove();
                URL.revokeObjectURL(a.href);
            })
            .catch(function(e) { alert("导出失败: " + e.message); })
            .finally(function() {
                if (btnEl) { btnEl.disabled = false; btnEl.textContent = "下载"; }
            });
    };

    // 删除帖子
    window.deletePost = function(id) {
        if (!confirm("确定删除这条记录？")) return;
        fetch("/api/delete_post", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({id: id})
        }).then(function() { loadPosts(); });
    };

    // 批量删除
    document.getElementById("batchDeleteBtn").addEventListener("click", function() {
        if (selectedIds.size === 0) return;
        if (!confirm("确定删除选中的 " + selectedIds.size + " 条记录？")) return;
        fetch("/api/batch_delete", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({ids: Array.from(selectedIds)})
        }).then(function() {
            selectedIds.clear();
            loadPosts();
        });
    });

    // 批量导出选中
    document.getElementById("batchExportBtn").addEventListener("click", function() {
        if (selectedIds.size === 0) return;
        var ids = Array.from(selectedIds).join(",");
        window.location.href = "/api/export_download?type=selected&ids=" + ids;
    });

    // 导出当前筛选：按结果页的来源/平台/搜索条件导出全部匹配帖子
    document.getElementById("exportFilteredBtn").addEventListener("click", function() {
        var source = document.getElementById("filterSource").value;
        var keyword = document.getElementById("searchInput").value.trim();
        var btn = this;
        btn.disabled = true;
        btn.textContent = "导出中...";
        // filtered 类型：后端一次性拉取所有匹配帖子，生成单个zip
        fetch("/api/export_download?type=filtered"
            + "&source=" + encodeURIComponent(source)
            + "&q=" + encodeURIComponent(keyword))
            .then(function(r) {
                if (!r.ok) throw new Error("导出失败");
                return r.blob();
            })
            .then(function(blob) {
                var a = document.createElement("a");
                a.href = URL.createObjectURL(blob);
                a.download = "";
                document.body.appendChild(a);
                a.click();
                a.remove();
                URL.revokeObjectURL(a.href);
            })
            .catch(function(e) { alert("导出失败: " + e.message); })
            .finally(function() {
                btn.disabled = false;
                btn.textContent = "导出当前筛选";
            });
    });

    // 加载历史
    function loadHistory() {
        fetch("/api/tasks")
            .then(function(r) { return r.json(); })
            .then(function(data) {
                var tbody = document.getElementById("historyBody");
                tbody.innerHTML = "";
                data.forEach(function(task) {
                    var tr = document.createElement("tr");
                    var statusBadge = {
                        completed: '<span class="badge badge-success">完成</span>',
                        running: '<span class="badge badge-warning">运行中</span>',
                        failed: '<span class="badge badge-error">失败</span>',
                        cancelled: '<span class="badge badge-warning">已取消</span>',
                        interrupted: '<span class="badge badge-error">已中断</span>',
                        pending: '<span class="badge">等待中</span>',
                    }[task.status] || task.status;

                    var dlBtns = '<div class="history-dl-btns">' +
                        '<a href="/api/export_batch?crawl_id=' + task.id + '&platform=pc" class="btn btn-sm btn-dl" download>本批次PC</a>' +
                        '<a href="/api/export_batch?crawl_id=' + task.id + '&platform=pc_android" class="btn btn-sm btn-dl" download>本批次PC+安卓</a>' +
                        '<a href="/api/export_batch?crawl_id=' + task.id + '&platform=android" class="btn btn-sm btn-dl" download>本批次安卓</a>' +
                        '</div>';

                    // 删除并重爬按钮：非运行中、非等待中的任务都可操作
                    var recrawlBtn = '';
                    if (task.status !== 'running' && task.status !== 'pending') {
                        recrawlBtn = '<button class="btn btn-sm" style="background:#f0ad4e;color:#fff;margin-right:4px" onclick="deleteAndRecrawl(' + task.id + ', \'' + (task.sites || '') + '\')">删除数据并重爬</button>';
                    }

                    tr.innerHTML = '<td>' + task.id + '</td><td>' + (task.task_type === 'by_page' ? '按页码' : task.task_type === 'incremental' ? '增量' : '按日期') + '</td><td>' + (task.sites || '') + '</td><td>' + statusBadge + '</td><td>' + task.success_posts + '</td><td>' + task.skipped_posts + '</td><td>' + task.error_posts + '</td><td>' + (task.created_at || '') + '</td><td><button class="btn btn-sm" onclick="viewBatchData(' + task.id + ')">查看数据</button>' + dlBtns + recrawlBtn + '<button class="btn btn-sm btn-danger" onclick="deleteTask(' + task.id + ')">删除</button></td>';
                    tbody.appendChild(tr);
                });
            });
    }

    // 查看某批次的数据：跳转结果页并只显示该批次帖子
    window.viewBatchData = function(id) {
        currentBatch = id;
        document.querySelectorAll(".nav-btn").forEach(function(b) { b.classList.remove("active"); });
        document.querySelectorAll(".panel").forEach(function(p) { p.classList.remove("active"); });
        document.querySelector('[data-panel="result"]').classList.add("active");
        document.getElementById("panel-result").classList.add("active");
        var banner = document.getElementById("batchBanner");
        var bid = document.getElementById("batchBannerId");
        if (bid) bid.textContent = id;
        if (banner) banner.classList.remove("hidden");
        loadPosts(true);
    };

    // 退出批次查看
    window.exitBatchView = function() {
        currentBatch = 0;
        var banner = document.getElementById("batchBanner");
        if (banner) banner.classList.add("hidden");
        loadPosts(true);
    };

    window.deleteTask = function(id) {
        if (!confirm('确定要删除这个任务以及该批次爬取的所有帖子数据和图片？\n\n此操作不可恢复！')) return;
        fetch("/api/delete_task", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({id: id, delete_posts: true})
        }).then(function() { loadHistory(); });
    };;

    window.deleteAndRecrawl = function(id, sites) {
        var choice = confirm(
            "即将删除该批次已爬取的帖子数据，然后重新增量爬取。\n\n" +
            "这通常用于：爬取中途暂停/取消，数据没拿到，需要重新爬取。\n\n" +
            "【确定】= 删除数据并重新爬取\n" +
            "【取消】= 什么都不做"
        );
        if (!choice) return;
        fetch("/api/delete_and_recrawl", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({id: id, sites: sites})
        }).then(function(r) { return r.json(); }).then(function(data) {
            if (data.status === "ok") {
                alert("已删除 " + data.deleted + " 条帖子，正在重新增量爬取...");
                loadHistory();
            } else {
                alert("操作失败: " + (data.message || "未知错误"));
            }
        }).catch(function(e) { alert("请求失败: " + e.message); });
    };


    // 导出页面

    function loadExportInfo() {
        fetch("/api/posts?limit=1")
            .then(function(r) { return r.json(); })
            .then(function(data) {
                document.getElementById("exportTotal").textContent = data.total;
            });
        // 获取各平台数量
        fetch("/api/export_counts")
            .then(function(r) { return r.json(); })
            .then(function(data) {
                document.getElementById("countPc").textContent = data.pc || 0;
                document.getElementById("countMixed").textContent = data.pc_android || data.mixed || 0;
                var _cA = document.getElementById("countAndroid");
                if (_cA) _cA.textContent = data.android || 0;
            });
        // 加载爬取批次
        loadCrawlBatches();
    }

    function loadCrawlBatches() {
        fetch("/api/crawl_batches")
            .then(function(r) { return r.json(); })
            .then(function(data) {
                var container = document.getElementById("batchList");
                var delContainer = document.getElementById("batchDeleteList");
                if (!data.batches || data.batches.length === 0) {
                    if (container) container.innerHTML = '<p class="empty-text">暂无爬取记录</p>';
                    if (delContainer) delContainer.innerHTML = '<p class="empty-text">暂无爬取记录</p>';
                    return;
                }
                
                var html = '';
                data.batches.forEach(function(batch) {
                    var time = batch.crawl_time ? batch.crawl_time.replace('T', ' ').substring(0, 19) : '未知';
                    html += '<div class="batch-item">';
                    html += '<div class="batch-info">';
                    html += '<span class="batch-time">📅 ' + time + '</span>';
                    html += '<span class="batch-count">共 ' + batch.post_count + ' 条</span>';
                    html += '</div>';
                    html += '<div class="batch-actions">';
                    if (batch.pc_count > 0) {
                        html += '<button class="btn btn-sm" onclick="exportBatch(' + batch.crawl_id + ', \'pc\')">PC (' + batch.pc_count + ')</button>';
                    }
                    if (batch.android_count > 0) {
                        html += '<button class="btn btn-sm" onclick="exportBatch(' + batch.crawl_id + ', \'pc_android\')">PC+安卓 (' + batch.android_count + ')</button>';
                    }
                    html += '</div>';
                    html += '</div>';
                });
                container.innerHTML = html;

                // 批次删除列表
                if (delContainer) {
                    var dhtml = '';
                    data.batches.forEach(function(batch) {
                        var time = batch.crawl_time ? batch.crawl_time.replace('T', ' ').substring(0, 19) : '未知';
                        dhtml += '<div class="batch-item">';
                        dhtml += '<div class="batch-info">';
                        dhtml += '<span class="batch-time">' + time + '</span>';
                        dhtml += '<span class="batch-count">共 ' + batch.post_count + ' 条</span>';
                        dhtml += '</div>';
                        dhtml += '<div class="batch-actions">';
                        dhtml += '<button class="btn btn-sm btn-danger" onclick="deleteBatch(' + batch.crawl_id + ', ' + batch.post_count + ')">删除该批次</button>';
                        dhtml += '</div>';
                        dhtml += '</div>';
                    });
                    delContainer.innerHTML = dhtml;
                }
            });
    }

    window.exportBatch = function(crawlId, platform) {
        window.location.href = "/api/export_batch?crawl_id=" + crawlId + "&platform=" + platform;
    };

    // 批次删除：删除该批次爬到的全部帖子+任务记录
    window.deleteBatch = function(crawlId, count) {
        if (!confirm("确定删除批次 #" + crawlId + " 的全部 " + count + " 条帖子？\n该批次任务历史也会一并删除，无法恢复。")) return;
        fetch("/api/delete_task", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({id: crawlId, delete_posts: true})
        }).then(function() {
            loadCrawlBatches();
            loadExportInfo();
        });
    };

    // 直接下载导出文件
    window.doExport = function(type) {
        window.location.href = "/api/export_download?type=" + type;
    };

    // 重新下载图片
    window.redownloadImages = function() {
        if (!confirm("将远程图片下载到本地，可能需要几分钟。继续？")) return;
        var btn = document.getElementById("redownloadBtn");
        btn.textContent = "下载中...";
        btn.disabled = true;
        fetch("/api/redownload_images", {method: "POST"})
            .then(function(r) { return r.json(); })
            .then(function(data) {
                btn.textContent = "重新下载图片";
                btn.disabled = false;
                if (data.status === "ok") {
                    alert("重新下载已启动，请等待日志完成");
                } else {
                    alert("启动失败");
                }
            });
    };

    // ========== 数据管理 ==========
    function formatSize(bytes) {
        if (bytes <= 0) return "0 B";
        var units = ["B", "KB", "MB", "GB"];
        var i = 0;
        var size = bytes;
        while (size >= 1024 && i < units.length - 1) { size /= 1024; i++; }
        return size.toFixed(i === 0 ? 0 : 1) + " " + units[i];
    }

    function loadCleanupInfo() {
        var container = document.getElementById("cleanupInfo");
        container.innerHTML = '<p class="loading-text">扫描中...</p>';
        fetch("/api/cleanup_info")
            .then(function(r) { return r.json(); })
            .then(function(data) {
                var html = '';
                var hasAny = false;

                if (data.orphan_images && data.orphan_images.count > 0) {
                    hasAny = true;
                    html += '<div class="cleanup-item">';
                    html += '<label class="checkbox-label"><input type="checkbox" class="cleanup-target" value="orphan_images">';
                    html += '<div class="cleanup-detail"><span class="cleanup-name">孤儿图片</span>';
                    html += '<span class="cleanup-desc">' + data.orphan_images.count + ' 个文件，' + formatSize(data.orphan_images.size) + '</span></div></label></div>';
                }

                if (data.export_leftovers && data.export_leftovers.count > 0) {
                    hasAny = true;
                    html += '<div class="cleanup-item">';
                    html += '<label class="checkbox-label"><input type="checkbox" class="cleanup-target" value="export_leftovers">';
                    html += '<div class="cleanup-detail"><span class="cleanup-name">旧导出文件</span>';
                    html += '<span class="cleanup-desc">' + data.export_leftovers.count + ' 个文件，' + formatSize(data.export_leftovers.size) + '</span></div></label></div>';
                }

                if (data.empty_tasks && data.empty_tasks.length > 0) {
                    hasAny = true;
                    html += '<div class="cleanup-item">';
                    html += '<label class="checkbox-label"><input type="checkbox" class="cleanup-target" value="empty_tasks">';
                    html += '<div class="cleanup-detail"><span class="cleanup-name">空任务记录</span>';
                    html += '<span class="cleanup-desc">' + data.empty_tasks.length + ' 条无数据的历史任务</span></div></label></div>';
                }

                if (!hasAny) {
                    html = '<p class="empty-text">数据库干净，无可清理项</p>';
                    document.getElementById("cleanupBtn").classList.add("hidden");
                } else {
                    document.getElementById("cleanupBtn").classList.remove("hidden");
                }

                container.innerHTML = html;
            })
            .catch(function() {
                container.innerHTML = '<p class="empty-text">加载失败</p>';
            });
    }

    window.doCleanup = function() {
        var checkboxes = document.querySelectorAll(".cleanup-target:checked");
        var targets = [];
        checkboxes.forEach(function(cb) { targets.push(cb.value); });
        if (targets.length === 0) {
            alert("请至少勾选一项");
            return;
        }
        if (!confirm("确定清理选中的 " + targets.length + " 项？操作不可恢复。")) return;
        var btn = document.getElementById("cleanupBtn");
        btn.disabled = true;
        btn.textContent = "清理中...";
        fetch("/api/cleanup", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({targets: targets})
        })
        .then(function(r) { return r.json(); })
        .then(function(data) {
            btn.disabled = false;
            btn.textContent = "执行清理";
            if (data.status === "ok") {
                var parts = [];
                var r = data.result || {};
                if (r.orphan_images_removed) parts.push("孤儿图片 " + r.orphan_images_removed + " 个");
                if (r.export_leftovers_removed) parts.push("旧导出 " + r.export_leftovers_removed + " 个");
                if (r.empty_tasks_removed) parts.push("空任务 " + r.empty_tasks_removed + " 条");
                alert("清理完成" + (parts.length ? "：" + parts.join("，") : ""));
                loadCleanupInfo();
            } else {
                alert("清理失败");
            }
        })
        .catch(function() {
            btn.disabled = false;
            btn.textContent = "执行清理";
            alert("请求失败");
        });
    };
});

// 复制文本
function copyText(el) {
    var text = el.dataset.copy || el.textContent;
    navigator.clipboard.writeText(text).then(function() {
        var orig = el.textContent;
        el.textContent = "已复制!";
        el.disabled = true;
        setTimeout(function() {
            el.textContent = orig;
            el.disabled = false;
        }, 800);
    });
}

// 复制标题
function copyTitle(el) {
    var text = el.textContent;
    navigator.clipboard.writeText(text).then(function() {
        el.classList.add("copied-title");
        var orig = el.textContent;
        el.textContent = "已复制!";
        setTimeout(function() {
            el.classList.remove("copied-title");
            el.textContent = orig;
        }, 800);
    });
}

// 备注整块点击复制（复制完整备注，不是被折叠截断的那段）
function copyNote(el) {
    // 「网盘大小」行也从 2026-09-23 起一并复制（此前是剔除的）
    var text = (el.dataset.copy || el.textContent || "")
        .replace(/\n{3,}/g, "\n\n").trim();
    navigator.clipboard.writeText(text).then(function() {
        var box = el.closest(".card-note") || el;
        box.classList.add("copied-note");
        var hint = box.querySelector(".note-copy-hint");
        var orig = hint ? hint.textContent : "";
        if (hint) hint.textContent = "已复制!";
        setTimeout(function() {
            box.classList.remove("copied-note");
            if (hint) hint.textContent = orig;
        }, 900);
    });
}

// ===== 图片灯箱 =====
var lightboxState = { images: [], index: 0, overlay: null };

function openLightbox(sources, startIndex) {
    lightboxState.images = sources || [];
    lightboxState.index = startIndex || 0;
    if (!lightboxState.images.length) return;

    var overlay = document.createElement("div");
    overlay.className = "lightbox-overlay";

    var counter = document.createElement("div");
    counter.className = "lightbox-counter";

    var img = document.createElement("img");
    img.className = "lightbox-img";
    img.alt = "";

    var closeBtn = document.createElement("button");
    closeBtn.className = "lightbox-close";
    closeBtn.textContent = "×";

    var prevBtn = document.createElement("button");
    prevBtn.className = "lightbox-nav lightbox-prev";
    prevBtn.textContent = "‹";

    var nextBtn = document.createElement("button");
    nextBtn.className = "lightbox-nav lightbox-next";
    nextBtn.textContent = "›";

    overlay.appendChild(counter);
    overlay.appendChild(img);
    overlay.appendChild(closeBtn);
    if (lightboxState.images.length > 1) {
        overlay.appendChild(prevBtn);
        overlay.appendChild(nextBtn);
    }
    document.body.appendChild(overlay);
    document.body.style.overflow = "hidden";

    lightboxState.overlay = overlay;

    function render() {
        img.src = lightboxState.images[lightboxState.index];
        counter.textContent = (lightboxState.index + 1) + " / " + lightboxState.images.length;
        var multi = lightboxState.images.length > 1;
        prevBtn.style.display = multi ? "" : "none";
        nextBtn.style.display = multi ? "" : "none";
    }

    function close() {
        if (lightboxState.overlay) {
            document.body.removeChild(lightboxState.overlay);
            document.body.style.overflow = "";
            lightboxState.overlay = null;
        }
    }

    function step(delta) {
        var n = lightboxState.images.length;
        if (!n) return;
        lightboxState.index = (lightboxState.index + delta + n) % n;
        render();
    }

    overlay.addEventListener("click", function(e) {
        if (e.target === overlay || e.target === img) close();
    });
    closeBtn.addEventListener("click", close);
    prevBtn.addEventListener("click", function(e) { e.stopPropagation(); step(-1); });
    nextBtn.addEventListener("click", function(e) { e.stopPropagation(); step(1); });

    overlay._keydown = function(e) {
        if (e.key === "Escape") close();
        else if (e.key === "ArrowLeft") step(-1);
        else if (e.key === "ArrowRight") step(1);
    };
    document.addEventListener("keydown", overlay._keydown);

    var observer = new MutationObserver(function() {
        if (!document.body.contains(overlay)) {
            document.removeEventListener("keydown", overlay._keydown);
            document.body.style.overflow = "";
            observer.disconnect();
        }
    });
    observer.observe(document.body, { childList: true });

    render();
}

// 卡片图片绑定灯箱：事件委托，处理动态渲染的卡片
document.addEventListener("click", function(e) {
    var img = e.target.closest(".card-images img");
    if (!img) return;
    var container = img.closest(".card-images");
    if (!container) return;
    var sources = [];
    container.querySelectorAll("img").forEach(function(im) {
        if (im.src) sources.push(im.src);
    });
    var idx = Array.prototype.indexOf.call(container.querySelectorAll("img"), img);
    openLightbox(sources, idx);
});
