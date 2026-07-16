# Phase 1 多任务监控使用说明

Toyoko Tracker 0.7.0 的 Phase 1 将原来的单一检索会话升级为持久化的多任务
工作区。WebUI 与桌面版共用同一套任务、调度和结果数据。

## 创建与选择任务

1. 打开左侧 **监控任务**。
2. 点击 **新建任务**。新任务会复制当前任务的检索条件，并保持暂停状态。
3. 点击任务卡片进行选择。
4. 当前选择会同步到顶部操作栏、空房检索、空房监控和价格日历。

浏览器会记住最后选择的任务。若该任务之后被删除，界面会自动选择默认任务。

## 编辑与保存条件

1. 在任务详情中点击 **编辑条件**。
2. 在 **空房检索**中修改日期、酒店、人数、房间、吸烟条件、房型、会员状态、
   酒店品牌和检索间隔。
3. 点击顶部 **保存任务**，只保存条件而不启动检索。
4. 点击 **单次检索**执行一轮，或点击 **启动**开始循环监控。

启动或单次检索也会先把当前条件写入选中的任务。任务只保存检索字段；Telegram、
Bark、Server 酱、SMTP 等通知地址和凭据仍是当前安装的全局设置。

## 管理任务

任务详情提供以下操作：

- **复制**：创建一份暂停的任务副本；
- **重命名**：修改显示名称；
- **上移 / 下移**：调整任务列表顺序；
- **暂停 / 启动**：只控制当前任务；
- **删除**：删除任务及其运行记录；系统始终保留至少一个默认兼容任务。

编辑、排序、暂停和删除都使用修订号检查。若另一个页面先修改了同一任务，界面会
重新读取最新记录，避免旧页面覆盖新数据。

## 查看运行状态

任务详情显示：

- 当前运行状态；
- 本轮完成数 / 酒店总数；
- 下一次检索时间；
- 当前结果数量；
- 最近错误；
- 最近运行记录。

顶部概览还显示全局 Provider 节流状态，包括正在请求、等待请求和冷却中的来源。
所有任务、单次检索和价格日历共用此访问控制。

## 调度与暂停行为

- 应用进程只运行一个任务协调器。
- 多个活跃任务按小批次公平轮转，大任务不会长期占用队列。
- 暂停一个任务会取消它的后续工作，并让已经开始的请求有序结束。
- 其他任务继续运行。
- 应用重启后会清理中断的运行记录，并按照每个任务保存的启动/暂停意图恢复。

## 原有接口兼容

原来的顶部 **单次检索 / 启动 / 停止**按钮继续可用，但现在只操作当前选中的
任务。`/start`、`/stop`、`/status` 与结果接口也支持 `task_id`；省略时使用
默认任务。

## English quick guide

Open **Monitor Tasks** to create, copy, rename, reorder, pause, resume, edit,
save, or delete persisted monitor tasks. Selecting a task also selects the
search form, command bar, monitor results, and price-calendar scope. Use
**Save Task** to persist conditions without running, **Scan Once** for one
round, or **Start** for recurring monitoring. Every task shares one fair
scheduler and one installation-wide Provider pacing/cooldown gate.
