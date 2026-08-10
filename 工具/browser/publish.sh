#!/usr/bin/env bash
# 一键推草稿（浏览器备用方案）：用项目内 venv 的 python 直接运行 browser_push.py
# （API 可用时优先用 api_push_draft.py；本脚本是 API 不可用时的备手）
# （不 source activate，避免 Git Bash 下 cygpath 报错的坑）
# 用法（在 Git Bash 中，进入 工具/browser/ 目录后）：
#   ./publish.sh 爵士把战场跳成了舞池            # 推 ../../文章草稿/爵士把战场跳成了舞池.wechat.html
#   ./publish.sh 路径/到/某文章.wechat.html      # 推指定 html（相对本脚本或绝对路径）
#   ./publish.sh 爵士 --force                    # 强制新建（忽略同名守卫）
#   ./publish.sh 爵士 --headless                 # 无头模式
set -e

HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE"

# 直接用 venv 内 python（跨环境稳定，不依赖 activate）；venv 在项目根，browser/ 上上级
VENV_PY="$HERE/../../venv/Scripts/python.exe"
if [ ! -f "$VENV_PY" ]; then
  echo "❌ 找不到 venv 环境，请先运行:  bash 工具/setup.sh"
  exit 1
fi

ARG="$1"
if [ -z "$ARG" ]; then
  echo "用法: ./publish.sh <文章名(不含.wechat.html) 或 完整html路径> [--force|--headless]"
  exit 1
fi

if [[ "$ARG" == */* || "$ARG" == *.html ]]; then
  TARGET="$ARG"
else
  TARGET="../../文章草稿/$ARG.wechat.html"
fi

if [ ! -f "$TARGET" ]; then
  echo "找不到文件: $TARGET"
  exit 1
fi

"$VENV_PY" browser_push.py "$TARGET" "${@:2}"
