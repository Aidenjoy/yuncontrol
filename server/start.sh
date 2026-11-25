#!/bin/bash
# ------------------------------------------------------------------
# Agents Anywhere Server 启动脚本
# 用法: ./server/start.sh
# ------------------------------------------------------------------
set -e

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$APP_DIR/.." && pwd)"
ENV_FILE="$ROOT_DIR/.env.local"
RUN_DIR="$ROOT_DIR/.local-dev"
PID_FILE="$RUN_DIR/server.pid"
LOG_FILE="$RUN_DIR/logs/server.log"
PYTHON="$APP_DIR/.venv/bin/python"

# ---- 加载配置 ------------------------------------------------------
if [ ! -f "$ENV_FILE" ]; then
  echo "[ERROR] 找不到 $ENV_FILE，请先 cp .env.example .env.local 并填写"
  exit 1
fi
set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

cd "$APP_DIR"

# ---- 检查是否已运行 ------------------------------------------------
if [ -f "$PID_FILE" ]; then
  PID=$(cat "$PID_FILE")
  if kill -0 "$PID" 2>/dev/null; then
    echo "[ERROR] Server 已在运行 (PID: $PID)，请先执行 ./stop.sh"
    exit 1
  fi
  echo "[WARN] 残留 PID 文件已清理"
  rm -f "$PID_FILE"
fi

# ---- 检查虚拟环境 --------------------------------------------------
if [ ! -x "$PYTHON" ]; then
  echo "[ERROR] 找不到 $PYTHON，请先执行：uv sync"
  exit 1
fi

# ---- 检查端口占用 --------------------------------------------------
PORT="${AGENT_SERVER_PORT:-8000}"
if command -v lsof >/dev/null 2>&1 && lsof -i ":$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "[ERROR] 端口 $PORT 已被占用，请先停掉旧进程"
  lsof -i ":$PORT" -sTCP:LISTEN
  exit 1
fi

# ---- 启动 --------------------------------------------------------
mkdir -p "$RUN_DIR/logs"
echo "[INFO] 启动 Server (监听 ${AGENT_SERVER_HOST:-127.0.0.1}:$PORT) ..."
nohup "$PYTHON" -m agent_server.main >> "$LOG_FILE" 2>&1 &
PID=$!
echo $PID > "$PID_FILE"

sleep 3

if kill -0 "$PID" 2>/dev/null; then
  echo "[OK] Server 启动成功 (PID: $PID)"
  echo "[INFO] 日志文件: $LOG_FILE"
  echo "[INFO] 首次启动请在日志里找 bootstrap token 创建管理员"
else
  echo "[ERROR] Server 启动失败，请查看日志: $LOG_FILE"
  tail -n 20 "$LOG_FILE"
  rm -f "$PID_FILE"
  exit 1
fi