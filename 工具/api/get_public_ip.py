# -*- coding: utf-8 -*-
"""获取当前公网 IP（用于微信公众平台 IP 白名单配置）。

用法:
  python get_public_ip.py
输出:
  一行纯 IP，如 171.108.206.238；失败则打印错误并退出码 1。
"""
import re
import sys

import requests

# 备用源，按序尝试（任一成功即返回）
IP_SOURCES = [
    "https://api.ipify.org",
    "https://ipinfo.io/ip",
    "https://myip.ipip.net",
    "https://ifconfig.me/ip",
]


def get_public_ip() -> str | None:
    for url in IP_SOURCES:
        try:
            r = requests.get(url, timeout=10)
            m = re.search(r"(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})", r.text or "")
            if m:
                return m.group(1)
        except Exception:
            continue
    return None


if __name__ == "__main__":
    ip = get_public_ip()
    if ip:
        print(ip)
    else:
        print("获取公网 IP 失败（网络异常或服务不可用）", file=sys.stderr)
        sys.exit(1)
