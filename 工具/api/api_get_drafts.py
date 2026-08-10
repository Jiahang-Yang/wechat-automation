#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
api_get_drafts.py —— 用微信 API 获取草稿箱列表，并同步到本地。

用法（在 工具/ 目录下用 venv 的 python 跑）：
  ../venv/Scripts/python.exe api_get_drafts.py

说明：
  - 调 cgi-bin/draft/batchget 拉草稿箱（no_content=1，只取标题不取正文，省流量）
  - 终端打印每篇标题 + media_id + 更新时间
  - 完整结果写入 工具/草稿列表.json（本地镜像；list_drafts 内部 sync 保证每次拉取都同步）
  - 该本地文件仅供人查阅/调试，判重一律以 API 实时返回为准，不读此文件
"""
import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wechat_api import get_token, list_drafts, ts_to_str


def main():
    token = get_token()
    # sync=True：拉取的同时把结果写入 工具/草稿列表.json
    resp = list_drafts(token, sync=True)

    total = resp.get("total_count", 0)
    items = resp.get("item", [])
    print(f"草稿箱共 {total} 篇，本次返回 {len(items)} 篇：\n")
    for i, it in enumerate(items, 1):
        news = (it.get("content", {}).get("news_item") or [{}])[0]
        print(f"{i}. {news.get('title', '(无标题)')}")
        print(f"   media_id : {it.get('media_id')}")
        print(f"   更新时间 : {ts_to_str(it.get('update_time'))}")

    print("\n完整列表已写入 工具/草稿列表.json（本地镜像，每次拉取都会同步）")


if __name__ == "__main__":
    main()
