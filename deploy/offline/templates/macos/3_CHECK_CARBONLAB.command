#!/bin/zsh
set -u

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
ENV_FILE="$ROOT_DIR/config/demo.env"
COMPOSE_FILE="$ROOT_DIR/compose.offline.yml"
OUTPUT_DIR="$ROOT_DIR/diagnostics"
mkdir -p "$OUTPUT_DIR"
OUTPUT_FILE="$OUTPUT_DIR/check-$(date +%Y%m%d-%H%M%S).txt"

{
  print "CarbonLab offline demo diagnostics"
  print "time=$(date -Iseconds)"
  print "host_arch=$(uname -m)"
  print "macos=$(sw_vers -productVersion 2>/dev/null || true)"
  print "docker_cli=$(docker --version 2>/dev/null || true)"
  print "docker_compose=$(docker compose version 2>/dev/null || true)"
  print "docker_daemon=$([[ -n \"$(docker info 2>/dev/null)\" ]] && print ready || print unavailable)"
  print "\n--- containers ---"
  docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" -p carbonlab_competition_demo ps 2>&1 || true
  print "\n--- backend health ---"
  curl -sS http://127.0.0.1:18000/api/health 2>&1 || true
  print "\n--- recent backend logs ---"
  docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" -p carbonlab_competition_demo logs --tail=120 backend 2>&1 || true
} | tee "$OUTPUT_FILE"

print "\n诊断结果已保存：$OUTPUT_FILE"
read "?按回车键关闭窗口..."
