# 云大师插件目录

目录兼容 YunWork `dsh-community-market` 的 `market.standard-http-v1` 协议（1.0.0）。它只管理插件元数据，不代理 npm、不执行插件代码、不调用模型。安装、升级、启停和卸载继续由 YunWork 原有插件管理器处理。

## 部署配置

在 **YunControl 服务端进程/容器**环境变量中添加：

```ini
AGENT_SERVER_PLUGIN_ORIGIN=https://你的云大师域名
```

未单独配置时复用 `AGENT_SERVER_PUBLIC_ORIGIN`。只填写公网 HTTPS origin，不带路径、尾部斜线、账号或非标准端口。反向代理要将 `/api/v2/plugins/` 转发到 YunControl 后端。配置缺失或无效时配置接口返回 503；目录查询和现有登录、远控不受影响。Docker Compose 修改环境变量后应重建容器（`docker compose up -d --build --force-recreate`，使用实际部署 compose 文件）；单纯 restart 不更新容器环境变量。

启动时按既有迁移机制自动执行 `v2_57`，或在 server 目录运行 `uv run alembic upgrade head`。禁止重置数据库。

## 桌面端配置

YunWork 的工作区设置中启用 **community-market**，不要同时选择互斥的 dshMarket。进入社区市场的源管理，添加标准 HTTP 源：

```text
https://你的云大师域名/api/v2/plugins/config
```

再选择「云大师」作为当前源。桌面端只需使用现有源管理功能，无需修改或下载 YunWork 源码。源注册和选择保存到 YunWork 原有本地 storage domain；不会修改其他源的目录，也不会卸载已安装插件。该协议仅接受 HTTPS 443、无凭据、同源清单和查询接口，不要用 `http://127.0.0.1:8000` 作为正式源，也不要关闭 TLS 校验。

点击市场「刷新」时，YunWork 现有 `force` 逻辑使用 `cacheMode: reload`，替换已缓存/进行中的 HTTP 请求并重建索引；无需改写安装器或缓存机制。服务端每页强制筛选 `published` 且未删除的记录，返回 `Cache-Control: no-store`；所有页面 revision 来自同一个目录写入时钟。旧分页游标也重新执行当前上架条件。

下架的含义是从该自有源的后续查询/刷新结果移除；不会禁止其他独立源展示同名包，也不会远程卸载已安装包。离线缓存不是服务端即时撤销渠道，刷新必须成功联网。

## HTTP API

所有管理 API 使用现有管理员 Bearer 凭证；普通用户返回 403，未登录返回 401。

| 方法 | 路径（均在 `/api/v2` 下） | 说明 |
| --- | --- | --- |
| GET | `/plugins/config` | 标准源 manifest |
| GET | `/plugins/v1/plugins` | 标准公共目录页，`q/category/cursor/limit`（可重复 category，多个分类同时匹配），limit 1–100，默认50 |
| GET | `/plugins/search` | 上述目录查询别名 |
| GET | `/admin/plugins` | 管理列表，`q/category/offset/limit` |
| GET | `/admin/plugins/sync` | 查询最近一次同步进度，不请求上游 |
| POST | `/admin/plugins/sync` | 手动启动后台元数据同步，返回 202；运行中重复请求返回 409 |
| POST | `/admin/plugins` | 创建/按目录条目 ID幂等更新：`{"item":标准条目}`，新条目草稿 |
| PUT | `/admin/plugins/{id}` | 编辑，条目 ID 不可更改，不隐式上架 |
| PATCH | `/admin/plugins/{id}` | `{"status":"published"}` 上架或 `{"status":"draft"}` 下架 |
| DELETE | `/admin/plugins/{id}` | 软删除并立即排除公共查询，返回删除条目 |
| POST | `/admin/plugins/import` | `{"items":[{"item":标准条目}]}`，最多200条，整个批次原子导入 |

JSON Schema 来自 YunWork，保留原许可证，位于 `server/agent_server/core/plugin_schemas`。条目的 可选的 package.registry 必须为 npm；URL、字段、长度和版本等以原始 Schema 校验。未知协议字段不会绕过校验。

后台导入框直接接受标准 provider page 或 items 数组，自动转换管理导入请求。重复条目 ID在同一批次返回422；不同批次/并发按条目 ID 复用记录。既有记录保留上架状态；已删除条目重新导入恢复为草稿。任何条目无效时整个请求422，不会部分导入。ID 以字符串返回，避免 JavaScript bigint 精度丢失。

示例条目：

```json
{
  "id": "my-plugin",
  "name": "dsh-plugin-example",
  "displayName": "示例插件",
  "summary": "插件说明",
  "latestVersion": "1.0.0",
  "package": { "registry": "npm", "name": "dsh-plugin-example" },
  "categories": ["tools"],
  "keywords": ["example"]
}
```

请替换为真实存在且经管理员审核的 npm 包，示例本身不保证可安装。

## 数据库

新增 `plugin_catalog_info`（元数据、唯一条目 ID、草稿/上架状态、软删除）和 `plugin_catalog_flow`（操作历史），均为非自增 bigint ID，包含 `create_time/update_time/create_by/update_by/deleted`。写入通过既有 instance_settings 的 `plugin-catalog-clock` 行锁串行分配时间戳+序列 ID，保证多进程幂等；状态与流程记录同事务写入。不增加租户字段，不改变已有身份/权限/会话表。

## 验收

1. 管理员进入 `#/admin/plugins` 新增真实插件，保持未上架；桌面自有源刷新应查不到。
2. 开启上架，桌面刷新，按名称和分类搜索应能看到；原安装流程仍使用 npm 包名。
3. 关闭上架，桌面刷新后应消失；已有安装不受影响。
4. 导入同一包两次，列表仍只有一条；编辑/删除和分页可用。
5. 普通用户请求管理接口应失败，直接公共查询也不会出现草稿或软删除条目。


## 本次修改文件

- 服务端路由：`server/agent_server/api/plugins.py`、`server/agent_server/app.py`。
- 协议验证：`server/agent_server/core/plugin_catalog.py`、`server/agent_server/core/plugin_schemas/`（上游 Schema、来源说明及许可证）。
- 持久化：`server/agent_server/infra/repositories/plugin_catalog.py`、`server/agent_server/infra/db/plugin_catalog.py`、`schema.py`、`__init__.py`、`migrations.py`。
- 迁移：`server/migrations/versions/v2_57.py`。
- 后端测试：`server/tests/test_plugin_catalog.py`、`server/tests/test_database_migrations.py`。
- Web 与 Desktop renderer：各自 `src/components/admin/{plugins-page,admin-page,admin-sidebar}.tsx`、`src/features/admin/navigation.ts`。
- 页面测试：`web-next/test/admin-pages.test.mjs`（包含开关请求验证）、`desktop-workbench/renderer/test/admin-pages.test.mjs`（菜单断言同步）。
- 联调脚本：`scripts/verify-yunwork-catalog.mts`，需传入 `YUNWORK_MARKET_SOURCE`、`YUNCONTROL_TEST_AUTH_FILE` 和可选 `YUNCONTROL_TEST_URL`。只允许 localhost，认证文件为临时测试管理员 Authorization headers JSON，不得使用生产凭证。使用现有 tsx 加载器运行；不安装任何目录中的插件。
- 部署与文档：`docker/docker-compose.postgres.yml`、`docs/README.md`、本文和 `CHANGELOG.md`。

## 本次验证记录

- 后端：插件目录、原有登录、架构边界与数据库迁移共150项通过；最终补充/定向检查10项通过（包含重复验证，不合计为160个独立测试）。使用独立 `yuncontrol_market_test` 数据库。
- Web：在本机已有 Node 26.8.1 下执行 `yarn test`，578项通过；`yarn typecheck`、`yarn protocol:check`通过。Node22的测试加载器出现既有模块链接错误后，改用本机已有Node26运行；未更改项目的Node配置。
- 真实参考适配器：复用原始 `standard-http-v1`、完整目录扫描器和五分钟HTTP缓存，通过本地测试传输联调；草稿0条、上架1条、下架后旧缓存1条、显式刷新后0条。协议清单/页面经上游Schema及实际TS解析器验证，不需要部署或运行YunWork源码。
- Apifox：源配置接口HTTP200，返回标准manifest。
- 开发库：已执行v2_57，未清空原有用户/设备/会话；当前Server/Web已用原启动脚本重启，健康检查200，空公共目录200。
- 未验证：公网域名与TLS证书、桌面客户端安装包和实际npm插件安装。Desktop renderer同步了管理界面及菜单断言，未单独构建桌面安装包。
- 未调用模型接口，未安装目录中的插件，未提交或推送代码；本次不修改YunWork项目。

本地调试时，配置接口允许 localhost、回环及内网 IP 的 HTTP origin（可带端口）。公网仍需 HTTPS 443；此例外仅使服务端配置接口可访问，不会放宽云大师市场客户端自身的 HTTPS 校验。

## 管理员手动同步目录

Web 管理员「插件管理」中的「同步插件目录」读取 YunWork `dsh-community-market` 已有来源：

- 1024Store：`https://deepseek1024.com/api/v2/plugins`，每页 200 条，按总页数遍历。
- dshfind：`https://api.dshfind.com/v1/catalog`，读取完整元数据快照，复用其插件识别与风险过滤条件。

POST 请求体为 `{}`（两个来源），或 `{"sources":["1024store"]}` / `{"sources":["dshfind"]}`。不接受自定义 URL，不在服务启动、打开页面或轮询时自动触发同步。每次请求限定响应大小与超时，对临时网络错误最多请求三次。

复用现有插件资料表、流水表和实例设置，每批最多 200 条；以规范化 GitHub 仓库身份（包含已声明的子目录）去重，多个来源的原始字段保存在管理响应 `origins` 中，包含实际提供的安装命令、版本、下载地址和图标地址。公共目录沿用标准协议返回仓库身份，以及能够按来源规则确认的 npm 包与版本；原始命令不执行，也不作为安装授权。

新增插件保持下架，更新不修改已有上下架状态；同步不恢复管理员删除的记录。来源内容未变时不覆盖管理员补充的资料。图标及插件本体均不下载，不安装、不调用模型。来源任务错误单独显示在 `errors` 中；条目失败计入 `failed`，过滤条目计入 `skipped`。总数随来源读取逐步增加。

进度通过数据库共享，包含 `total/processed/created/updated/unchanged/skipped/failed`；运行任务阻止重复启动，进程中断后租约最长 10 分钟到期，可重新手动同步，已提交批次保留。该任务运行在 Server 进程中，不是独立持久任务队列。

### 同步功能 Mock 验证（2026-11-25）

- 独立测试库临时 schema：10,006 条输入，新增 10,002、更新 1、未变 1、过滤 1、失败 1；重复同步新增/更新均为 0，修改来源数据后更新 10,001 条。验证结束已清理临时 schema。
- 通过实际仓储和 API 验证：新插件下架、保留已上架状态、公共查询仅返回上架插件及安装身份、删除不恢复、重复启动 409、单来源异常不阻止另一来源处理。上游请求全部使用 MockTransport。
- 前端 Mock：打开页面不启动同步、快速重复点击只发一次请求、运行时按钮禁用、统计和异常展示、完成后刷新列表均通过；Web 类型检查和同步模块 ruff 检查通过。
- Apifox 使用仅监听本机的临时 Mock 服务：POST 同步返回 202，GET 进度返回 200、`completed`、总数/处理数/新增数均为 1；未连接真实来源或开发库，临时服务已停止。
- 未执行真实目录同步、插件本体下载/安装、完整回归或桌面安装包验证。
