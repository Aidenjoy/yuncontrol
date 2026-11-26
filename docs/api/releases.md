# 安装包发布与版本检测

管理员在「管理 → 文件管理」登记各端安装包，客户端通过两个公开接口拿到最新版本号和下载地址。

## 平台

| `platform` | 含义 |
| --- | --- |
| `desktop-macos-arm64` | 桌面端 macOS，Apple Silicon（M 系列） |
| `desktop-macos-x64` | 桌面端 macOS，Intel 芯片 |
| `desktop-windows` | 桌面端 Windows |
| `desktop-linux` | 桌面端 Linux |
| `android` | Android App |
| `ios` | iOS App |

每个平台只允许一条未删除记录：新版本通过编辑该平台的现有记录发布，删除后可以重新登记。macOS 的 M 系列和 Intel 是两个独立平台，各自维护版本号。

## 管理接口

需要管理员令牌（`Authorization: Bearer <token>`）。

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/api/v2/admin/releases?platform=&q=&limit=&offset=` | 列表，含未发布记录 |
| `POST` | `/api/v2/admin/releases` | 新增，返回 201 |
| `PUT` | `/api/v2/admin/releases/{id}` | 整条替换 |
| `DELETE` | `/api/v2/admin/releases/{id}` | 软删除，返回 204 |

写入字段：

```json
{
  "platform": "desktop-macos-arm64",
  "version": "2.2.0",
  "downloadUrl": "https://dl.example.com/yundashi-2.2.0-arm64.dmg",
  "fileName": "yundashi-2.2.0-arm64.dmg",
  "notes": "修复引导页布局。",
  "published": true
}
```

- `version`：数字点分，可带后缀（`2.2.0`、`2.2.0-beta.1`），不能带 `v` 前缀以外的自由文本。
- `downloadUrl`：`http`/`https`，不能包含用户名密码。
- `fileName` 用于界面展示和客户端保存文件名。
- `published=false` 的记录只在管理界面可见。
- 平台创建后不可修改；要换平台请删除后重新登记。

平台已有记录时新增返回 `409`，提示当前版本号并引导编辑；字段不合法返回 `422`。

## 公开接口

无需登录，响应带 `Cache-Control: no-store`。

### 每个平台的最新版本

```
GET /api/v2/releases/latest
GET /api/v2/releases/latest?platform=desktop-macos-arm64
GET /api/v2/releases/lates?type=android
```

```json
{
  "items": [
    {
      "type": "desktop-macos-arm64",
      "platform": "desktop-macos-arm64",
      "version": "2.2.0",
      "downloadUrl": "https://dl.example.com/yundashi-2.2.0-arm64.dmg",
      "fileName": "yundashi-2.2.0-arm64.dmg",
      "notes": "修复引导页布局。",
      "publishedAt": "2026-11-26T08:00:00+00:00"
    }
  ]
}
```

只返回已发布的记录，每个平台一条；未发布的平台不出现在结果里。`/lates` 与 `/latest` 返回相同结构；`type` 与 `platform` 是等价筛选参数，同时传入时必须一致，否则返回 422。返回的 `type` 与 `platform` 一致。支持 `android`、`ios`、`desktop-macos-arm64`、`desktop-macos-x64`、`desktop-windows`。下载地址来自管理员保存的发布记录，不从 health 版本推断。

### 检测是否有新版本

```
GET /api/v2/releases/check?platform=desktop-macos-arm64&currentVersion=2.1.0
```

```json
{
  "platform": "desktop-macos-arm64",
  "currentVersion": "2.1.0",
  "latestVersion": "2.2.0",
  "updateAvailable": true,
  "downloadUrl": "https://dl.example.com/yundashi-2.2.0-arm64.dmg",
  "fileName": "yundashi-2.2.0-arm64.dmg",
  "notes": "修复引导页布局。",
  "publishedAt": "2026-11-26T08:00:00+00:00"
}
```

- 不传 `currentVersion` 时，只要存在已发布版本就返回 `updateAvailable=true`。
- 平台没有已发布版本时，`latestVersion` 和 `downloadUrl` 为 `null`，`updateAvailable=false`。
- `currentVersion` 无法解析时返回 `400`。

## 版本比较

按数字段从高到低比较，缺失段补 0（`1.2` 等于 `1.2.0`）；同一数字版本下，正式版高于预发布版（`2.2.0` > `2.2.0-beta.1`），两个预发布版按后缀字符串比较。

## 数据库

`v2_58` 迁移新增 `release_files` 表，不改写任何已有数据。部分唯一索引 `uk_release_files_active_platform`（`WHERE deleted = 0`）保证每个平台只有一条未删除记录。删除为软删除（`deleted=1`），记录保留在库内。


## 旧平台约束修复（v2_59）

已执行过早期 v2_58 的数据库可能仍只允许 `desktop-macos`，新代码提交 M/Intel 标识时会被检查约束拒绝。必须执行新增 v2_59 迁移，不能靠修改已经执行过的 v2_58 修复。迁移允许两种架构标识，保留旧记录，并将有效记录唯一约束统一为按 platform 唯一；如同平台已有多条有效记录则明确停止，不自动删除。

macOS M 系列和 Intel 可各保存一条相同版本号（如 2.0.25），平台之间互不冲突；同平台升级编辑原记录。Linux 不再出现在新增选项或公开版本查询中，现有记录不物理删除。后端仅将已知唯一约束冲突转换为“平台已有版本”，不会再把检查约束或主键错误误报为版本重复。
