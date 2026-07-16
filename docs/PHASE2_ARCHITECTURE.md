# Phase 2 alert architecture

## Scope

Phase 2 adds a task-scoped rule engine and a process-wide notification
dispatcher. Notification destinations and credentials remain in the global
`AppConfig`; alert definitions and delivery policy are stored by task.

## Persistence

`alerting.py` maintains the following SQLite records:

- `price_alert_rules`: revisioned rule definitions and hotel/date scope.
- `notification_policies`: timezone, quiet window, aggregation, digest and
  critical behavior.
- `alert_observations`: last baseline per rule, hotel and stay date.
- `alert_events`: immutable trigger identity plus aggregated occurrence count.
- `alert_batches`: durable immediate, aggregate, quiet, digest or legacy batch.
- `alert_deliveries`: per-channel outcome with redacted detail.

The event fingerprint includes the rule, rule revision, hotel, stay date,
event type and transition counter. Reprocessing the same transition is
idempotent, while a later transition or semantic rule edit can create a new
event.

## Evaluation

The task scheduler invokes rule evaluation after a complete scan round.
Price-calendar daily observations use the same evaluator.

- Target and member-price rules trigger on a false-to-true threshold change.
- Price-drop rules require a previous observation; the first observation is
  baseline-only.
- Vacancy rules compare the previous known availability state; the first
  available observation is treated as an available transition.
- Cached data advances alert state only after conditional revalidation.
- Unknown/error observations preserve the last valid price and vacancy baseline.
- Rule cooldown aggregates repeated qualifying drops into the existing event.

## Scheduling

The event due time is computed in this order:

1. Critical override, when enabled by the task policy.
2. Daily digest time.
3. End of the active quiet window.
4. End of the aggregation window.

Time calculations use `zoneinfo.ZoneInfo`. Cross-midnight quiet windows and
daylight-saving timezone transitions are evaluated in the configured local
timezone and persisted as UTC timestamps. Windows installs and desktop bundles
include the IANA `tzdata` database.

## Delivery and recovery

One `AlertDispatcher` thread claims due batches. The runtime supplies a
task-aware `AppConfig` and maps delivery to the existing Telegram, email,
local, Bark and Server Chan adapters.

On startup, batches left in `sending` return to `queued`. Retry is limited to
failed/partial batches, and channels already recorded as sent or queued are
excluded from retry. Batch state is derived from every stored channel result,
so a successful retry changes a partial batch to sent without erasing earlier
channel history.

## Compatibility

Existing availability notifications keep their event controls and message
format. Their already-delivered events are mirrored into Phase 2 history as
`legacy` batches. For hotels and dates covered by an enabled
vacancy-transition rule, the older available/unavailable send switches are
suppressed to avoid a second message for the same transition. Uncovered hotels
keep the original notification behavior.

## API contract

- Rule collection and detail endpoints use optimistic `expected_revision`.
- Policy writes use an independent policy revision.
- Preview evaluates current results without changing baselines.
- History never returns notification credentials.
- Calendar badges are filtered by task, hotel and stay month.
