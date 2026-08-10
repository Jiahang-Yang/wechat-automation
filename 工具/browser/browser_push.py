#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
browser_push.py — Playwright 浏览器方案：获取文章列表 / 获取草稿列表 / 推送草稿。
（API 不可用时的备用方案；API 可用时优先走 api_push_draft.py）

三种主要行为（按参数自动选择）:
  - 无参数:  打开浏览器查看已群发文章列表，同步到本地 工具/文章列表.json
  - 带文章:  先在浏览器中获取草稿列表并同步本地（不调 API），再推送草稿，
             最后获取文章列表并同步本地。

原理: Playwright 驱动 Chromium（默认），复用 wechat_login.json 登录态，
      纯浏览器 DOM 操作，不依赖微信 API。
      此脚本是 API 方案的备手——API 失效时仍可推送 & 看列表。

用法:
  python browser_push.py                                → 仅获取文章列表
  python browser_push.py <文章.wechat.html> [选项]        → 推草稿 + 同步列表
  python browser_push.py <文章.wechat.html> --force      → 跳过查重
  python browser_push.py <文章.wechat.html> --headless    → 无头模式

依赖: playwright（见 tools/requirements.txt），chromium 浏览器。
"""
import sys, os, json, time, argparse, re
from datetime import datetime

# ── 路径常量 ──────────────────────────────────────────────
TOOL_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(TOOL_DIR, "wechat_login.json")
DRAFT_LIST_FILE = os.path.normpath(os.path.join(TOOL_DIR, "..", "草稿列表.json"))   # 本地草稿镜像（API 或 Playwright 写入，工具/ 根，两路径共用）
ARTICLE_LIST_FILE = os.path.normpath(os.path.join(TOOL_DIR, "..", "文章列表.json"))  # 本地文章镜像（仅 Playwright 写入，工具/ 根）
BASE_URL = "https://mp.weixin.qq.com"

# ══════════════════════════════════════════════════════════
#  第一部分：基础工具函数
# ══════════════════════════════════════════════════════════

def log(msg: str) -> None:
    # 输出给使用者（父亲）看，不带技术前缀
    print(msg, flush=True)

def ok(msg: str) -> None:
    print(f"  ✅ {msg}", flush=True)

def bad(msg: str) -> None:
    print(f"  ❌ {msg}", flush=True)

def warn(msg: str) -> None:
    print(f"  ⚠️  {msg}", flush=True)

def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def read_json(path: str):
    """读取 JSON 文件，不存在或损坏则返回 {}。"""
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        warn(f"读取 {os.path.basename(path)} 失败，将视为空文件")
        return {}

def write_json(path: str, data) -> None:
    """写入 JSON 文件。"""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def infer_title(path: str) -> str:
    """从文件路径推断文章标题：剥 .wechat.html → .html → .md。"""
    b = os.path.basename(path)
    b = re.sub(r"\.wechat\.html$", "", b, flags=re.I)
    b = re.sub(r"\.(html|md)$", "", b, flags=re.I)
    return b

def extract_titles_from_draft_json(data: dict) -> set:
    """
    从 草稿列表.json 中提取所有标题（兼容 API 格式和 Playwright 格式）。
    API 格式:   {"item":[{"content":{"news_item":[{"title":"..."}]}},...]}
    Playwright: {"drafts":[{"title":"..."},...]}
    """
    titles = set()
    items = data.get("item", []) if "item" in data else data.get("drafts", [])
    for it in items:
        if "content" in it:
            # API 格式
            news = (it.get("content", {}).get("news_item") or [{}])[0]
            t = news.get("title", "")
        else:
            # Playwright 格式
            t = it.get("title", "")
        if t:
            titles.add(t)
    return titles

# ══════════════════════════════════════════════════════════
#  第二部分：浏览器登录态管理
# ══════════════════════════════════════════════════════════

def _has_qr_frame(page) -> bool:
    """检测微信扫码登录 iframe（open.weixin.qq.com/qrconnect）是否出现。
    扫码页的顶层 URL 仍是 mp.weixin.qq.com/，单看 URL 会误判已登录，必须查子 frame。"""
    try:
        return any("qrconnect" in f.url or "open.weixin.qq.com" in f.url for f in page.frames)
    except Exception:
        return False


def ensure_login(page, headless=False) -> str:
    """
    确保已登录公众平台。
    - 复用 wechat_login.json 的登录态；无效则弹出窗口等待微信扫码（最多约 2 分钟）
    - **headless 模式下检测到扫码页立即返回空 token**（无头弹不了扫码窗，
      由调用方决定切换有头模式重跑），不傻等 2 分钟
    - **只有确认登录成功才写回 wechat_login.json**（避免未登录态覆盖好态）
    返回: 页面 URL 中提取的 token（字符串，可能为空）。
    """
    log("正在打开公众号后台…")
    page.goto(BASE_URL, wait_until="domcontentloaded")

    logged = False
    for i in range(120):  # 最多等约 2 分钟
        url = page.url
        # 已登录特征：URL 进入后台(home/frame) 且带 token，且无扫码 iframe
        if ("/cgi-bin/home" in url or "/frame" in url or "home" in url) \
                and "token=" in url and not _has_qr_frame(page):
            try:
                # URL 已带 token 且无扫码帧，文本校验只是双保险，1 秒足够
                page.wait_for_selector("text=首页", timeout=1000)
                logged = True
                break
            except Exception:
                pass
        if "login" in url or "safeguard" in url or _has_qr_frame(page):
            if i == 0:
                log("请在浏览器窗口用微信扫码登录（最多等待 2 分钟）…")
            if headless:
                warn("当前无法弹出扫码窗口（无头模式），将由程序自动切换为带窗口模式")
                return ""
            page.wait_for_timeout(5000)
            continue
        page.wait_for_timeout(2000)

    if not logged:
        # 不用 input() 等回车（非交互环境会挂起），改轮询再等 60 秒
        log("未确认登录，继续等待扫码完成（60 秒）…")
        for _ in range(20):
            page.wait_for_timeout(3000)
            url = page.url
            if ("home" in url or "frame" in url) and "token=" in url and not _has_qr_frame(page):
                try:
                    page.wait_for_selector("text=首页", timeout=2000)
                    logged = True
                    break
                except Exception:
                    continue

    if logged:
        try:
            page.context.storage_state(path=STATE_FILE)
            log("登录正常")
        except Exception as e:
            warn(f"保存登录态失败: {e}")
    else:
        warn("未能确认登录成功，本次不覆盖保存登录态（可重跑脚本）")

    # 提取 token（页面 URL 参数）
    m = re.search(r"token=(\d+)", page.url)
    return m.group(1) if m else ""

# ══════════════════════════════════════════════════════════
#  第三部分：行为一 —— 获取草稿列表（浏览器 DOM 抓取）
#           返回格式与 API 完全不同，一眼可辨。
# ══════════════════════════════════════════════════════════

def scrape_draft_list(page):
    """
    在浏览器中抓取草稿箱列表。
    流程: 直接导航到草稿箱列表页（list_card，带 token）→ 等待渲染 → 提取标题 & 时间。
    新版草稿箱是卡片布局：div.weui-desktop-publish，标题在
    a.weui-desktop-publish__cover__title > span，时间文本形如「更新于 00:16」。
    返回: [{"title": "…", "update_time": "…"}, …]
          失败返回 None（不中止主流程）。
    """
    log("─ 行为一：获取草稿列表（浏览器）──")
    try:
        # 直接导航到草稿箱列表页（新版入口 list_card；旧 list_ex 已废弃）
        tok = ""
        m = re.search(r"token=(\d+)", page.url)
        if m:
            tok = m.group(1)
        if tok:
            draft_url = (f"{BASE_URL}/cgi-bin/appmsg?begin=0&count=20&type=77"
                         f"&action=list_card&token={tok}&lang=zh_CN")
            page.goto(draft_url, wait_until="domcontentloaded")

        # 采样等待渲染（最多 5 次 × 2 秒），抓到即停
        drafts = []
        for i in range(5):
            page.wait_for_timeout(2000)
            drafts = page.evaluate("""() => {
                const items = [];
                // 方案 A（新版）：卡片布局 .weui-desktop-publish
                document.querySelectorAll('div.weui-desktop-publish').forEach(card => {
                    const titleEl = card.querySelector('a.weui-desktop-publish__cover__title span, a.weui-desktop-publish__cover__title');
                    const t = titleEl ? (titleEl.textContent || '').replace(/\\s+/g, ' ').trim() : '';
                    // 时间：形如「更新于 00:16 / 昨天 / 2026-08-01」
                    let time = '';
                    const tm = (card.textContent || '').match(/更新于\\s*([^\\s]+)/);
                    if (tm) time = tm[1];
                    if (t) items.push({title: t, update_time: time});
                });
                if (items.length) return items;
                // 方案 B（兼容旧版）：表格行 / 卡片 / appmsgid 链接
                const rows = document.querySelectorAll('tr[data-id], tr[data-appmsgid]');
                rows.forEach(row => {
                    const tds = row.querySelectorAll('td');
                    if (tds.length < 2) return;
                    const titleLink = tds[1] ? tds[1].querySelector('a') : null;
                    const title = titleLink ? (titleLink.textContent || '').trim() : '';
                    const time = tds.length >= 2 ? (tds[tds.length - 1].textContent || '').trim() : '';
                    if (title) items.push({title: title, update_time: time});
                });
                if (items.length) return items;
                document.querySelectorAll('.appmsg_item, .draft_item').forEach(card => {
                    const titleEl = card.querySelector('.appmsg_item_title, .draft_title, a');
                    const timeEl = card.querySelector('.appmsg_item_time, .draft_time');
                    if (titleEl) {
                        items.push({
                            title: (titleEl.textContent || '').trim(),
                            update_time: timeEl ? (timeEl.textContent || '').trim() : ''
                        });
                    }
                });
                return items;
            }""")
            if drafts:
                break

        if drafts:
            ok(f"获取草稿列表 → {len(drafts)} 篇")
            for d in drafts:
                print(f"    · {d['title']}  |  {d['update_time']}")
        else:
            warn("草稿列表为空（可能草稿箱无内容，或页面结构已变化）")
        return drafts

    except Exception as e:
        warn(f"获取草稿列表失败: {e}")
        return None


def sync_draft_list(scraped_drafts):
    """
    合并浏览器草稿列表到本地 草稿列表.json。
    规则:
      - 本地有但浏览器没有的 → 已从后台删除 → 从本地移除
      - 浏览器有但本地没有的 → 新增 → 补充到本地
      - 格式: Playwright 格式（{source, scraped_at, count, drafts}），
        与 API 格式（{synced_at, total_count, item}）完全不同，一眼可辨。
    """
    if scraped_drafts is None:
        return

    local = read_json(DRAFT_LIST_FILE)
    local_titles = extract_titles_from_draft_json(local)
    scraped_titles = {d["title"] for d in scraped_drafts if d.get("title")}

    added = scraped_titles - local_titles
    removed = local_titles - scraped_titles

    if added:
        ok(f"新增草稿 {len(added)} 篇: {', '.join(sorted(added))}")
    if removed:
        warn(f"移除已不存在的草稿 {len(removed)} 篇: {', '.join(sorted(removed))}")
    if not added and not removed:
        ok("草稿列表与本地一致，无需更新")

    merged = [{"title": d["title"], "update_time": d.get("update_time", "")}
              for d in scraped_drafts if d.get("title")]

    write_json(DRAFT_LIST_FILE, {
        "source": "playwright",
        "scraped_at": now_str(),
        "count": len(merged),
        "drafts": merged,
    })
    log(f"草稿列表已同步到本地 → 共 {len(merged)} 篇")


# ══════════════════════════════════════════════════════════
#  第四部分：行为二 —— 推送草稿（浏览器 DOM 操作）
#            JSAPI 灌正文 + 填标题 + 派发点击保存。
# ══════════════════════════════════════════════════════════

def push_draft(page, content: str, title: str, token: str) -> tuple:
    """
    在浏览器中新建图文消息、灌入内容并保存为草稿。
    参数:
      page    — Playwright Page 对象（已登录）
      content — HTML 正文（.wechat.html 的内容）
      title   — 文章标题
      token   — 当前页面 token
    返回: (success: bool, appmsgid: str)
    """
    log("─ 行为二：推送草稿 ──")

    # 进入图文新建页
    edit_url = (f"{BASE_URL}/cgi-bin/appmsg?t=media/appmsg_edit_v2"
                f"&action=edit&isNew=1&type=77&createType=0&token={token}")
    log("进入图文编辑页…")
    page.goto(edit_url, wait_until="domcontentloaded")
    try:
        page.wait_for_selector(".ProseMirror", timeout=20000)
        ok("编辑器就绪")
    except Exception:
        warn("编辑器可能未完全加载，继续尝试注入…")

    # ── 注入正文 ──
    # 优先 JSAPI（干净），失败则回退 DOM 直接写
    ready = False
    for _ in range(30):
        try:
            r = page.evaluate("""() => new Promise((resolve) => {
                if (!window.__MP_Editor_JSAPI__) { resolve({ok: false}); return; }
                window.__MP_Editor_JSAPI__.invoke({
                    apiName: 'mp_editor_get_isready',
                    apiParam: {},
                    sucCb: (res) => resolve({ok: true, res}),
                    errCb: (err) => resolve({ok: false, err})
                });
            })""")
            if r.get("ok"):
                ready = True
                break
        except Exception:
            pass
        page.wait_for_timeout(1500)

    injected = False
    if ready:
        r = page.evaluate("""(html) => new Promise((resolve) => {
            window.__MP_Editor_JSAPI__.invoke({
                apiName: 'mp_editor_set_content',
                apiParam: {content: html},
                sucCb: (res) => resolve({ok: true, res}),
                errCb: (err) => resolve({ok: false, err})
            });
        })""", content)
        injected = r.get("ok", False)
        log(f"JSAPI 注入: {'成功' if injected else '失败（将回退 DOM）'}")

    if not injected:
        page.evaluate("""(html) => {
            const ed = document.querySelector('.ProseMirror');
            if (ed) {
                ed.innerHTML = html;
                ed.dispatchEvent(new Event('input', {bubbles: true}));
                ed.dispatchEvent(new Event('change', {bubbles: true}));
            }
        }""", content)
        injected = True
        log("已回退 DOM 注入")

    # ── 填标题 ──
    page.evaluate(
        "(v) => {"
        " const t = document.querySelector('#title');"
        " if (t) { t.value = v; t.dispatchEvent(new Event('input', {bubbles: true}));"
        "           t.dispatchEvent(new Event('change', {bubbles: true})); }"
        "}", title)
    ok(f"标题: 《{title}》")

    # ── 验证正文长度 ──
    text_len = page.evaluate("""() => {
        const eds = document.querySelectorAll('.ProseMirror');
        return eds.length >= 2 ? eds[1].innerText.length
             : eds.length ? eds[0].innerText.length : -1;
    }""")

    # ── 保存为草稿 ──
    page.wait_for_timeout(2000)
    dispatched = False
    try:
        # 用 JS 对按钮元素直接派发 MouseEvent，绕过可能覆盖的浮层
        dispatched = page.evaluate("""() => {
            const btns = [...document.querySelectorAll('button')].filter(
                b => b.textContent.includes('保存为草稿') && b.getBoundingClientRect().width > 0
            );
            if (!btns.length) return false;
            btns[btns.length - 1].dispatchEvent(
                new MouseEvent('click', {bubbles: true, cancelable: true, view: window})
            );
            return true;
        }""")
    except Exception as e:
        log(f"保存按钮派发异常: {e}")

    # ── 轮询确认保存 ──
    # 微信保存草稿成功后，页面可能：① 停留在编辑页（URL 带 appmsgid）
    # ② 自动跳转到草稿箱列表页（URL 为 list_card，无 appmsgid）。
    # 两种情况都算保存成功；② 必须立即识别，否则会在草稿箱页面空等最长 50 秒
    #（看起来像"推完后又扫描一遍草稿箱"）。
    saved = False
    appmsgid = ""
    for _ in range(25):
        url = page.url
        if "appmsgid=" in url:
            saved = True
            mm = re.search(r"appmsgid=(\d+)", url)
            appmsgid = mm.group(1) if mm else ""
            break
        if "list_card" in url or ("appmsg" in url and "edit" not in url):
            # 已跳转草稿箱列表 = 保存成功（拿不到 appmsgid，但不影响）
            saved = True
            break
        page.wait_for_timeout(2000)

    # ── 汇总反馈 ──
    print("\n" + "─" * 48)
    ok(f"正文注入 ({text_len if text_len > 0 else len(content)} 字)")
    ok(f"标题: 《{title}》")
    if saved:
        ok("保存草稿成功")
    else:
        bad("保存失败（请手动点击「保存为草稿」）")
    print("─" * 48)

    if saved:
        log(f"下一步: 公众号后台 → 草稿箱 → 预览 → 群发")
        log(f"appmsgid = {appmsgid}")

    return saved, appmsgid


# ══════════════════════════════════════════════════════════
#  第五部分：行为三 —— 获取文章列表（已群发）+ 账本式合并同步
#           抓首页「发表记录」区域的已发布文章（近期快照）；
#           本地 文章列表.json 是「账本」，抓取是「快照」，
#           合并规则：新文章追加、老文章保留、明确「已删除」才删。
# ══════════════════════════════════════════════════════════

def scrape_article_list(page, token=""):
    """
    在浏览器中获取已群发文章列表（近期快照，按发布时间倒序）。
    流程: 回到首页（带 token）→ 抓取「发表记录」区域的已发布文章
          （a.weui-desktop-mass-appmsg__title 精确选择器，标题取 span 文本，
           徽标在 <b class="weui-desktop-key-tag"> 里不会混入）
          → 按标题聚合去重 + 识别「已删除」（仅剩 tempkey 失效链接的标题）+ 提取 send_time。
    返回: [{"title": "…", "publish_time": "…", "send_time": "…", "link": "…"}, …]
          （status 仅作内部合并信号，写盘前剥除；失败返回 None 不中止主流程）
    """
    log("── 读取已发布文章列表 ──")
    try:
        if not token:
            warn("未取得 token（登录态无效），无法获取文章列表")
            return None

        # 已在首页（带 token）则直接抓，避免重复加载整页（省 3-5 秒）；否则导航过去
        cur = page.url
        if "token=" not in cur or not ("home" in cur or "frame" in cur):
            page.goto(f"{BASE_URL}/cgi-bin/home?t=home/index&token={token}&lang=zh_CN",
                      wait_until="domcontentloaded")

        # 等待渲染：最多采样 5 次（每次 1.5 秒），抓到即停
        articles = []
        for i in range(5):
            page.wait_for_timeout(1500)
            articles = page.evaluate("""() => {
                // 按标题聚合：同一标题可能有正常链接(/s/xxx) + 失效链接(/s?tempkey 历史版本)
                const seen = {};
                const nodes = document.querySelectorAll(
                    'a.weui-desktop-mass-appmsg__title, a[href*="mp.weixin.qq.com/s/"]'
                );
                nodes.forEach(a => {
                    const href = a.href || '';
                    const isTitleClass = a.classList && a.classList.contains('weui-desktop-mass-appmsg__title');
                    // 正常文章链接：mp.weixin.qq.com/s/xxx；失效链接：mp.weixin.qq.com/s?__biz=...&tempkey=...
                    const isNormal = /mp\\.weixin\\.qq\\.com\\/s\\/[A-Za-z0-9_-]+/.test(href);
                    const isTempKey = /mp\\.weixin\\.qq\\.com\\/s\\?/.test(href) || href.includes('tempkey');
                    if (!isTitleClass && !isNormal && !isTempKey) return;
                    // 标题：优先取 a 内 span 文本（徽标在 <b class="weui-desktop-key-tag"> 里，不混入）
                    const span = a.querySelector('span');
                    let t = span
                        ? (span.textContent || '').replace(/\\s+/g, ' ').trim()
                        : (a.textContent || '').replace(/\\s+/g, ' ').trim();
                    t = t.replace(/\\s*(原创|已关闭推荐)\\s*/g, '').replace(/\\s*已修改.*$/g, '').trim();
                    if (!t) return;
                    if (!seen[t]) {
                        // 向上找文章条目容器（取 send_time 用）
                        let box = a;
                        for (let k = 0; k < 5 && box.parentElement; k++) {
                            box = box.parentElement;
                            if (String(box.className || '').includes('weui-desktop-mass-appmsg__bd')) break;
                        }
                        let send_time = '';
                        const ul = box.querySelector('a[href*="mpunderline"]');
                        const m = ul ? ul.href.match(/send_time=(\\d+)/) : null;
                        if (m) send_time = m[1];
                        seen[t] = {title: t, publish_time: '', send_time: send_time,
                                   status: '', link: isNormal ? href : '', _tempkey: isTempKey};
                    } else {
                        if (isNormal) seen[t].link = href;   // 有正常链接则采用
                        if (isTempKey) seen[t]._tempkey = true;
                    }
                });
                // 已删除判定：该标题只有失效链接（tempkey）、没有正常链接 → 已删除
                const items = [];
                for (const k in seen) {
                    const e = seen[k];
                    if (!e.link && e._tempkey) e.status = '已删除';
                    delete e._tempkey;
                    items.push(e);
                }
                return items;
            }""")
            if articles:
                break

        if articles:
            # 时间戳转可读日期（Python 端做，避免 JS 时区问题）
            for a in articles:
                if a.get("send_time"):
                    try:
                        a["publish_time"] = time.strftime(
                            "%Y-%m-%d", time.localtime(int(a["send_time"])))
                    except Exception:
                        pass
            ok(f"已读取到 {len(articles)} 篇近期文章")
        else:
            warn("暂时没读到文章（可能无已发布内容，或页面结构有变化）")
        return articles

    except Exception as e:
        warn(f"读取文章列表失败: {e}")
        return None


def sync_article_list(articles):
    """
    账本式合并更新本地 工具/文章列表.json。

    本地文件是「账本」，本次抓取是「近期快照」（首页只显示近期文章，
    老文章可能被刷出首页但并没有删除）：
      - 快照里有、账本里没有            → 追加（新文章）
      - 快照里有、账本里也有            → 以快照刷新（补 send_time / 更新链接）
      - 账本里有、快照里没有            → 保留（老文章，不删除）
      - 快照里明确标「已删除」的标题    → 从账本删除
    排序：有 send_time 的按发布时间**倒序**（最新在前）；老文章（无时间戳）
    排最后并保持账本原有相对顺序。
    """
    if articles is None:
        warn("文章列表获取失败，未写入本地文件")
        return

    local = read_json(ARTICLE_LIST_FILE)
    old = local.get("articles", []) if isinstance(local, dict) else []
    by_title = {a.get("title"): a for a in old if a.get("title")}

    added, updated, removed = [], [], []
    for a in articles:
        t = a.get("title", "")
        if not t:
            continue
        if a.get("status") == "已删除":
            if t in by_title:
                del by_title[t]
                removed.append(t)
            continue
        if t in by_title:
            # 修正式更新：补 send_time/publish_time（首次抓取的老条目没有），链接以快照为准
            old_a = by_title[t]
            if a.get("send_time") and not old_a.get("send_time"):
                old_a["send_time"] = a["send_time"]
                old_a["publish_time"] = a.get("publish_time", "")
                updated.append(t)
            new_link = a.get("link") or old_a.get("link")
            if old_a.get("link") != new_link:
                old_a["link"] = new_link
                updated.append(t)
        else:
            by_title[t] = a
            added.append(t)

    # 有时间戳的按发布时间倒序（最新在前）；无时间戳的老文章排最后（保持账本顺序）
    with_t = [a for a in by_title.values() if a.get("send_time")]
    without_t = [a for a in by_title.values() if not a.get("send_time")]
    with_t.sort(key=lambda a: int(a["send_time"] or 0), reverse=True)
    merged = with_t + without_t

    # status 只是合并过程中的内部信号（标记「已删除」以便剔除），
    # 删除的文章不进账本、保留的文章永远没有该状态 → 写盘前剥掉，账本保持干净
    for a in merged:
        a.pop("status", None)

    write_json(ARTICLE_LIST_FILE, {
        "source": "playwright",
        "scraped_at": now_str(),
        "count": len(merged),
        "articles": merged,
    })
    log(f"已更新本地记录：共 {len(merged)} 篇文章"
        f"（本次新增 {len(added)}，删除 {len(removed)}）")
    for a in merged:
        print(f"    · {a['title']}  |  {a['publish_time']}")


# ══════════════════════════════════════════════════════════
#  第六部分：主入口 —— 按参数分发三种行为
# ══════════════════════════════════════════════════════════

def main():
    ap = argparse.ArgumentParser(
        description=(
            "Playwright 浏览器方案（不依赖微信 API）\n"
            "  无参数         → 仅获取已群发文章列表\n"
            "  带文章.wechat.html → 查草稿列表 → 推送 → 获取文章列表"
        )
    )
    ap.add_argument(
        "html", nargs="?",
        help="要推送的 .wechat.html 文件路径（不提供则仅获取文章列表）"
    )
    ap.add_argument("--force", action="store_true",
                    help="忽略草稿查重，强制新建一篇")
    ap.add_argument("--headless", action="store_true",
                    help="无头模式（不弹窗口）")
    ap.add_argument("--show", action="store_true",
                    help="强制显示浏览器窗口（默认无参模式自动无头，仅调试用）")
    ap.add_argument("--browser", choices=["chromium", "firefox"],
                    default="chromium",
                    help="浏览器内核（默认 chromium）")
    args = ap.parse_args()

    mode_push = args.html is not None

    # 无参模式（仅查看文章列表）自动使用无头浏览器：不弹窗、更快，
    # 也避免运行环境对浏览器命令"先预跑一次再正式跑"导致的双窗口现象。
    # 推送模式保持有头（可能要扫码、要让使用者看到操作过程）。
    if not mode_push and not args.headless and not args.show:
        args.headless = True
        log("即将自动获取已发布文章列表（约 6~10 秒）…")

    # ── 推送模式：预读文件 ──
    if mode_push:
        src = os.path.abspath(args.html)
        if not os.path.exists(src):
            log(f"文件不存在: {src}")
            sys.exit(1)
        with open(src, "r", encoding="utf-8") as f:
            html_content = f.read()
        title = infer_title(src)
        log(f"目标文章: 《{title}》")
    else:
        log("本次仅读取已发布文章列表。")

    # ── 启动浏览器 ──
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        _t0 = time.time()
        engine = p.chromium if args.browser == "chromium" else p.firefox

        def _launch():
            """启动浏览器 + 建上下文 + 新页面。返回 (browser, ctx, page)。"""
            # --disable-gpu：减少 GPU 子进程，显著加快 browser.close() 的进程回收
            la = {"headless": args.headless}
            if args.browser == "chromium":
                la["args"] = ["--disable-gpu", "--disable-software-rasterizer"]
            b = engine.launch(**la)
            c = b.new_context(
                viewport={"width": 1440, "height": 900},
                locale="zh-CN",
                storage_state=STATE_FILE if os.path.exists(STATE_FILE) else None,
            )
            pg = c.new_page()
            return b, c, pg

        log("第 1 步 / 共 3 步：正在启动…")
        browser, ctx, page = _launch()
        if os.path.exists(STATE_FILE):
            log("    已找到登录信息")
        log(f"    （启动完成，用时 {time.time() - _t0:.1f} 秒）")

        # ── 登录 ──
        log("第 2 步 / 共 3 步：正在登录公众号后台…")
        token = ensure_login(page, headless=args.headless)

        # ⚠️ 无头模式下登录态失效（token 为空）：弹不了扫码窗，
        #    自动切换为有头模式重启，等待用户扫码后继续
        if not token and args.headless:
            warn("登录状态已过期，且当前无法弹出扫码窗口 → 正在切换为带窗口模式…")
            try:
                browser.close()
            except Exception:
                pass
            args.headless = False
            log("第 2 步：已切换带窗口模式，请在弹出的浏览器窗口中用微信扫码…")
            browser, ctx, page = _launch()
            token = ensure_login(page, headless=False)
        log(f"    （登录完成，用时 {time.time() - _t0:.1f} 秒）")

        # ══════════════════════════════════════════════════
        #  行为一：获取草稿列表（仅推送模式）
        #  纯浏览器 DOM 抓取，不调 API。
        #  失败不中止：退而取本地 草稿列表.json 做查重。
        # ══════════════════════════════════════════════════
        if mode_push:
            scraped_drafts = scrape_draft_list(page)

            if scraped_drafts is not None:
                # ── 同步本地 ──
                sync_draft_list(scraped_drafts)

                # ── 浏览器查重 ──
                scraped_titles = {d["title"] for d in scraped_drafts if d.get("title")}
                if title in scraped_titles:
                    if not args.force:
                        warn(f"草稿箱已存在同名《{title}》，已中止（加 --force 可强制推送）。")
                        browser.close()
                        sys.exit(0)
                    else:
                        warn(f"草稿箱已有同名《{title}》，但 --force 已指定，仍新建一篇。")
                else:
                    ok("浏览器草稿查重通过（未命中同名），继续推送。")
            else:
                # 浏览器获取失败 → 退而查本地 草稿列表.json
                warn("浏览器获取草稿列表失败，退而使用本地 草稿列表.json 查重。")
                local = read_json(DRAFT_LIST_FILE)
                local_titles = extract_titles_from_draft_json(local)
                if title in local_titles:
                    if not args.force:
                        warn(f"本地草稿列表已存在同名《{title}》，已中止（加 --force 可强制推送）。")
                        browser.close()
                        sys.exit(0)
                    else:
                        warn(f"本地草稿列表已有同名《{title}》，但 --force 已指定，仍新建一篇。")
                else:
                    ok("本地草稿列表查重通过，继续推送。")

        # ══════════════════════════════════════════════════
        #  行为二：推送草稿（仅推送模式）
        # ══════════════════════════════════════════════════
        if mode_push:
            saved, _appmsgid = push_draft(page, html_content, title, token)
            # 推送成功后重新扫描一遍草稿箱，把新推的草稿同步进本地镜像
            # （推前的镜像不含新草稿，必须再扫一次才能保持一致）
            if saved:
                log("推送成功，重新扫描草稿箱并同步本地…")
                fresh = scrape_draft_list(page)
                if fresh is not None:
                    sync_draft_list(fresh)

        # ══════════════════════════════════════════════════
        #  行为三：获取已群发文章列表（所有模式都执行）
        #  从首页底部「已群发」→「查看全部」进入。
        # ══════════════════════════════════════════════════
        print()
        log("第 3 步 / 共 3 步：正在读取已发布文章…")
        articles = scrape_article_list(page, token)
        sync_article_list(articles)
        log(f"    （读取完成，用时 {time.time() - _t0:.1f} 秒）")

        if not args.headless:
            log("窗口即将自动关闭…")
            page.wait_for_timeout(1000)
        _t_close = time.time()
        try:
            ctx.close()          # 先关页面上下文，释放页面/网络子进程
        except Exception:
            pass
        browser.close()
        log(f"本次已完成，总用时约 {time.time() - _t0:.1f} 秒")


if __name__ == "__main__":
    main()
