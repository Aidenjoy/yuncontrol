# 云大师 Runtime（yunwork）

云大师是独立类型 `yunwork`，显示名称「云大师」，推荐排序等级为 0；保留原 DSH、Codex、Claude。

## 接入边界

复用 DSH Bridge 2.x 的线协议和执行实现，内部 initialize 仍使用 `dsh` 以保持插件能力兼容。Connector 在隔离边界将结构化 `runtime` 字段映射为 `yunwork`，不替换正文、模型 ID 或原生业务 ID。云大师使用独立 Router（`router/yunwork`）、密钥、Sync 订阅、发现文件 `~/.agents-anywhere/yunwork-bridge/connector.json`；父 Connector 退出时一起清理。DSH 入口不变，双方不回退、不共用发现文件。

Bridge 插件新增 `runtimeType: yunwork` 配置；默认仍为 `dsh`。云大师默认状态目录为 `~/.agents-anywhere/yunwork-bridge-next`，不读取 DSH 的旧状态迁移目录；其会话仍由 YunWork 自身的 DSH_HOME 管理。YunWork 和原版 DSH 必须使用各自的应用数据/Profile 目录，不能配置成同一个 DSH_HOME。

## 发布与连接

1. 将 YunControl 本次 Connector 与 `dsh-bridge-next` 修改提交到 `Aidenjoy/yuncontrol`。
2. YunWork 的 Bridge 打包来源改为该仓库；Stable/Beta/Next 的 Bridge 配置传入 `runtimeType: yunwork`。
3. 在 YunWork 仓库准备新版 Bridge 依赖后重新构建发布。旧安装包内置 Connector 和 Bridge 不会随 Server 更新。
4. 启动 YunWork，启用远程连接并连接自己的 YunControl Server；设备页刷新后添加「云大师」。
5. 服务器按 Connector 上报的 Runtime 元数据提供能力与配置；无需共享数据库，无数据库迁移。Web/Desktop、Android、iOS 更新后均优先展示云大师。

验收需覆盖：原 DSH/YunWork 同时运行各自发现、断开云大师不影响 DSH、独立会话同步、审批和中断、各端排序与新建会话。本次验证不得调用产生费用的模型接口。

## 本次检查

- 原 DSH Provider、Bridge 客户端、同步、快照、检查点及主 Router 回归：90 项通过。
- Web Runtime 实例回归：11 项通过；类型及已配置实例均验证云大师优先。
- Web 与 Bridge TypeScript 类型检查通过；Bridge 默认/云大师配置目录隔离检查通过。
- 双本地模拟 Bridge 并行握手通过，验证 Router、密钥、发现文件、订阅和身份隔离，并验证父进程停止后清理子发现文件。
- YunWork 发布策略 19 项通过，Next/Beta 渠道一致性检查通过。
- 未调用模型接口；未重新构建 YunWork、Android 或 iOS 安装包，未进行真实 YunWork 会话端到端验收。
- Desktop Renderer 类型检查未完成：该子项目现有依赖/lock 安装状态不完整；对应共享 Web 代码已完成类型检查。


## 首次启动与字段转换

云大师启动器传入 `YUNWORK_ANYWHERE_RUNTIME_TYPE=yunwork` 后，Connector RPC Host 在发出 ready 前发布 DSH 与云大师各自的 Bridge 发现文件；普通 DSH 启动仍按原路径发布 DSH，不接管其他云大师进程的发现文件。云大师使用独立 Router，不重新挂载原 DSH、Control、Logs 服务。独立 Bridge 启动失败会记录警告，不阻断原有控制通道；后续探测仍可重试。父进程关闭时一起清理。

运行时转换仅处理初始化身份、会话记录、时间线 source、能力条目等已声明的协议字段。工具参数、正文、模型元数据和命令业务返回保持原样，不做递归字符串或同名字段替换；时间线内容及其哈希保持一致。
