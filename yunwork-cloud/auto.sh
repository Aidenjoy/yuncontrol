#!/bin/bash
# ------------------------------------------------------------------
# yunwork-cloud 一键更新脚本（装依赖 + 重启）
# 用法: ./yunwork-cloud/auto.sh
# 代码更新请自行在仓库根目录执行 git pull，本脚本不动代码
# ------------------------------------------------------------------
set -e

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
ENV_FILE="$APP_DIR/.env"

step() {
  echo ""
  echo "=================================================================="
  echo "[STEP $1/4] $2"
  echo "=================================================================="
}

step 1 "加载配置 (.env)"
if [ ! -f "$ENV_FILE" ]; then
  echo "[ERROR] 找不到 $ENV_FILE，请先 cp .env.example .env 并填写"
  exit 1
fi
set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a
echo "[OK] 配置已加载"

step 2 "安装依赖 (uv sync)"
cd "$APP_DIR"
uv sync
echo "[OK] 依赖安装完成"

step 3 "停止旧服务 (./stop.sh)"
if ./stop.sh; then
  echo "[OK] 旧服务已停止"
else
  echo "[WARN] 停止脚本返回非零，继续启动流程"
fi

step 4 "启动服务 (./start.sh)"
./start.sh

echo ""
echo "[OK] yunwork-cloud 更新完成：依赖已安装，服务已重启"
