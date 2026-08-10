#!/usr/bin/env bash
# 把 技能/ 下的各技能复制到用户级技能目录，使其在本机所有项目可用。
# 用法：bash 技能/install_skills.sh
#
# 说明：智能体（如 WorkBuddy）会自动发现 ~/.workbuddy/skills/ 与
# <工作区>/.workbuddy/skills/ 下的技能，并按 SKILL.md 的 description 在相关任务时自动加载。
# 本脚本只是把便携技能源（技能/）装到那个位置，等价于让智能体手动复制。

set -euo pipefail

SRC="$(cd "$(dirname "$0")" && pwd)"
DEST="${HOME}/.workbuddy/skills"

mkdir -p "$DEST"

count=0
for d in "$SRC"/*/; do
  [ -d "$d" ] || continue
  name="$(basename "$d")"
  # 覆盖合并复制：不用 rm -rf 先删旧目录（部分环境/沙箱会拦截 rm 或拒绝中文路径）。
  # 技能均为纯 SKILL.md 单文件，合并覆盖即可，无旧文件残留问题。
  mkdir -p "$DEST/$name"
  cp -r "$d/." "$DEST/$name/"
  echo "已安装技能: $name -> $DEST/$name"
  count=$((count + 1))
done

if [ "$count" -eq 0 ]; then
  echo "未在 $SRC 找到任何技能子目录。"
  exit 1
fi

echo "完成，共安装 $count 个技能。新开对话后，智能体在相关任务会按 description 自动加载。"
