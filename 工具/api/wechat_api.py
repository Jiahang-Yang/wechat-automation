#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
wechat_api.py —— 微信公众平台 API 共享模块。

仅依赖 requests（已在 venv 安装）。提供：
  - load_config()        读取 工具/api/.env（APPID / APPSECRET）
  - get_token()          access_token 获取 + 本地缓存（过期前 5 分钟刷新）
  - http_json()          JSON 接口调用封装（GET/POST）
  - upload_permanent_image()  上传永久图片素材，返回 media_id（封面用）
  - find_cover_in_assets()    在 素材/ 找默认封面图
  - ts_to_str()          Unix 时间戳 → 可读字符串
"""
import os
import json
import time
import requests

BASE = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(BASE, ".env")
TOKEN_CACHE = os.path.join(BASE, "access_token_cache.json")
ASSETS_DIR = os.path.normpath(os.path.join(BASE, "..", "..", "素材"))
DRAFT_LIST_FILE = os.path.normpath(os.path.join(BASE, "..", "草稿列表.json"))
API = "https://api.weixin.qq.com/cgi-bin"

EXT_CT = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".bmp": "image/bmp",
    ".webp": "image/webp",
}


def load_config():
    cfg = {}
    if os.path.exists(ENV_PATH):
        with open(ENV_PATH, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                cfg[k.strip()] = v.strip().strip('"').strip("'")
    return cfg


def get_token(force=False):
    cfg = load_config()
    appid = cfg.get("APPID")
    secret = cfg.get("APPSECRET")
    if not appid or not secret:
        raise RuntimeError("缺少 APPID / APPSECRET。请在 工具/api/.env 填写（参考 .env.example）。")

    if not force and os.path.exists(TOKEN_CACHE):
        try:
            with open(TOKEN_CACHE, encoding="utf-8") as f:
                data = json.load(f)
            if time.time() < data.get("expire_at", 0) - 300:
                return data["access_token"]
        except Exception:
            pass

    r = requests.get(
        f"{API}/token",
        params={"grant_type": "client_credential", "appid": appid, "secret": secret},
        timeout=30,
    )
    r.raise_for_status()
    resp = r.json()
    if "access_token" not in resp:
        raise RuntimeError(f"获取 access_token 失败：{resp}")
    token = resp["access_token"]
    with open(TOKEN_CACHE, "w", encoding="utf-8") as f:
        json.dump({"access_token": token, "expire_at": time.time() + resp.get("expires_in", 7200)}, f)
    return token


def http_json(method, url, body=None, params=None):
    """发起 JSON 请求，返回解析后的 dict。method: GET/POST。"""
    data = json.dumps(body, ensure_ascii=False) if isinstance(body, (dict, list)) else body
    r = requests.request(
        method,
        url,
        params=params,
        data=data,
        timeout=30,
        headers={"Content-Type": "application/json; charset=utf-8"},
    )
    r.raise_for_status()
    # 微信接口响应常不带 charset 声明，requests 会误用 apparent_encoding 猜成
    # Latin-1，导致中文变成 mojibake。微信 API 一律 UTF-8，强制指定即可。
    r.encoding = "utf-8"
    return r.json()


def upload_permanent_image(token, filepath):
    """上传永久图片素材（封面用），返回 media_id。"""
    ext = os.path.splitext(filepath)[1].lower()
    ct = EXT_CT.get(ext, "application/octet-stream")
    with open(filepath, "rb") as f:
        files = {"media": (os.path.basename(filepath), f, ct)}
        r = requests.post(
            f"{API}/material/add_material",
            params={"access_token": token, "type": "image"},
            files=files,
            timeout=60,
        )
    r.raise_for_status()
    data = r.json()
    if "media_id" not in data:
        raise RuntimeError(f"封面上传失败：{data}")
    return data["media_id"]


def find_cover_in_assets():
    """在 素材/ 目录找第一张图片作默认封面。"""
    if not os.path.isdir(ASSETS_DIR):
        return None
    for name in sorted(os.listdir(ASSETS_DIR)):
        if os.path.splitext(name)[1].lower() in EXT_CT:
            return os.path.join(ASSETS_DIR, name)
    return None


def ts_to_str(ts):
    try:
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(int(ts)))
    except Exception:
        return str(ts)


def list_drafts(token, offset=0, count=20, no_content=1, sync=True):
    """拉取草稿箱列表（**实时调用微信 API**，非本地缓存）。

    - sync=True（默认）：把完整响应当场写入 工具/草稿列表.json，作为本地镜像。
      这样「每次用 API 获取草稿列表后都同步到本地」这一约定即被强制满足——
      无论谁来调（获取脚本 / 推送脚本的判重环节），都会写盘。
    - 返回微信原始响应 dict（含 item / total_count），调用方应基于**此实时结果**
      做判重，而不是去读 草稿列表.json 文件（那是给人看的镜像，可能滞后）。
    """
    resp = http_json(
        "POST",
        f"{API}/draft/batchget",
        body={"no_content": no_content, "offset": offset, "count": count},
        params={"access_token": token},
    )
    if resp.get("errcode", 0) != 0:
        raise RuntimeError(f"获取草稿箱失败：{resp}")
    if sync:
        with open(DRAFT_LIST_FILE, "w", encoding="utf-8") as f:
            json.dump(resp, f, ensure_ascii=False, indent=2)
    return resp


def draft_title_exists(token, title, sync=True):
    """实时拉草稿箱，按标题精确判重。返回 (存在?, media_id)。

    判重依据永远是「当前草稿箱的真实状态」，因此新老两种推送方法都调它，
    保证看到的是同一份「现在的草稿列表」。
    """
    resp = list_drafts(token, sync=sync)
    for it in resp.get("item", []):
        news = (it.get("content", {}).get("news_item") or [{}])[0]
        if news.get("title", "") == title:
            return True, it.get("media_id")
    return False, None
