#!/bin/bash
# ------------------------------------------------------------------
# Agents Anywhere Web 一键更新脚本（装依赖 + 构建 + 重启）
# 用法: ./web-next/auto.sh
# 代码更新请自行在仓库根目录执行 git pull，本脚本不动代码
# ------------------------------------------------------------------
set -e

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$APP_DIR/.." && pwd)"
ENV_FILE="$ROOT_DIR/.env.local"

step() {
  echo ""
  echo "=================================================================="
  echo "[STEP $1/5] $2"
  echo "=================================================================="
}

step 1 "加载配置 (.env.local)"
if [ -f "$ENV_FILE" ]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
  echo "[OK] 配置已加载"
else
  echo "[WARN] 未找到 $ENV_FILE，使用默认后端地址 http://127.0.0.1:8000"
fi

step 2 "安装依赖 (yarn install)"
cd "$APP_DIR"
yarn install
echo "[OK] 依赖安装完成"

step 3 "构建前端 (yarn build)"
yarn build
echo "[OK] 前端构建完成"

step 4 "停止旧服务 (./stop.sh)"
if ./stop.sh; then
  echo "[OK] 旧服务已停止"
else
  echo "[WARN] 停止脚本返回非零，继续启动流程"
fi

step 5 "启动服务 (./start.sh)"
./start.sh

echo ""
echo "[OK] Web 更新完成：依赖 + 构建 + 服务已重启"