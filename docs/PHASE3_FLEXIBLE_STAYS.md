# Phase 3：灵活日期、连住验证与价格比较

## 1. 在 WebUI 中使用

进入 **价格日历 → 多酒店价格比较**。

1. 选择最早入住日和最晚退房日。
2. 设置连住晚数（1–14 晚）。
3. 可使用 **周末** 或 **未来 30 天** 快捷方式。
4. 点击 **开始比较**。

系统会按稳定顺序生成所有入住/退房组合，去除重复组合，并把同一日期的逐晚
查询复用于多个连住组合。

## 2. 连住结论

比较表会明确区分：

- **可连住**：每一晚都有可用证据。
- **不可连住**：至少一晚明确满房。
- **待确认**：Provider 返回未知状态。
- **证据不完整**：任务尚未取得全部夜晚数据。

完整连住结论基于逐晚 Provider 观测合成，并不冒充 Provider 原生的整段入住
确认。表格同时显示：

- 普通总价与会员总价；
- 每晚平均价；
- 独立有房晚数；
- 同房型连续入住；
- 需要中途换房。

当每一晚存在同一标准化房型时，系统选择总价最低的共同房型。若各晚均有房，
但没有贯穿全程的共同房型，则使用逐晚最低价计算参考总价，并标记为需要换房。

## 3. 多酒店比较与热力图

行表示酒店，列表示入住日期组合。

- 绿色到红色表示同一日期组合中从低到高的五级价格热度。
- `★` 表示该入住日的最低总价酒店；并列最低会同时标记。
- 会员状态为会员时，优先使用完整的会员总价。
- 缺价、未知、满房和未完成组合保持独立状态，不参与最低价排名。

页面底部说明逐晚证据、房型变化、币种和 Provider 显示税费口径。当前价格以
Provider 返回的 JPY 显示值为准。

## 4. 暂停、继续与重启

灵活日期任务保存到 SQLite：

- `flexible_stay_jobs`：日期窗口、酒店、条件和进度；
- `flexible_stay_nights`：每家酒店、每个夜晚的原始证据；
- `flexible_stay_results`：连住组合、总价和房型连续性。

点击 **暂停** 后，当前请求结束时停止后续查询。点击 **继续** 只补查尚未完成
或状态未知的夜晚。应用重启会把未完成任务恢复为可继续状态，不重复查询已经
得到明确有房或满房结论的夜晚。

已完成、部分完成、取消或失败的任务保留 180 天，并在创建新任务时清理更早
记录；排队、运行和暂停中的任务不参与清理。

所有请求经过与监控任务、单次检索和价格日历共用的 Provider pacing gate，
因此全局并发、最小间隔和 429/503 冷却仍然生效。

## 5. API

```text
GET    /api/v1/flexible-stays?task_id=TASK_ID
POST   /api/v1/flexible-stays
GET    /api/v1/flexible-stays/JOB_ID
DELETE /api/v1/flexible-stays/JOB_ID
POST   /api/v1/flexible-stays/JOB_ID/pause
POST   /api/v1/flexible-stays/JOB_ID/resume
POST   /api/v1/flexible-stays/JOB_ID/cancel
```

创建请求示例：

```json
{
  "task_id": "default",
  "earliest_date": "2026-08-01",
  "latest_date": "2026-08-31",
  "nights": 3,
  "shortcut": "custom",
  "hotel_codes": ["00001", "00002"],
  "selected_hotels": [
    {"code": "00001", "provider": "toyoko", "name_primary": "Hotel A"},
    {"code": "00002", "provider": "toyoko", "name_primary": "Hotel B"}
  ]
}
```

任务详情同时返回 `columns`、`rows`、`daily_minima`、`nightly_minima`、
汇总信息和 Provider 能力限制。
