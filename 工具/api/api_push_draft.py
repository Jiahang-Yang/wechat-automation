#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
api_push_draft.py —— 用微信 API 把一篇文章推送到草稿箱。

用法（在 工具/ 目录下用 venv 的 python 跑）：
  ../venv/Scripts/python.exe api_push_draft.py <文章.wechat.html> [选项]

选项：
  --cover <图片路径>   封面图（本地文件，会先上传成永久素材拿 media_id）
  --thumb <media_id>   直接传已上传的封面 media_id（跳过上传）
  --title <标题>       覆盖标题（默认取文件名）
  --author <作者>
  --digest <摘要>      摘要（不填自动抓正文前段）
  --md                 源文件是 .md，先调用 md2wechat.py 生成 .wechat.html
  --force              即使标题已存在于草稿箱也继续推送

说明：
  - content 字段直接塞入 .wechat.html 的正文 HTML（内联样式，微信可识别）
  - draft/add 必须有 thumb_media_id（封面），纯文字文章也需一张封面图
  - 推之前会先拉草稿箱按标题查重，命中且未加 --force 则中止
"""
import os
import sys
import re
import json
import argparse
import subprocess

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wechat_api import (
    get_token, http_json, API, BASE,
    upload_permanent_image, find_cover_in_assets, draft_title_exists,
)

# 封面 media_id 本地缓存：同一张封面图只上传一次，之后复用 media_id，
# 避免每次推送都往素材库重复上传（素材库会堆满重复封面）
COVER_CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "封面缓存.json")


def load_cover_cache():
    if os.path.exists(COVER_CACHE):
        try:
            with open(COVER_CACHE, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_cover_cache(cache):
    with open(COVER_CACHE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def build_content_from_html(html):
    """取正文体：优先 <body> 内部，否则整文件（我们的 .wechat.html 已是纯片段）。"""
    m = re.search(r"<body[^>]*>(.*)</body>", html, re.S | re.I)
    return m.group(1).strip() if m else html.strip()


def extract_title(html, fallback):
    m = re.search(r"<title>(.*?)</title>", html, re.S | re.I)
    return m.group(1).strip() if m else fallback


def auto_digest(content, n=80):
    text = re.sub(r"<[^>]+>", "", content)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:n]


def draft_exists(token, title):
    """拉草稿箱（实时 API），按标题判重。返回 (存在?, media_id)。
    直接复用 wechat_api.draft_title_exists；sync=True 顺便同步本地 草稿列表.json。"""
    return draft_title_exists(token, title, sync=True)


def main():
    parser = argparse.ArgumentParser(description="推送文章到草稿箱")
    parser.add_argument("article", help="文章 .wechat.html（或 .md，配合 --md）")
    parser.add_argument("--cover", help="封面图本地路径（上传成永久素材）")
    parser.add_argument("--thumb", help="已上传的封面 media_id（跳过上传）")
    parser.add_argument("--title", help="覆盖标题")
    parser.add_argument("--author", default="")
    parser.add_argument("--digest", default="")
    parser.add_argument("--md", action="store_true", help="源文件是 .md")
    parser.add_argument("--force", action="store_true", help="标题已存在也强制推送")
    args = parser.parse_args()

    # 1) 拿到正文 HTML
    path = os.path.abspath(args.article)
    if not os.path.exists(path):
        print(f"❌ 文件不存在：{path}")
        sys.exit(1)
    if args.md or path.endswith(".md"):
        md2wechat = os.path.normpath(os.path.join(BASE, "..", "md2wechat.py"))
        subprocess.run([sys.executable, md2wechat, path], check=True)
        path = os.path.splitext(path)[0] + ".wechat.html"
    with open(path, encoding="utf-8") as f:
        html = f.read()
    content = build_content_from_html(html)

    # 2) 标题
    basename = os.path.basename(path)
    fallback = re.sub(r"\.wechat\.html$", "", basename, flags=re.I)
    fallback = re.sub(r"\.(html|md)$", "", fallback, flags=re.I)
    title = args.title or extract_title(html, fallback)

    # 3) 摘要
    digest = args.digest or auto_digest(content)

    token = get_token()

    # 4) 查重（除非 force）
    if not args.force:
        exists, mid = draft_exists(token, title)
        if exists:
            print(f"⚠️ 草稿箱已存在同名《{title}》（media_id={mid}），已中止以免重复。")
            print("   如需强制重推，加 --force。")
            sys.exit(0)

    # 5) 封面 media_id（优先复用：--thumb > 本地缓存 > 上传并写缓存）
    thumb_media_id = args.thumb
    if not thumb_media_id:
        cover = args.cover or find_cover_in_assets()
        if not cover or not os.path.exists(cover):
            print("❌ 缺少封面：draft/add 必须有 thumb_media_id。")
            print("   请用 --cover <图片路径> 指定封面，或 --thumb <media_id> 传已上传的。")
            sys.exit(1)
        cache = load_cover_cache()
        key = os.path.abspath(cover)
        thumb_media_id = cache.get(key)
        if thumb_media_id:
            print(f"↻ 复用已上传封面（素材库 media_id 缓存）")
        else:
            print(f"↑ 上传封面：{cover}")
            thumb_media_id = upload_permanent_image(token, cover)
            cache[key] = thumb_media_id
            save_cover_cache(cache)

    # 6) 推送
    resp = http_json(
        "POST",
        f"{API}/draft/add",
        body={
            "articles": [
                {
                    "title": title,
                    "author": args.author,
                    "digest": digest,
                    "content": content,
                    "thumb_media_id": thumb_media_id,
                    "need_open_comment": 0,
                    "only_fans_can_comment": 0,
                }
            ]
        },
        params={"access_token": token},
    )
    if "media_id" not in resp:
        print("❌ 推送失败：", json.dumps(resp, ensure_ascii=False, indent=2))
        sys.exit(1)

    print(f"✅ 推送成功！《{title}》")
    print(f"   media_id = {resp['media_id']}")
    print("   下一步：去公众号后台草稿箱预览 → 群发。")


if __name__ == "__main__":
    main()
