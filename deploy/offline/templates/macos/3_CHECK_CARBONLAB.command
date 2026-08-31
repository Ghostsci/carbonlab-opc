#!/bin/zsh
set -u

export PATH="/usr/local/bin:/opt/homebrew/bin:/Applications/Docker.app/Contents/Resources/bin:$HOME/.orbstack/bin:/usr/bin:/bin:/usr/sbin:/sbin:${PATH:-}"

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
ENV_FILE="$ROOT_DIR/config/demo.env"
COMPOSE_FILE="$ROOT_DIR/compose.offline.yml"
OUTPUT_DIR="$ROOT_DIR/diagnostics"
mkdir -p "$OUTPUT_DIR"
OUTPUT_FILE="$OUTPUT_DIR/check-$(date +%Y%m%d-%H%M%S).txt"
PROJECT_NAME="${CARBONLAB_PROJECT_NAME:-carbonlab_competition_demo}"
DOCKER_BIN="$(command -v docker 2>/dev/null || true)"

{
  print "CarbonLab offline demo diagnostics"
  print "time=$(date '+%Y-%m-%dT%H:%M:%S%z')"
  print "host_arch=$(uname -m)"
  print "macos=$(sw_vers -productVersion 2>/dev/null || true)"
  print "docker_path=${DOCKER_BIN:-not_found}"
  print "docker_cli=$(${DOCKER_BIN:-/usr/bin/false} --version 2>/dev/null || true)"
  print "docker_compose=$(${DOCKER_BIN:-/usr/bin/false} compose version 2>/dev/null || true)"
  print "docker_daemon=$([[ -n \"$(${DOCKER_BIN:-/usr/bin/false} info 2>/dev/null)\" ]] && print ready || print unavailable)"
  print "\n--- containers ---"
  ${DOCKER_BIN:-/usr/bin/false} compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" -p "$PROJECT_NAME" ps 2>&1 || true
  print "\n--- backend health ---"
  curl -sS http://127.0.0.1:18000/api/health 2>&1 || true
  print "\n--- recent backend logs ---"
  ${DOCKER_BIN:-/usr/bin/false} compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" -p "$PROJECT_NAME" logs --tail=120 backend 2>&1 || true
} | tee "$OUTPUT_FILE"

print "\n诊断结果已保存：$OUTPUT_FILE"
read "?按回车键关闭窗口..."
