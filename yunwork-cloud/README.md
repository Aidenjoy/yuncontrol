# yunwork-cloud

面向阿里云 Linux 的多用户云大师 Agent 控制服务。它接收 yuncontrol Server 的服务端请求，为每个用户创建或删除一个 Docker 容器，不使用数据库，也不向浏览器开放。

## 调用链与隔离边界

```text
Web → yuncontrol Server → yunwork-cloud → Docker
                         ↘ utoken 专用语言 Key 接口
```

- 浏览器只持有 Agents Anywhere 访问令牌；云主机控制密钥、Connector Token 和模型 Key 仅存在于服务端调用链。
- 用户实例 ID 是控制密钥对用户 ID 计算的 HMAC，形式为 `user-<24位十六进制>`。用户名、中文显示名和特殊字符不会进入容器名或目录名。
- 每用户目录包含 `instance.json`、权限为 `0600` 的 `container.env` 和挂载到容器 `/user` 的 `data/`。删除实例会删除整个实例目录。
- 容器不映射端口、不挂载 Docker Socket，并使用独立标签、资源限制、`cap-drop=ALL` 和 `no-new-privileges`。
- 控制服务直接在宿主机使用 Docker CLI，权限等同宿主机 Docker 管理员。它只能部署在受信任主机上，不得暴露给浏览器或公网直连。

## 准备云大师 Agent 镜像

控制服务直接作为 Python 项目运行在云主机上，本目录不提供控制服务镜像。用户容器镜像需要由云大师 Agent、DSH CLI、yuncontrol bridge/connector 及 `dsh-yunwork-platform` 的部署产物另行构建。

在镜像构建机完成构建后，将镜像导入或推送到云主机，并确保云主机上的镜像名与 `YUNWORK_CLOUD_IMAGE` 一致。默认值为 `yunwork-cloud:local`。例如已有镜像归档时可执行：

```bash
docker load -i yunwork-cloud-image.tar
docker image inspect yunwork-cloud:local
```

镜像入口必须读取控制服务写入的环境变量，启动 Connector，并将工作数据放在 `/user`。部署后应实际验证 Connector 能连接 Server、`yunwork` Runtime 能启动，不能只验证容器进程存活。

## 配置与启动

要求：Linux、Python 3.12、uv、Docker Engine。以下命令在 `yunwork-cloud/` 目录执行。

```bash
cp .env.example .env
openssl rand -hex 32
chmod 600 .env
```

把生成的随机值填入 `.env` 的 `YUNWORK_CLOUD_CONTROL_SECRET`，同一个值稍后填入 yuncontrol Server 的 `AGENT_SERVER_YUNWORK_CLOUD_SECRET`。不要使用示例值或提交 `.env`。

检查数据根和镜像配置：

```dotenv
YUNWORK_CLOUD_DATA_ROOT=/srv/yunwork-cloud/users
YUNWORK_CLOUD_IMAGE=yunwork-cloud:local
YUNWORK_CLOUD_HOST=127.0.0.1
YUNWORK_CLOUD_PORT=8090
```

控制服务和云大师容器都运行在同一台宿主机上，`YUNWORK_CLOUD_DATA_ROOT` 必须保持为宿主机绝对路径，并确保运行控制服务的系统用户有权创建和写入该目录。

首次启动或更新后，安装依赖并重启服务：

```bash
./auto.sh
curl --fail http://127.0.0.1:8090/healthz
tail -n 100 ../.local-dev/logs/yunwork-cloud.log
```

日常也可分别执行 `./stop.sh` 和 `./start.sh`。PID 文件为 `../.local-dev/yunwork-cloud.pid`，服务以当前登录用户运行。

`/healthz` 不需要鉴权，其他接口均要求 `Authorization: Bearer <控制密钥>`。服务未启用 CORS，也不应添加浏览器跨域访问。

## Server 与 utoken 配置

yuncontrol 根目录 `.env.local`：

```dotenv
AGENT_SERVER_PUBLIC_ORIGIN=https://agents.example.com
AGENT_SERVER_UTOKEN_URL=https://token.example.com
AGENT_SERVER_YUNWORK_CLOUD_URL=https://cloud-controller.example.com
AGENT_SERVER_YUNWORK_CLOUD_SECRET=<与 YUNWORK_CLOUD_CONTROL_SECRET 相同>
AGENT_SERVER_UTOKEN_CLOUD_KEY_SECRET=<与 utoken 的 YUNCONTROL_CLOUD_KEY_SECRET 相同>
```

utoken 服务环境：

```dotenv
YUNCONTROL_CLOUD_KEY_SECRET=<独立随机值，至少 32 字符>
```

`AGENT_SERVER_PUBLIC_ORIGIN` 必须是容器可访问的 Server Web/API origin；`AGENT_SERVER_UTOKEN_URL` 同时用于模型网关和认证 origin。三个地址均只接受不带路径、查询参数或用户信息的 HTTP(S) origin，生产环境应使用 HTTPS。

服务默认只绑定 `127.0.0.1`。Server 不在同一主机时，应在云主机配置 TLS 反向代理和防火墙，仅允许 Server 访问控制接口；不要直接把 8090 端口暴露到公网。

## 运维

实例目录由 Server 计算实例 ID 后定位，容器名为 `yunwork-user-<24位十六进制>`：

```bash
docker ps --filter label=com.yundashi.yunwork.managed=true
docker logs --tail=100 yunwork-user-<24位十六进制>
ls -la /srv/yunwork-cloud/users/user-<24位十六进制>
```

`container.env` 含 Connector Token 和模型 Key，只允许管理员读取，不应进入日志、工单或 API 响应。控制 API 不提供日志或文件读取能力。

创建、查询和删除均为幂等操作，同一用户的操作串行。控制服务重启后通过 `instance.json` 和 Docker inspect 恢复状态。删除会先移除受标签校验的容器，再安全删除对应实例目录；不要手工把其他目录软链接到数据根。

## 本地验证

```bash
uv run pytest
uv run ruff check .
```

测试使用假 Docker 执行层，不会删除本机真实容器或用户目录。真实部署仍需验证镜像、服务间网络、utoken 绑定、Connector 上线、Runtime 激活和端到端会话。
