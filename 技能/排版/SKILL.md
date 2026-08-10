---
name: wechat-format
description: 将公众号文章 Markdown 转为微信排版 HTML。当用户要把 文章草稿/xxx.md 生成同名 .wechat.html（内联样式，可直接复制到微信编辑器）时使用。
---

# 排版：Markdown → 微信 HTML

## 工具
- `工具/md2wechat.py`：读 Markdown，输出内联样式排版 HTML（不依赖第三方、不卡）。

## 用法
从项目根目录运行（venv 已内嵌）：

```bash
./venv/Scripts/python.exe 工具/md2wechat.py 文章草稿/xxx.md
```

→ 生成 `文章草稿/xxx.wechat.html`。

（从 `工具/` 目录运行时：`../venv/Scripts/python.exe md2wechat.py ../文章草稿/xxx.md`）

## 注意
- 排版样式按系列视觉锚点设计（小节标题加粗深色无橙边），**勿手改 HTML**。
- Git Bash 给 Python 传路径用 `D:/...`，**不要**用 `/d/...`（会被误解成 `C:\d\...`）。
- 改稿后重跑此脚本即可刷新 HTML；同篇重跑会覆盖旧 `.wechat.html`。
- 用户侧手动路径见「用户指南.md 第三节」：进 `工具/` 跑 `../venv/Scripts/python.exe md2wechat.py ../文章草稿/xxx.md`。
