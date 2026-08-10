#!/usr/bin/env bash
# setup.sh — 在新机器上重建「公众号工作流」的 Python 环境
# 用法：进入「公众号工作流/工具」目录后运行  bash setup.sh
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE"

ROOT="$(cd .. && pwd)"   # 项目根 = 工具/ 的上级目录

PY="${PYTHON:-python3}"
if ! command -v "$PY" >/dev/null 2>&1; then PY=python; fi
echo ">>> 使用 Python: $($PY --version 2>&1)"

if [ -f "$ROOT/venv/Scripts/python.exe" ] || [ -f "$ROOT/venv/bin/python" ]; then
  echo ">>> venv 已存在，跳过创建（如需重建请先删除 venv/）"
else
  echo ">>> 1/3 创建 venv ..."
  "$PY" -m venv "$ROOT/venv"
fi

if [ -f "$ROOT/venv/Scripts/python.exe" ]; then VENV_PY="$ROOT/venv/Scripts/python.exe"
else VENV_PY="$ROOT/venv/bin/python"; fi

echo ">>> 2/3 安装依赖 ..."
"$VENV_PY" -m pip install -U pip
"$VENV_PY" -m pip install -r "$HERE/requirements.txt"

echo ">>> 3/3 下载 Chromium（若卡在 __dirlock，删 C:/Users/<你>/AppData/Local/ms-playwright/__dirlock 后重试）..."
"$VENV_PY" -m playwright install chromium
echo "    （如需回退 Firefox：再跑  $VENV_PY -m playwright install firefox，并用 --browser firefox）"

echo
echo "✅ 环境就绪。以后发文只需:  工具/browser/publish.sh <文章名>"
