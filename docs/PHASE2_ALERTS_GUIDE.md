# Phase 2：价格提醒与通知策略

Phase 2 为每个监控任务增加独立的价格规则和通知策略。通知渠道及其密钥仍是
全局设置；规则、静默时段、聚合和摘要则属于当前选中的监控任务。

## 1. 创建价格提醒

进入 **推送设定 → 价格提醒与通知策略**，选择当前监控任务后添加规则。

支持四种规则：

1. **目标价**：最低可用价、会员价或非会员价低于指定金额时触发。
2. **会员价**：会员价低于指定金额时触发。
3. **降价**：与同一规则、酒店和入住日期的上一条观测比较，可按金额或百分比触发。
4. **空房变化**：监测出现空房、空房消失或任意状态变化。

每条规则可以限定：

- 当前任务的全部酒店或单家酒店；
- 单日或日期区间；
- 最低价、会员价、非会员价口径；
- 普通或紧急级别。

降价规则的首条有效观测只建立价格基线，不产生降价提醒。目标价和会员价规则
在首次观测已经满足阈值时会正常触发。

## 2. 静默时段

填写 IANA 时区，例如 `Asia/Shanghai`、`Asia/Tokyo` 或
`America/New_York`，再设置静默开始和结束时间。

- 同日窗口示例：`13:00 → 17:00`。
- 跨午夜窗口示例：`23:00 → 07:00`。
- 静默期间产生的普通事件会持久化排队，在静默结束后发送。
- 勾选“紧急规则跳过静默/摘要”后，紧急规则立即进入发送队列。

## 3. 消息聚合

聚合窗口用于把短时间内产生的多个提醒合并成一条消息。例如设为 120 秒时，
同一任务在窗口内的目标价、会员价和降价事件会进入同一个批次。

同一规则在冷却时间内连续触发时会增加事件的发生次数，并更新为最新价格，
避免重复发送大量相同内容。

## 4. 每日摘要

将摘要模式设为 **每日摘要** 并选择本地时间。普通提醒会保存在持久化队列中，
到指定时间合并发送。若摘要时间落在静默窗口内，发送时间顺延到静默结束。

应用重启时：

- 已排队的摘要继续保留；
- 发送过程中被中断的批次重新进入队列；
- 已成功渠道不会在部分失败重试时重复发送；
- 失败详情会去除密钥、密码和令牌形式的内容。

## 5. 提醒历史和价格日历

提醒历史显示：

- 规则、酒店、入住日期与触发类型；
- 立即、聚合、静默队列或每日摘要模式；
- 每个渠道的发送、排队或失败状态；
- 可重试批次的后续结果。

价格日历会在对应日期显示提醒数量徽标；紧急事件使用红色徽标。

## 6. API

主要接口：

- `GET/POST /api/v1/alerts/rules`
- `GET/PATCH/DELETE /api/v1/alerts/rules/<rule_id>`
- `POST /api/v1/alerts/rules/preview`
- `GET/PATCH /api/v1/alerts/policy`
- `GET /api/v1/alerts/history`
- `POST /api/v1/alerts/batches/<batch_id>/retry`
- `GET /api/v1/alerts/calendar-badges`

所有规则写入和策略写入都支持 `expected_revision` 乐观并发控制。

---

## English quick guide

Each monitor task owns its price rules and notification policy. Create target,
member-price, price-drop, or vacancy-transition rules in **Push Settings**.
Quiet-hour events are persisted until the next allowed time, aggregation
combines nearby events, and daily digest mode sends one scheduled summary.
Critical rules can explicitly bypass quiet hours and digest mode. History
traces each rule to its event, batch, and per-channel outcome, while price
calendar badges show alert counts by hotel and stay date.
