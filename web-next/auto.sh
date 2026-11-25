#!/bin/bash
# ------------------------------------------------------------------
# Agents Anywhere Web 一键更新脚本（拉代码 + 装依赖 + 构建 + 重启）
# 用法: ./web-next/auto.sh
# ------------------------------------------------------------------
set -e

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$APP_DIR/.." && pwd)"
ENV_FILE="$ROOT_DIR/.env.local"

step() {
  echo ""
  echo "=================================================================="
  echo "[STEP $1/6] $2"
  echo "=================================================================="
}

step 1 "拉取最新代码 (git pull)"
cd "$ROOT_DIR"
git pull --ff-only
echo "[OK] 代码已更新: $(git rev-parse --short HEAD)"

step 2 "加载配置 (.env.local)"
if [ -f "$ENV_FILE" ]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
  echo "[OK] 配置已加载"
else
  echo "[WARN] 未找到 $ENV_FILE，使用默认后端地址 http://127.0.0.1:8000"
fi

step 3 "安装依赖 (yarn install)"
cd "$APP_DIR"
yarn install
echo "[OK] 依赖安装完成"

step 4 "构建前端 (yarn build)"
yarn build
echo "[OK] 前端构建完成"

step 5 "停止旧服务 (./stop.sh)"
if ./stop.sh; then
  echo "[OK] 旧服务已停止"
else
  echo "[WARN] 停止脚本返回非零，继续启动流程"
fi

step 6 "启动服务 (./start.sh)"
./start.sh

echo ""
echo "[OK] Web 更新完成：代码 + 依赖 + 构建 + 服务已重启"