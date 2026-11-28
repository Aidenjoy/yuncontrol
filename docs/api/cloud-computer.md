# 云电脑 API

云电脑为每个 Agents Anywhere 用户维护一个独立云大师 Agent 容器。浏览器只调用 yuncontrol Server，由 Server 创建当前用户的 Connector、解析其 utoken 数字身份并取得桌面端复用的「客户端语言模型专用（不建议用于其他用途）」Key，再调用云主机控制服务。

## 配置

以下值全部存在且有效时功能才可用：

| 配置 | 用途 |
| --- | --- |
| `AGENT_SERVER_YUNWORK_CLOUD_URL` | `yunwork-cloud` 控制服务 origin |
| `AGENT_SERVER_YUNWORK_CLOUD_SECRET` | 云主机控制 Bearer 密钥，至少 32 字符 |
| `AGENT_SERVER_UTOKEN_URL` | utoken 服务 origin，同时作为容器模型与认证 origin |
| `AGENT_SERVER_UTOKEN_CLOUD_KEY_SECRET` | utoken 专用 Key 接口共享密钥，至少 32 字符 |
| `AGENT_SERVER_PUBLIC_ORIGIN` | 容器访问 Server 的公开 origin |

utoken 侧必须配置相同的 `YUNCONTROL_CLOUD_KEY_SECRET`。该内部接口为 `POST /api/yuncontrol/cloud-key`，只接受 `X-Cloud-Key-Secret` 服务凭证和数字 `user_id`，响应带 `Cache-Control: no-store`。它不是浏览器 API，不接收密码，也不应在日志中记录请求头或响应 Key。

未配置时 `GET` 返回 `configured=false` 和 `phase=disabled`，供 Web 显示部署提示；`POST`、`DELETE` 返回 503。云主机部署见 [yunwork-cloud README](../../yunwork-cloud/README.md)。

## Server 接口

三个接口都要求当前用户的 Agents Anywhere Bearer 访问令牌，路径位于 `/api/v2`：

```text
GET    /cloud-computer
POST   /cloud-computer
DELETE /cloud-computer
```

响应只包含安全字段：

```json
{
  "configured": true,
  "phase": "provisioning",
  "containerState": "created",
  "connectorId": "conn_example",
  "displayName": "云电脑",
  "updatedAt": "2026-11-03T00:00:00Z",
  "error": null
}
```

`phase` 为 `disabled`、`provisioning`、`running` 或 `error`。`running` 仅表示容器运行；Web 还会确认 Connector 在线，并发现、配置和激活 `yunwork` Runtime。只有三者均可用时开关才显示已开启。响应不包含 Connector Token、模型 Key、控制密钥或容器日志。

### 查询或恢复进度

```bash
curl --fail \
  -H "Authorization: Bearer $AGENTS_ANYWHERE_TOKEN" \
  https://agents.example.com/api/v2/cloud-computer
```

没有实例时返回 `disabled`。已有实例会结合云主机和 Docker 实际状态返回进度，因此页面刷新、跨页离开或控制服务重启后仍可恢复显示。

### 开启

```bash
curl --fail -X POST \
  -H "Authorization: Bearer $AGENTS_ANYWHERE_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{}' \
  https://agents.example.com/api/v2/cloud-computer
```

Server 使用当前用户确定性的 Connector 身份，重复开启不会重复创建设备。创建失败会尝试删除残留实例和 Connector。账号未绑定有效 utoken 数字身份时返回 409；依赖服务错误使用安全错误文案，不回显上游响应体或密钥。

### 关闭并删除

```bash
curl --fail -X DELETE \
  -H "Authorization: Bearer $AGENTS_ANYWHERE_TOKEN" \
  https://agents.example.com/api/v2/cloud-computer
```

此操作先删除容器和该用户的全部云端文件，再删除属于当前用户的云端 Connector，且无法恢复。重复关闭保持幂等。Web 会在确认框中明确提示数据删除，完成后刷新设备列表。

## 客户端范围

本次仅 Web 设置页提供「云电脑」开关和中英文状态展示。Android、iOS 和 Desktop 尚未加入该开关，但可使用同一套已认证 Server API 后续接入。Web 不新增 Next.js Route Handler，继续兼容 `NEXT_OUTPUT=export` 静态导出与 Server 同源托管。
