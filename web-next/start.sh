#!/bin/bash
# ------------------------------------------------------------------
# Agents Anywhere Web 启动脚本（next start，需先 build）
# 用法: ./web-next/start.sh
# ------------------------------------------------------------------
set -e

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$APP_DIR/.." && pwd)"
ENV_FILE="$ROOT_DIR/.env.local"
RUN_DIR="$ROOT_DIR/.local-dev"
PID_FILE="$RUN_DIR/web.pid"
LOG_FILE="$RUN_DIR/logs/web.log"
NEXT_BIN="$APP_DIR/node_modules/next/dist/bin/next"

# ---- 加载配置 ------------------------------------------------------
if [ -f "$ENV_FILE" ]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
fi

HOST="${WEB_HOST:-127.0.0.1}"
PORT="${WEB_PORT:-5174}"

cd "$APP_DIR"

# ---- 检查是否已运行 ------------------------------------------------
if [ -f "$PID_FILE" ]; then
  PID=$(cat "$PID_FILE")
  if kill -0 "$PID" 2>/dev/null; then
    echo "[ERROR] Web 已在运行 (PID: $PID)，请先执行 ./stop.sh"
    exit 1
  fi
  echo "[WARN] 残留 PID 文件已清理"
  rm -f "$PID_FILE"
fi

# ---- 检查构建产物与依赖 --------------------------------------------
if [ ! -f "$NEXT_BIN" ]; then
  echo "[ERROR] 找不到 next，请先执行：yarn install"
  exit 1
fi
if [ ! -f "$APP_DIR/.next/BUILD_ID" ]; then
  echo "[ERROR] 找不到构建产物 .next/BUILD_ID，请先执行：yarn build"
  exit 1
fi

# ---- 检查端口占用 --------------------------------------------------
if command -v lsof >/dev/null 2>&1 && lsof -i ":$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "[ERROR] 端口 $PORT 已被占用，请先停掉旧进程"
  lsof -i ":$PORT" -sTCP:LISTEN
  exit 1
fi

# ---- 启动 --------------------------------------------------------
mkdir -p "$RUN_DIR/logs"
echo "[INFO] 启动 Web (监听 $HOST:$PORT) ..."
nohup node "$NEXT_BIN" start --hostname "$HOST" --port "$PORT" >> "$LOG_FILE" 2>&1 &
PID=$!
echo $PID > "$PID_FILE"

sleep 3

if kill -0 "$PID" 2>/dev/null; then
  echo "[OK] Web 启动成功 (PID: $PID)"
  echo "[INFO] 访问地址: http://$HOST:$PORT"
  echo "[INFO] 日志文件: $LOG_FILE"
else
  echo "[ERROR] Web 启动失败，请查看日志: $LOG_FILE"
  tail -n 20 "$LOG_FILE"
  rm -f "$PID_FILE"
  exit 1
fi