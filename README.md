# 公众号工作流（本地优先 · 可移植）

> 本文件给 **智能体 / 接手开发者** 看。给使用者（父亲）的通俗手册见同目录 `用户指南.md`。

## 一、项目愿景

只解决一件事：**把写公众号文章，从「打开网页 → 复制 → 粘贴 → 排版 → 点来点去」变成「写 Markdown → 一条命令 → 进草稿箱」**。

两个号：
- **飞行笔记的一隅**（用户本人）：变形金刚同人 / 亚文化整活，娱乐号。
- **运海老杨**（父亲 杨运海）：财税健康 / 个人财税 / 转型思考，认真号，关联书系《财税创造价值》。

核心结论：**个人订阅号没有群发 API**（但草稿箱 / 发布接口个人号已开放，可经官方 API 推草稿、读草稿箱）。自动化的天花板是「人工群发」——写好、排好版、推进草稿箱；**最后群发必须由人在后台点**。本项目把前 90% 自动化，并做成「整个文件夹搬走就能用」。

## 二、能 / 不能

**能**
- Markdown 一键转公众号排版 HTML（本地、无第三方、不卡）
- 排版 HTML 一键推进**草稿箱**（等效秀米「同步草稿箱」，但本地、无第三方）
- 防重复（推送前先调微信 API 拉【当前】草稿箱按标题判重，同篇重跑自动中止；每次拉列表同时同步写 `工具/草稿列表.json` 本地镜像）
- 整个文件夹复制即走（venv 内嵌 + `工具/setup.sh` 可重建）

**不能**
- 不能自动群发（个人号无群发 API；但草稿箱 / 发布接口个人号已开放，可经官方 API 推草稿、读草稿箱）
- 不替你点「群发」——公开发布仍需人在后台点（微信规则）

## 三、目录结构（整理后）

```
公众号工作流/
├── README.md            # 本文件（智能体向技术说明）
├── 用户指南.md           # 给使用者（父亲）的通俗操作手册
├── .gitignore
├── 文章草稿/            # 源稿 .md + 生成 .wechat.html（父亲主要工作区；gitignore，不入库）
├── 素材/               # 配图（父亲放图；gitignore，不入库）
├── 技能/               # 可移植技能源（写作/封面/排版/发布/白名单 各含 SKILL.md + install_skills.sh）
├── 工具/
│   ├── api/                  # 【API 路径】官方接口脚本 + 凭证（自洽闭环）
│   │   ├── wechat_api.py        # 共享模块：token / 封面上传 / draft 调用
│   │   ├── api_get_drafts.py    # 【API】获取草稿箱列表（官方接口，纯 requests）
│   │   ├── api_push_draft.py    # 【API】推送文章到草稿箱（官方接口，纯 requests）
│   │   ├── .env                 # API 凭证（gitignore，勿提交）
│   │   ├── .env.example         # 凭证模板（复制为 .env 填 APPID/APPSECRET）
│   │   └── get_public_ip.py     # 获取当前公网 IP（40164 白名单配置用，供「白名单」技能调用）
│   ├── browser/              # 【浏览器备用路径】API 不可用时兜底（自洽闭环）
│   │   ├── browser_push.py      # HTML → 推草稿箱（Playwright 浏览器模拟）
│   │   ├── publish.sh           # browser_push.py 一键包装（调 venv python）
│   │   └── wechat_login.json    # 登录态缓存（gitignore，机器相关）
│   ├── md2wechat.py          # Markdown → 公众号排版 HTML（独立，无同目录依赖）
│   ├── setup.sh              # 新机器重建 venv + 依赖 + Chromium
│   ├── requirements.txt      # 依赖锁：playwright==1.62.0、requests>=2.31.0
│   ├── 草稿列表.json          # 草稿箱列表本地镜像（API/浏览器共用，gitignore，仅供查阅）
│   └── 文章列表.json          # 已发布文章账本（Playwright 同步，gitignore，仅供查阅）
├── venv/               # 本机 Python 环境（gitignore，setup.sh 可重建）
```

> **设计原则**：根目录只放「父亲能看懂的」（`文章草稿/`、`素材/`）、「最基本说明」（`README.md` 给智能体、`用户指南.md` 给使用者）与「技能规则」（`技能/`，给智能体自动加载）；一切脚本 / 登录态 / 依赖等"工具调用"相关都收在 `工具/`（并按 api / browser 两组分目录）。

## 四、发文路径（API 优先，浏览器模拟作备用）

### 路径 A：官方 API（推荐，免浏览器 / 免扫码）
走微信官方接口（`cgi-bin/draft/*`），只要 `工具/api/.env` 里有 APPID/APPSECRET（IP 白名单留空即可任意 IP 调用）。不依赖 Playwright / Chromium / 扫码登录。

> 若报 **`40164 invalid ip`**（当前 IP 不在白名单）：按「白名单」技能处理——`get_public_ip.py` 查当前 IP → 给用户开发者平台链接（自动带 AppID）添加白名单（约 1 分钟生效）；修复前走浏览器备用路径，不阻塞本次推送。

```bash
# 0. 复制模板并填凭证（一次性）
cp 工具/api/.env.example 工具/api/.env
#   编辑 .env 填入 APPID / APPSECRET（公众平台 → 设置与开发 → 基本配置）

# 1. 取排版 HTML（若还没生成）
./venv/Scripts/python.exe 工具/md2wechat.py 文章草稿/xxx.md

# 2. 用 API 同步草稿箱列表（验证 token + 接口，并写 工具/草稿列表.json）
../venv/Scripts/python.exe 工具/api/api_get_drafts.py

# 3. 用 API 推送草稿（需一张封面图；推前会再按标题查重）
../venv/Scripts/python.exe 工具/api/api_push_draft.py 文章草稿/xxx.wechat.html --cover 素材/封面.png
#   可选：--thumb <media_id> 复用已上传封面 / --title 覆盖标题 / --force 强制重推

# 4. （不加参数）用浏览器脚本刷新已群发文章列表（API 无文章列表接口，此项走浏览器）
#    （无参模式自动无头：不弹窗、约 6 秒完成）
../venv/Scripts/python.exe 工具/browser/browser_push.py
```
- 依赖：`requests`（已在 venv 安装，`工具/requirements.txt` 含 `requests>=2.31.0`；新机器跑 `工具/setup.sh` 会自动装）。
- 推送前按标题查重走官方 `draft/batchget`，命中且未加 `--force` 自动中止；不再需要本地清单兜底。
- 封面：`draft/add` 强制要 `thumb_media_id`，脚本用 `material/add_material` 上传 `--cover` 图拿永久 media_id。
- 第 4 步可选：只有想刷新「已群发文章列表」时才跑（文章列表只能经浏览器抓取，API 拿不到）。**账本式合并**：本地 `文章列表.json` 是账本、抓取是近期快照——新文章追加到末尾、老文章保留（首页只显示近期，被刷下去 ≠ 删除）、快照里明确标「已删除」的才从账本删。

### 路径 B：浏览器备用（API 不可用时）
当 `.env` 缺失 / AppSecret 错误 / IP 白名单拦截 / 网络异常导致 API 走不通时，用 Playwright 浏览器模拟兜底。它**不加参数只看列表、加文章参数则「查草稿 → 推送 → 看文章列表」一气呵成**。

```bash
# 仅刷新已群发文章列表（不加参数）
./工具/browser/publish.sh        # 等价 browser_push.py 无参数
# 带文章：查草稿列表 → 推送 → 刷新文章列表
./工具/browser/publish.sh xxx
#   或：./工具/browser/publish.sh xxx --force      跳过查重强制新建
#   或：./工具/browser/publish.sh xxx --headless   无头（仅测试）
```
- `publish.sh` 即 `browser_push.py` 的一键包装（直接用 venv 的 python，无需 source activate）。
- 首次运行弹窗微信扫码，登录态缓存在 `工具/browser/wechat_login.json`；草稿查重走浏览器 DOM（抓取失败不退而读本地 `草稿列表.json`），推送走 JSAPI 灌正文后「保存为草稿」。

### 路径 C：纯手动（零环境依赖）
写稿 → `工具/md2wechat.py` 生成 HTML → 浏览器打开全选复制 → 微信 PC 版内嵌浏览器粘贴 → 群发。
（Edge 开后台编辑/粘贴会卡死，根因是 **Dark Reader** 扩展；微信 PC 版无扩展、稳定。）

## 五、环境与可移植性

- **本机即用**：`venv/` 已内嵌。API 可用时直接 `../venv/Scripts/python.exe 工具/api/api_push_draft.py 文章.wechat.html --cover 素材/封面.png`；浏览器备用路径用 `./工具/browser/publish.sh xxx`（首次弹窗扫码）。
- **搬到其他机器**：
  1. 复制「公众号工作流」文件夹，**排除 `venv/`**（venv 不跨机器：`pyvenv.cfg` 写死了创建机的 Python 路径，拷过去无效且 setup.sh 会因"venv 已存在"跳过重建）；
  2. 新机器先装 **Python 3.11+** 并加入 PATH（命令行 `python --version` 能出结果）；
  3. 在新机器 `bash 工具/setup.sh`（建 venv + 装 playwright + 下 Chromium）；无 Git Bash 时等价手动命令：
     `python -m venv venv` → `venv\Scripts\pip install -r 工具\requirements.txt` → `venv\Scripts\python -m playwright install chromium`
  4. 首次 `./工具/browser/publish.sh xxx` 弹窗微信扫码，之后登录态缓存在 `工具/browser/wechat_login.json`，cookie 过期前免扫。
- **版本控制**：`.gitignore` 排除 `venv/`、`工具/api/.env`、`工具/api/access_token_cache.json`、`工具/browser/wechat_login.json`、`工具/草稿列表.json`、`__pycache__`；`git clone` 后跑 `工具/setup.sh` 复原。
- ⚠️ **Python 路径坑（重要）**：Git Bash 给 Python 传路径必须用盘符写法（如 `D:/...`），**不能**用 `/d/...`（会被误解成 `C:\d\...`）。

## 六、已知坑

| 现象 | 根因 | 处理 |
|------|------|------|
| Edge 编辑/粘贴卡死 | Dark Reader 扩展与编辑器 DOM 修复死循环 | 在 mp.weixin.qq.com 页面禁用 Dark Reader，或改用微信 PC 版 |
| 保存「假成功」不进草稿箱 | JS `.click()` 不触发 Vue 事件 | browser_push.py（浏览器备用路径）已改用对按钮派发 MouseEvent，稳定 |
| 保存点击超时 | 编辑器浮层盖住按钮中心，坐标点击被拦 | 同上，JS 派发绕过浮层 |
| 跑几次堆出多个草稿 | 每次新建草稿 | 推送前先查当前草稿箱按标题判重：API 路径走 `draft/batchget`，浏览器路径走后台 DOM（抓取失败退查本地 `草稿列表.json`）；命中同名自动中止（`--force` 可强制重推） |
| 误以为文章发了/没发 | 个人号无群发 API，仍需人工群发 | 草稿箱可经官方 API 读取，发否以用户后台确认为准 |
| 换浏览器内核要重登 | 微信把 UA 绑进登录态 cookie，跨内核 UA 不一致被踢 | 单内核沿用即可；要双内核免登需按 `--browser` 分两个登录态文件 |

## 七、平台限制

- 个人订阅号无群发 API，无法全自动发文。
- 订阅号每天群发 1 次，0 点刷新；支持最长 2 天内定时群发。
- 2018 后注册无留言功能，读者靠私信/朋友圈互动。
- 微信对自动化登录有风控，cookie 可能隔几天过期需重扫；个人号别高频使用。

## 八、内容定位

- **运海老杨**：财税健康 / 个人财税 / 从业者视角。风格基线（父亲口吻）：平实有阅历、金句收尾；与书系《财税创造价值》强关联。合规：定位「梳理 / 分享 / 教育」，避免承诺具体避税结果或收益。
- **飞行笔记的一隅**：变形金刚同人 / 亚文化整活，第一人称毒舌幽默（惊天雷·书记员视角），小节标题加粗深色无橙边。

## 九、技能（可移植 + 自动加载）

工作流技能已**按步骤拆分**在 `技能/` 下，每个子目录是一个独立技能，含一个 `SKILL.md`（标准文件名单数，智能体才能自动发现）：

```
技能/
├── 写作/SKILL.md   # 写公众号文章草稿（含变形金刚同人系列笔调与衔接铁律）
├── 封面/SKILL.md   # 生成公众号封面（ImageGen，头条 2.35:1 / 小图 1:1）
├── 排版/SKILL.md   # Markdown → 微信排版 HTML（md2wechat.py）
├── 发布/SKILL.md   # 推草稿箱（API 优先 / 浏览器备用）
└── 白名单/SKILL.md # 40164 IP 白名单处理（查 IP + 开发者平台链接）
```
同目录还带一个 `install_skills.sh`（一键装到用户级技能目录）。

**为什么放根目录 `技能/` 而不是收进 `工具/`**：技能定义的是「怎么写、怎么排、怎么发」的**规则**（内容资产，跨项目可复用）；`工具/` 里是**怎么执行**的脚本（工具调用）。两者性质不同，分开放更清晰——根目录 = 父亲看得懂的内容 + 说明 + 技能规则；`工具/` = 纯技术执行。

**移植到其他电脑时，让技能生效的方式**：
1. 复制整个「公众号工作流」文件夹到新机器；
2. 让智能体把 `技能/` 下的每个子目录，复制到它的**技能目录**：
   - 用户级（本机所有项目可用）：`~/.workbuddy/skills/`
   - 项目级（仅当前工作区）：`<工作区>/.workbuddy/skills/`
3. 也可直接跑 `bash 技能/install_skills.sh`（默认装到用户级 `~/.workbuddy/skills/`）。
4. 装完后，**智能体会按每个 `SKILL.md` 的 `description` 自动判断相关性并加载**——相关任务不用你提醒，它会自己调用对应技能。这与 WorkBuddy 自身机制一致：工作区/用户级技能目录里的技能会被自动发现、按相关度自动使用，无需在界面里手动「加号」选择。

> 根目录不再有 `SKILL.md`；旧版已归档到 `_archive/SKILL_旧版.md`。
