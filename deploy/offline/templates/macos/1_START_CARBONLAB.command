#!/bin/zsh -f
set -euo pipefail

# Finder launches applications with a minimal PATH. Add the standard Docker
# Desktop / OrbStack CLI locations so double-click startup behaves like Terminal.
export PATH="/usr/local/bin:/opt/homebrew/bin:/Applications/Docker.app/Contents/Resources/bin:$HOME/.orbstack/bin:/usr/bin:/bin:/usr/sbin:/sbin:${PATH:-}"

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
ENV_FILE="$ROOT_DIR/config/demo.env"
COMPOSE_FILE="$ROOT_DIR/compose.offline.yml"
IMAGE_ARCHIVE="$ROOT_DIR/images/carbonlab-offline-images.tar.gz"
PROJECT_NAME="${CARBONLAB_PROJECT_NAME:-carbonlab_competition_demo}"
mkdir -p "$ROOT_DIR/diagnostics"

fail() {
  print -u2 "\n启动失败：$1"
  print -u2 "请运行 3_CHECK_CARBONLAB.command，并查看 diagnostics/ 目录。"
  if [[ -t 0 ]]; then
    read "?按回车键关闭窗口..."
  fi
  exit 1
}

resolve_docker() {
  local candidate
  for candidate in \
    "${CARBONLAB_DOCKER_BIN:-}" \
    "$(command -v docker 2>/dev/null || true)" \
    "/usr/local/bin/docker" \
    "/opt/homebrew/bin/docker" \
    "/Applications/Docker.app/Contents/Resources/bin/docker" \
    "$HOME/.orbstack/bin/docker"; do
    if [[ -n "$candidate" && -x "$candidate" ]]; then
      print -r -- "$candidate"
      return 0
    fi
  done
  return 1
}

[[ -f "$ENV_FILE" ]] || fail "缺少 config/demo.env"
[[ -f "$COMPOSE_FILE" ]] || fail "缺少 compose.offline.yml"
DOCKER_BIN="$(resolve_docker)" || fail "没有找到 Docker 或 OrbStack。请先安装并启动 Docker Desktop/OrbStack。"

if [[ "$(uname -m)" != "arm64" ]]; then
  fail "这个安装包仅支持 Apple Silicon Mac（arm64）。"
fi

if ! "$DOCKER_BIN" info >/dev/null 2>&1; then
  print "正在启动容器运行环境..."
  open -a Docker >/dev/null 2>&1 \
    || open -a OrbStack >/dev/null 2>&1 \
    || fail "无法启动 Docker Desktop 或 OrbStack"
  for _ in {1..120}; do
    "$DOCKER_BIN" info >/dev/null 2>&1 && break
    sleep 2
  done
fi
"$DOCKER_BIN" info >/dev/null 2>&1 || fail "Docker Desktop/OrbStack 未在 4 分钟内就绪"

set -a
source "$ENV_FILE"
set +a

if ! "$DOCKER_BIN" image inspect "carbonlab-offline-backend:${CARBONLAB_IMAGE_TAG}" >/dev/null 2>&1 \
  || ! "$DOCKER_BIN" image inspect "carbonlab-offline-postgres-slim:${CARBONLAB_IMAGE_TAG}" >/dev/null 2>&1; then
  [[ -f "$IMAGE_ARCHIVE" ]] || fail "缺少离线镜像包 $IMAGE_ARCHIVE"
  print "首次启动：正在导入离线镜像，请耐心等待..."
  gzip -dc "$IMAGE_ARCHIVE" | "$DOCKER_BIN" load || fail "离线镜像导入失败"
fi

print "正在启动零碳云离线演示环境..."
"$DOCKER_BIN" compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" -p "$PROJECT_NAME" up -d || fail "容器启动失败"

HEALTH_URL="http://127.0.0.1:${BACKEND_PORT}/api/health"
for _ in {1..120}; do
  if curl -fsS "$HEALTH_URL" 2>/dev/null | grep -q '"status":"ok"'; then
    FRONTEND_URL="http://127.0.0.1:${FRONTEND_PORT}/login"
    print "\n零碳云已就绪：$FRONTEND_URL"
    print "登录页点击『一键进入演示』即可。"
    if [[ "${CARBONLAB_NO_BROWSER:-0}" != "1" ]]; then
      open "$FRONTEND_URL"
    fi
    if [[ -t 0 ]]; then
      read "?按回车键关闭本窗口（系统会继续运行）..."
    fi
    exit 0
  fi
  sleep 2
done

"$DOCKER_BIN" compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" -p "$PROJECT_NAME" logs --tail=120 backend > "$ROOT_DIR/diagnostics/startup-backend.log" 2>&1 || true
fail "后端健康检查超时"
