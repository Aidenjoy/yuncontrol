# yuncontrol 部署说明

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
AGENT_SERVER_DB_URL=postgresql+asyncpg://yuncontrol:密码@127.0.0.1:5432/yuncontrol
AGENT_SERVER_SECRET=粘贴上一步的输出
```
其余保持默认（Redis 127.0.0.1:6379、PUBLIC_ORIGIN http://127.0.0.1:5174），Redis 地址不同就一起改。

## 2. 建库（只需一次，已有库跳过）

```bash
psql -U postgres -c "CREATE USER yuncontrol WITH PASSWORD '你的密码'"
psql -U postgres -c "CREATE DATABASE yuncontrol OWNER yuncontrol"
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

卡住或崩溃时（国内直连官方源）：
```bash
export PIP_INDEX_URL=http://mirrors.cloud.aliyuncs.com/pypi/simple
uv sync
或者
uv sync --index-url http://mirrors.cloud.aliyuncs.com/pypi/simple --refresh

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
git clone git@github.com:Aidenjoy/yuncontrol.git ~/yuncontrol
cd ~/yuncontrol
```

## 2. 新建配置文件

```bash
cd ~/yuncontrol
openssl rand -hex 32        # 复制输出，下一步填到 AGENT_SERVER_SECRET
cp .env.example .env.local
vim .env.local
chmod 600 .env.local
```

```bash
AGENT_SERVER_DB_URL=postgresql+asyncpg://yuncontrol:密码@127.0.0.1:5432/yuncontrol   # 改
AGENT_SERVER_SECRET=粘贴上一步的输出                                              # 填
AGENT_SERVER_REDIS_URL=redis://:密码@127.0.0.1:6379/0                            # 改
AGENT_SERVER_HOST=127.0.0.1
AGENT_SERVER_PORT=8000
AGENT_SERVER_PUBLIC_ORIGIN=https://agent.yundashi.com
AGENTS_ANYWHERE_API=                                                              # 留空，浏览器走同源
AGENT_SERVER_FILES_LOCAL_ROOT=./.data/files                                      # 相对 server/，已 gitignore
WEB_HOST=127.0.0.1
WEB_PORT=5174
```

写进文件的路径不能用 `~`，非 root 用户把 `/root` 换成 `/home/你的用户名`。

## 3. 建库（只需一次，已有库跳过）

```bash
psql -U postgres -c "CREATE USER yuncontrol WITH PASSWORD '你的密码'"
psql -U postgres -c "CREATE DATABASE yuncontrol OWNER yuncontrol"
```

## 4. 启动

```bash
cd ~/yuncontrol
./server/auto.sh
./web-next/auto.sh
```

## 5. nginx

```bash
vim /etc/nginx/conf.d/agent.yundashi.com.conf
```

```nginx
server {
    listen 80;
    server_name agent.yundashi.com;
    return 301 https://agent.yundashi.com$request_uri;
}

server {
    listen 443 ssl;
    server_name agent.yundashi.com;

    ssl_certificate /etc/nginx/ssl/yundashi.com.pem;
    ssl_certificate_key /etc/nginx/ssl/yundashi.com.key;
    ssl_protocols TLSv1.2 TLSv1.3;
    client_max_body_size 100m;

    location /api/ {
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

    location / {
        proxy_pass http://127.0.0.1:5174;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

```bash
nginx -t && nginx -s reload
```

## 6. 打开 https://agent.yundashi.com

首次登录需要 bootstrap token：

```bash
grep -i token ~/yuncontrol/.local-dev/logs/server.log
```

## 升级

```bash
cd ~/yuncontrol
pg_dump -U yuncontrol yuncontrol > ~/backup_$(date +%F).sql
git pull                # 自己控制版本，auto.sh 不拉代码
./server/auto.sh
./web-next/auto.sh
```

## 日志

```bash
tail -f ~/yuncontrol/.local-dev/logs/server.log      # 后端
tail -f ~/yuncontrol/.local-dev/logs/web.log         # 前端 Node 进程
tail -f ~/.agents-anywhere/logs/runtime-*.jsonl      # Connector
```

浏览器里的报错看 F12 Console / Network，不在 `web.log` 里。

后端日志不自动轮转，加 logrotate：

```bash
sudo tee /etc/logrotate.d/yuncontrol >/dev/null <<'EOF'
/root/yuncontrol/.local-dev/logs/*.log {
    daily
    rotate 14
    size 100M
    missingok
    notifempty
    copytruncate
    compress
    delaycompress
}
EOF
```

## 启停脚本

```bash
cd ~/yuncontrol
./server/auto.sh      # 加载 .env.local + uv sync + 迁移 + 停旧 + 启动
./server/start.sh     # 只启动
./server/stop.sh      # 只停止

./web-next/auto.sh    # 加载 .env.local + yarn install + build + 停旧 + 启动
./web-next/start.sh   # 只启动（需先 build）
./web-next/stop.sh    # 只停止
```

PID：`.local-dev/server.pid`、`.local-dev/web.pid`

两个 `auto.sh` 都不执行 `git pull`，代码版本自己在根目录控制。


# 服务器环境
uv
curl -LsSf https://astral.sh/uv/install.sh | sh

node
1. gitee镜像安装nvm（避开github连不上）
git clone https://gitee.com/mirrors/nvm.git ~/.nvm
cd ~/.nvm
git checkout `git describe --abbrev=0 --tags`
2. 写入全局环境变量（所有终端生效）
echo ". ~/.nvm/nvm.sh" >> /etc/profile
source /etc/profile
3. 设置国内镜像并安装24
export NVM_NODEJS_ORG_MIRROR=https://npmmirror.com/mirrors/node
nvm install 24
nvm use 24
nvm alias default 24
4. 验证
node -v
npm -v

yarn
启用corepack，生成yarn/pnpm命令
corepack enable
source /etc/profile
yarn --version