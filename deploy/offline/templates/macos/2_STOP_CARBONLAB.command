#!/bin/zsh
set -euo pipefail

export PATH="/usr/local/bin:/opt/homebrew/bin:/Applications/Docker.app/Contents/Resources/bin:$HOME/.orbstack/bin:/usr/bin:/bin:/usr/sbin:/sbin:${PATH:-}"

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_NAME="${CARBONLAB_PROJECT_NAME:-carbonlab_competition_demo}"
DOCKER_BIN="$(command -v docker 2>/dev/null || true)"
[[ -n "$DOCKER_BIN" && -x "$DOCKER_BIN" ]] || {
  print -u2 "未找到 Docker 或 OrbStack，请确认容器运行环境已安装。"
  read "?按回车键关闭窗口..."
  exit 1
}
"$DOCKER_BIN" compose \
  --env-file "$ROOT_DIR/config/demo.env" \
  -f "$ROOT_DIR/compose.offline.yml" \
  -p "$PROJECT_NAME" \
  down
print "零碳云演示环境已停止，演示数据已保留。"
read "?按回车键关闭窗口..."
