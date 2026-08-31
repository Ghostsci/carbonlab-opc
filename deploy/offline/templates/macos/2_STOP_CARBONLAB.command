#!/bin/zsh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
docker compose \
  --env-file "$ROOT_DIR/config/demo.env" \
  -f "$ROOT_DIR/compose.offline.yml" \
  -p carbonlab_competition_demo \
  down
print "零碳云演示环境已停止，演示数据已保留。"
read "?按回车键关闭窗口..."
