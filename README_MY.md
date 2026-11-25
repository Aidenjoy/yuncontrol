# 本地开发

## 1. 新建配置文件

```bash
cd /Users/aiden/projects/vscode/yuncontrol
cp .env.example .env.local
openssl rand -hex 32        # 复制输出，下一步填到 AGENT_SERVER_SECRET
vim .env.local              # 改 AGENT_SERVER_DB_URL 的用户/密码/库名，填 AGENT_SERVER_SECRET
```

本地开发只需要改这两项：

```bash
AGENT_SERVER_DB_URL=postgresql+asyncpg://用户:密码@127.0.0.1:5432/agents_anywhere
AGENT_SERVER_SECRET=粘贴上一步的输出
```
其余保持默认（Redis 127.0.0.1:6379、PUBLIC_ORIGIN http://127.0.0.1:5174），Redis 地址不同就一起改。

## 2. 建库（只需一次，已有库跳过）

```bash
psql -U postgres -c "CREATE USER agents_anywhere WITH PASSWORD '你的密码'"
psql -U postgres -c "CREATE DATABASE agents_anywhere OWNER agents_anywhere"
```

## 3. 启动 Server（终端 1）

```bash
cd /Users/aiden/projects/vscode/yuncontrol
set -a; source .env.local; set +a
cd server
uv sync

uv run python -m agent_server.infra.db.migrations upgrade

uv run uvicorn agent_server.app:create_app --factory --host 127.0.0.1 --port 8000 --reload
或者
uv run python -m agent_server.main
```

## 4. 启动 Web（终端 2）

```bash
cd /Users/aiden/projects/vscode/yuncontrol/web-next
corepack yarn install
yarn dev
```

 install 卡住或崩溃时（国内直连官方源慢）：

```bash
export COREPACK_NPM_REGISTRY=https://registry.npmmirror.com
yarn config set --home npmRegistryServer https://registry.npmmirror.com
yarn install
```

## 5. 打开 http://127.0.0.1:5174

首次登录需要 bootstrap token，在终端 1 的日志里。

## 6. Connector（可选，终端 3）

```bash
cd /Users/aiden/projects/vscode/yuncontrol/connector
uv sync
uv run anywhere-cli configure --server-url http://127.0.0.1:8000 --connector-id conn_xxx --connector-token cxt_xxx
uv run anywhere-cli start
```

conn_xxx / cxt_xxx 在 Web 的连接器页面新建后获得。

---

# 服务器部署

## 1. 拉代码

```bash
git clone <仓库地址> /opt/agents-anywhere
cd /opt/agents-anywhere
```

## 2. 新建配置文件

```bash
openssl rand -hex 32        # 复制输出，下一步填到 AGENT_SERVER_SECRET
cp .env.example .env.local
vim .env.local
chmod 600 .env.local
```

```bash
AGENT_SERVER_DB_URL=postgresql+asyncpg://用户:密码@127.0.0.1:5432/agents_anywhere     # 改
AGENT_SERVER_SECRET=粘贴上一步的输出                                            # 填
AGENT_SERVER_PUBLIC_ORIGIN=https://aa.example.com                                 # 改
AGENT_SERVER_FILES_LOCAL_ROOT=/opt/agents-anywhere/.data/files                      # 取消注释
AGENT_SERVER_STATIC_DIR=/opt/agents-anywhere/web-next/out                           # 取消注释
```

## 3. 构建 Web

```bash
cd /opt/agents-anywhere/web-next
corepack yarn install
NEXT_OUTPUT=export AGENTS_ANYWHERE_API= yarn build
```

## 4. 建库 + 安装 Server + 建表

```bash
# 建库，只需一次，已有库跳过这两行
psql -U postgres -c "CREATE USER agents_anywhere WITH PASSWORD '你的密码'"
psql -U postgres -c "CREATE DATABASE agents_anywhere OWNER agents_anywhere"

cd /opt/agents-anywhere
set -a; source .env.local; set +a
cd server
uv sync --no-dev
uv run python -m agent_server.infra.db.migrations upgrade
uv run --no-sync python -m agent_server.main     # 看到 Uvicorn running 后 Ctrl-C，日志里有 bootstrap token
```

## 5. systemd

```bash
which uv                 # 下一步填到 ExecStart
vim /etc/systemd/system/agents-anywhere.service
```

```ini
[Unit]
Description=Agents Anywhere Server
After=network.target

[Service]
WorkingDirectory=/opt/agents-anywhere/server
EnvironmentFile=/opt/agents-anywhere/.env.local
ExecStart=/usr/local/bin/uv run --no-sync python -m agent_server.main
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

```bash
systemctl daemon-reload
systemctl enable --now agents-anywhere
journalctl -u agents-anywhere -f
```

## 6. nginx

```bash
vim /etc/nginx/conf.d/agents-anywhere.conf
```

```nginx
server {
    listen 443 ssl;
    server_name aa.example.com;
    ssl_certificate /etc/nginx/ssl/aa.example.com.pem;
    ssl_certificate_key /etc/nginx/ssl/aa.example.com.key;

    client_max_body_size 200m;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_buffering off;
        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;
    }
}
```

```bash
nginx -t && nginx -s reload
```

## 7. 打开 https://aa.example.com

首次登录需要 bootstrap token：`journalctl -u agents-anywhere | grep -i token`

## 升级

```bash
systemctl stop agents-anywhere
pg_dump -U agents_anywhere agents_anywhere > ~/backup_$(date +%F).sql

cd /opt/agents-anywhere
git pull
set -a; source .env.local; set +a
cd web-next && corepack yarn install && NEXT_OUTPUT=export AGENTS_ANYWHERE_API= yarn build && cd ..
cd server && uv sync --no-dev && uv run python -m agent_server.infra.db.migrations upgrade

systemctl start agents-anywhere
```

# 脚本（代替上面的 systemd 方式）

```bash
./server/auto.sh      # git pull + 加载 .env.local + uv sync + 迁移 + 停旧 + 启动
./server/start.sh     # 只启动
./server/stop.sh      # 只停止

./web-next/auto.sh    # git pull + 加载 .env.local + yarn install + build + 停旧 + 启动
./web-next/start.sh   # 只启动（需先 build）
./web-next/stop.sh    # 只停止
```

PID 与日志：`.local-dev/server.pid`、`.local-dev/web.pid`、`.local-dev/logs/*.log`

Web 监听地址默认 `127.0.0.1:5174`，在 `.env.local` 里用 `WEB_HOST=0.0.0.0`、`WEB_PORT=5174` 改。

这套脚本的 Web 走 `next start`（Node 进程代理 `/api/v2` 到后端），与上面「构建静态文件 + `AGENT_SERVER_STATIC_DIR`」是两种二选一的部署方式。
