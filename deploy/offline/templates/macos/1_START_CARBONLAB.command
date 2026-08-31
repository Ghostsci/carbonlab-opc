#!/bin/zsh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
ENV_FILE="$ROOT_DIR/config/demo.env"
COMPOSE_FILE="$ROOT_DIR/compose.offline.yml"
IMAGE_ARCHIVE="$ROOT_DIR/images/carbonlab-offline-images.tar.gz"
PROJECT_NAME="carbonlab_competition_demo"
mkdir -p "$ROOT_DIR/diagnostics"

fail() {
  print -u2 "\n启动失败：$1"
  print -u2 "请运行 3_CHECK_CARBONLAB.command，并查看 diagnostics/ 目录。"
  read "?按回车键关闭窗口..."
  exit 1
}

[[ -f "$ENV_FILE" ]] || fail "缺少 config/demo.env"
[[ -f "$COMPOSE_FILE" ]] || fail "缺少 compose.offline.yml"
command -v docker >/dev/null 2>&1 || fail "没有找到 Docker。请先安装 Docker Desktop。"

if [[ "$(uname -m)" != "arm64" ]]; then
  fail "这个安装包仅支持 Apple Silicon Mac（arm64）。"
fi

if ! docker info >/dev/null 2>&1; then
  print "正在启动 Docker Desktop..."
  open -a Docker >/dev/null 2>&1 || fail "无法启动 Docker Desktop"
  for _ in {1..120}; do
    docker info >/dev/null 2>&1 && break
    sleep 2
  done
fi
docker info >/dev/null 2>&1 || fail "Docker Desktop 未在 4 分钟内就绪"

set -a
source "$ENV_FILE"
set +a

if ! docker image inspect "carbonlab-offline-backend:${CARBONLAB_IMAGE_TAG}" >/dev/null 2>&1 \
  || ! docker image inspect "carbonlab-offline-postgres-slim:${CARBONLAB_IMAGE_TAG}" >/dev/null 2>&1; then
  [[ -f "$IMAGE_ARCHIVE" ]] || fail "缺少离线镜像包 $IMAGE_ARCHIVE"
  print "首次启动：正在导入离线镜像，请耐心等待..."
  gzip -dc "$IMAGE_ARCHIVE" | docker load || fail "离线镜像导入失败"
fi

print "正在启动零碳云离线演示环境..."
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" -p "$PROJECT_NAME" up -d || fail "容器启动失败"

HEALTH_URL="http://127.0.0.1:${BACKEND_PORT}/api/health"
for _ in {1..120}; do
  if curl -fsS "$HEALTH_URL" 2>/dev/null | grep -q '"status":"ok"'; then
    FRONTEND_URL="http://127.0.0.1:${FRONTEND_PORT}/login"
    print "\n零碳云已就绪：$FRONTEND_URL"
    print "登录页点击『一键进入演示』即可。"
    open "$FRONTEND_URL"
    read "?按回车键关闭本窗口（系统会继续运行）..."
    exit 0
  fi
  sleep 2
done

docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" -p "$PROJECT_NAME" logs --tail=120 backend > "$ROOT_DIR/diagnostics/startup-backend.log" 2>&1 || true
fail "后端健康检查超时"
