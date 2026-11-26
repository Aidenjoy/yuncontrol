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

密码或账号状态不满足返回 401；要求二次验证返回 409（本入口暂不支持二次验证）；上游不可用/无效响应返回 502；配置非法返回 503；本地停用/身份冲突返回 403。每次新登录验证 utoken，云大师Agent签发自己的既有凭证；utoken 禁用或改密不会即时撤销已经签发的云大师Agent凭证，仍遵循既有会话有效期与本地禁用机制。

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

云大师Agent新增 `POST /api/v2/auth/revoke`。utoken 密码提交成功后发送 `{"userId":123,"changedAt":1795500000000}`，`changedAt` 为该事件固定的 Unix 毫秒时间，重试必须复用。请求头 `X-Auth-Secret` 使用双方共享、至少 32 字符的随机密钥。仅使用配置的认证实例映射，不接受客户端提供实例地址；未知身份返回 `matched:false`，不创建用户。

云大师Agent配置 `AGENT_SERVER_AUTH_REVOKE_SECRET`；utoken 配置 `YUNCONTROL_REVOKE_URL=http://127.0.0.1:8000/api/v2/auth/revoke` 和 `YUNCONTROL_REVOKE_SECRET`（与前者一致）。公网必须 HTTPS，两端应同步时钟；超过云大师Agent当前时间 60 秒的事件拒绝。不要在日志中打印密钥。

撤销时间存入现有 instance_settings 表，使用原子最大值处理重复、乱序和并发，无数据库迁移。新增用户令牌携带毫秒签发时间，旧版没有签发时间的令牌在收到第一次通知后失效。旧二维码、旧授权码及旧移动刷新凭证也失效。账号、设备、业务会话不删除。配置认证服务后，HTTP 鉴权与带用户 token 的新 WebSocket 握手检查该时间。已建立的 WebSocket、已发放的短期 WS/预览票据不会主动断开或即时撤销，继续使用既有生命周期；这不是即时全连接踢出方案。

通知异步发送，最多三次、单次三秒，失败记录日志，不影响改密。没有持久化队列，进程退出或重试耗尽后不保证送达；失效通知成功前，旧凭证仍有效。个人改密、管理员重置及忘记密码重置均覆盖。

改密通知验证（2026-11-24）：Server 认证及架构回归 95 项通过；补充时间戳与 WebSocket 握手后定向回归 22 项通过。utoken 通知 HTTP 模拟重试测试通过，Model/Controller 编译检查通过。未修改真实用户密码，未执行真实账号端到端改密；已运行的 utoken 需重新构建并重启以加载通知代码。


## 当前页面内注册与独立管理员入口

- 普通登录页的「注册」在当前页面显示表单，仅 Web 提供内嵌注册；Desktop 保留原有外部注册入口。表单读取 `AGENT_SERVER_UTOKEN_URL` 的现有 `/api/status`，发码分别调用其 `/api/verification` 或 `/api/phone_verification`，注册调用其 `/api/user/register`。
- 当前 Server 的 `/api/v2/auth/utoken/config`、`/api/v2/auth/utoken/code`、`/api/v2/auth/utoken/register` 只转发固定上游接口。验证码生成、存储、邮件/短信发送、校验及账号创建完全在 token 服务执行；不用本地邮件设置，不写本地账号，不发登录会话，不共享 Cookie，不自动重试注册/发码。
- 注册完成返回当前登录表单，提示用户登录；随后登录才按既有 token 认证流程建立本地身份关联。
- 普通登录界面隐藏「本地管理员登录」切换。Web 访问 `/admin-login` 会转到 `/#/admin-login`，也可直接使用 `http://<当前域名或IP>:<端口>/#/admin-login`；Desktop renderer 同样识别 `#/admin-login`。管理员认证仍由原后端接口校验，地址不是权限校验的替代。
- 不修改 token 项目的代码、配置、邮件系统或原站注册入口。上游开启人机校验时，当前登录站点域名须在其现有 Turnstile Site Key 的允许范围内；不能绕过或关闭校验。验证码与注册需各自新的校验令牌。
- 更新 Web/Desktop 和 Server 后生效；本次不调用真实发码或注册接口，不触发邮件、短信或账号创建。


### 邮箱发码故障处理

Web 注册表单不再提供邀请码输入；发码请求与注册提交分别管理忙碌状态，发码时不禁用输入框，避免移动端键盘收起造成页面跳动。验证码请求发起后保留 60 秒冷却，失败也不自动重试；错误信息固定区域显示，人机校验通过 reset 更新，不销毁重建整个控件。

若 token 的 `/api/verification` 返回 `success=false,message=EOF`，本项目返回 502 并提示 token 邮件服务连接中断。SMTP 配置、认证和发送故障需在 token 服务排查；当前项目不接管邮件发送，也不更改 token 的直注册流程。

邮箱发码、短信、注册配置、注册提交及登录统一使用 `AGENT_SERVER_UTOKEN_URL`，确保验证码生成和验证由同一个 token 实例处理。
