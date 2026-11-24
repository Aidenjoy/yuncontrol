# utoken 账号密码登录

配置 `AGENT_SERVER_UTOKEN_URL` 后，普通用户在现有登录表单输入 utoken 用户名和密码。

## 协议兼容

复用 `POST /api/v2/auth/login`，请求结构保持 `AuthRequest`：`{"email":"utoken用户名","password":"密码"}`。`email` 在此模式下作为账号标识，可填非邮箱用户名；成功仍返回原 `AuthResponse`。本地管理员仍可提交原有邮箱及 password/passwordVerifier。普通用户的本地密码和 passwordVerifier 不再允许登录。采用客户端密码摘要的调用方需改为发送原 password，后端无法从摘要恢复 utoken 密码；Android/iOS/Desktop 的网页登录继续复用 Web 页面，无需改动其原生令牌流程。

## 身份与权限

服务端调用配置 origin 的 `/api/user/login`，检查 HTTP、success、二次验证、数字用户 ID 和状态。首次登录在同一事务中创建普通用户并绑定，按 origin＋utoken 用户 ID 唯一关联，不按用户名/邮箱自动合并，不继承上游管理员权限。并发唯一冲突后读取同一绑定；停用本地账号不能通过上游认证恢复。复用现有 users/oauth_accounts 表，无 schema 变更，无需新增迁移。

启用后 `/auth/register` 禁止普通用户注册，仅保留首次带 setup token 的管理员初始化；第三方 OAuth start/finalize 关闭，防止绕过 utoken 认证。已有会话、设备所有权、权限和远控协议保持原样。移除配置后恢复原认证行为。

## 配置

根目录 `.env.local`：`AGENT_SERVER_UTOKEN_URL=http://127.0.0.1:3000`，重启 Server 生效。配置仅由管理员控制，不接受客户端传入服务地址。认证请求直接连接配置地址，不使用环境代理或自动重定向。公网使用 HTTPS，不跨系统共享数据库，不保存密码、Cookie 或模型 key。

## 错误与有效期

密码或账号状态不满足返回 401；要求二次验证返回 409（本入口暂不支持二次验证）；上游不可用/无效响应返回 502；配置非法返回 503；本地停用/身份冲突返回 403。每次新登录验证 utoken，云大师签发自己的既有凭证；utoken 禁用或改密不会即时撤销已经签发的云大师凭证，仍遵循既有会话有效期与本地禁用机制。

## 验证记录与手动验收

2026-11-24：专用 PostgreSQL 测试库 `yuncontrol_utoken_test_20261124` 上运行认证、UToken 与架构边界测试，94 项通过；最终 UToken 定向回归 20 项通过。Web 表单、管理员路由和密码摘要回归 17 项通过，typecheck、protocol:check 通过。测试使用模拟上游身份及真实本地数据库；未使用真实 UToken 密码验证成功登录。Apifox 健康接口返回 200；实际 UToken 错误密码经完整链路返回 401，普通注册返回 403，Web 返回 200。本次没有调用任何模型接口。

手动验收：

1. 确认 UToken 服务运行，Server 已读取 `AGENT_SERVER_UTOKEN_URL`，刷新 Web 登录页。
2. 输入 UToken 用户名和密码，应直接进入工作台，无二次注册；退出再登录，本地用户 ID 不变。
3. 输入错误密码，应停留登录页；停用本地用户后，即使 UToken 密码正确也不能进入。
4. 点击「本地管理员登录」，使用原有管理员邮箱密码，应正常进入；普通本地账号应被拒绝。
5. 直接调用 `/auth/register`、第三方 OAuth start/finalize 应返回 403。
6. 停止 UToken 后普通用户登录应提示认证服务不可用；本地管理员仍可登录。
7. Android/iOS/Desktop 使用本 Server 的网页登录入口重复验收；本次未做真机验证。

## 修改密码通知（最小撤销方案）

云大师新增 `POST /api/v2/auth/revoke`。utoken 密码提交成功后发送 `{"userId":123,"changedAt":1795500000000}`，`changedAt` 为该事件固定的 Unix 毫秒时间，重试必须复用。请求头 `X-Auth-Secret` 使用双方共享、至少 32 字符的随机密钥。仅使用配置的认证实例映射，不接受客户端提供实例地址；未知身份返回 `matched:false`，不创建用户。

云大师配置 `AGENT_SERVER_AUTH_REVOKE_SECRET`；utoken 配置 `YUNCONTROL_REVOKE_URL=http://127.0.0.1:8000/api/v2/auth/revoke` 和 `YUNCONTROL_REVOKE_SECRET`（与前者一致）。公网必须 HTTPS，两端应同步时钟；超过云大师当前时间 60 秒的事件拒绝。不要在日志中打印密钥。

撤销时间存入现有 instance_settings 表，使用原子最大值处理重复、乱序和并发，无数据库迁移。新增用户令牌携带毫秒签发时间，旧版没有签发时间的令牌在收到第一次通知后失效。旧二维码、旧授权码及旧移动刷新凭证也失效。账号、设备、业务会话不删除。配置认证服务后，HTTP 鉴权与带用户 token 的新 WebSocket 握手检查该时间。已建立的 WebSocket、已发放的短期 WS/预览票据不会主动断开或即时撤销，继续使用既有生命周期；这不是即时全连接踢出方案。

通知异步发送，最多三次、单次三秒，失败记录日志，不影响改密。没有持久化队列，进程退出或重试耗尽后不保证送达；失效通知成功前，旧凭证仍有效。个人改密、管理员重置及忘记密码重置均覆盖。

改密通知验证（2026-11-24）：Server 认证及架构回归 95 项通过；补充时间戳与 WebSocket 握手后定向回归 22 项通过。utoken 通知 HTTP 模拟重试测试通过，Model/Controller 编译检查通过。未修改真实用户密码，未执行真实账号端到端改密；已运行的 utoken 需重新构建并重启以加载通知代码。
