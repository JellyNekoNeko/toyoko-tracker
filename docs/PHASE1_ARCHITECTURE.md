# Phase 1 architecture — multi-task monitoring

This document freezes the integration contracts for Phase 1 of Toyoko Tracker
0.7.0. It complements `TASK_ALLOCATION_0.7.0.md` and is intentionally narrower:
it defines the task state model, installation-wide pacing boundary, coordinator
behavior and compatibility projection used while the old single-task WebUI
continues to operate.

## Ownership boundaries

### Workspace repository

The repository owns durable task definitions and run history:

- task identity, display name and sort order;
- search configuration and optimistic revision;
- desired state selected by the user;
- last known runtime state, next run, error and result summary;
- durable run history with immutable terminal records.

The repository does not own notification credentials, live worker objects,
threading events or Provider HTTP clients.

Task definitions and runtime observations use separate counters:

- `revision` changes only when the user-facing task definition or desired state
  changes;
- `runtime_revision` changes for progress state, next-run time, result summary
  and runtime errors.

This prevents a background scan from invalidating an editor that is saving a
definition revision observed before the scan progressed.

### Runtime coordinator

One coordinator exists per application process. It owns:

- in-memory runtime contexts for every active task;
- the ready queue and fairness policy;
- one cancellation token per task;
- restart reconciliation between desired and runtime state;
- the compatibility projection for the selected/default task.

Starting another task never creates another coordinator.

### Provider pacer

One Provider pacer exists per application process and is shared by:

- continuous monitoring tasks;
- one-time scans;
- enhanced availability confirmation;
- price-calendar refreshes;
- flexible-date jobs introduced in Phase 3.

The pacer is the final boundary before a Provider request starts. Feature-level
delays may request a slower pace, but they do not replace or bypass this gate.

## Task configuration

Task JSON stores search behavior only:

- dates and selected hotels;
- guests, rooms, smoking and room requirement;
- membership status and preferred language;
- enabled hotel Providers and area/radius metadata;
- scan cadence, jitter, engine, parallel and adaptive-backoff preferences;
- optional task-level budget filters.

Installation-level notification destinations and credentials remain in
`auto_save.json`. Task serialization excludes Telegram, Bark, Server Chan,
SMTP and other credentials.

`room_requirement` is the public field name. The historical
`om_requirement` attribute is accepted during migration and converted at the
repository boundary.

## State model

### Desired state

| Value | Meaning |
| --- | --- |
| `paused` | The user does not want scheduled scans for this task. |
| `active` | The coordinator should schedule recurring scans. |

### Runtime state

| Value | Meaning |
| --- | --- |
| `idle` | No run is active or queued. |
| `queued` | The task has work waiting for a coordinator turn. |
| `scanning` | At least one hotel request is active for the current run. |
| `waiting` | The latest run completed and the next cadence is pending. |
| `pausing` | Cancellation was requested and in-flight work is draining. |
| `error` | The latest run ended with a task-level failure. |

Runtime state is observational. On startup, the coordinator reconciles it from
durable desired state and run records instead of trusting an old `scanning`
value.

### Run state

| Value | Terminal |
| --- | --- |
| `queued` | No |
| `running` | No |
| `complete` | Yes |
| `partial` | Yes |
| `cancelled` | Yes |
| `interrupted` | Yes |
| `failed` | Yes |

Startup marks orphaned `queued` or `running` records as `interrupted` before
new work is scheduled.

## Production implementation

The Phase 1 scheduling core is split into three layers:

- `TaskCoordinator` owns monotonic readiness, rotation, bounded turns and
  cadence calculation;
- `TaskRuntimeRegistry` owns one isolated context per durable task and performs
  orphaned-run recovery;
- `TaskSchedulerKernel` joins storage, contexts, the coordinator and the shared
  Provider pacer through an injected single-hotel scan callback;
- `TaskSchedulerService` owns the single process-wide scheduler thread,
  serializes task mutations and controls startup/shutdown draining;
- `runtime.py` supplies the production Provider adapter, notification and
  analytics completion hooks, legacy route projection and application
  lifecycle integration.

Durable `next_run_at` values are wall-clock timestamps. The kernel converts
them to monotonic deadlines while scheduling and converts the next deadline
back before persistence.

Application bootstrap starts the task service after workspace migration and
default-task import. The historical worker loop remains only as compatibility
code and is no longer created by `/start`; all recurring and one-time task work
uses the same coordinator.

Shutdown signals issued turns, waits for the coordinator to drain and preserves
the durable `active` intent so the next application start can reconcile and
resume the task. A second start call reuses the existing coordinator thread.

## Fair scheduling contract

1. Ready tasks are ordered by `next_run_at`.
2. Tasks with equal readiness rotate rather than retaining insertion priority.
3. A coordinator turn contains one hotel request or a small bounded batch. A
   complete large task round is not an indivisible queue item.
4. Manual/adaptive hotel priority may reorder work inside a task, but a task
   receives only a bounded number of consecutive priority turns.
5. The next recurring run is based on the previous run's target cadence. A slow
   run does not trigger an immediate series of catch-up scans.
6. Pausing a task removes future work immediately; an already-started request
   may finish and is recorded before the task reaches `idle`.

## Provider pacing contract

The pacer enforces:

- installation-wide total concurrency;
- per-Provider concurrency;
- per-Provider minimum start interval;
- shared cooldown after HTTP 429/503 or explicit Retry-After;
- cancellable waits that acquire no capacity when cancelled;
- a snapshot suitable for diagnostics and UI display.

Playwright-backed requests use an effective global concurrency of one unless a
future Provider adapter explicitly proves independent browser contexts safe.

## Task API

Phase 1 adds these task-native endpoints:

| Method | Path | Purpose |
| --- | --- | --- |
| `GET`, `POST` | `/api/v1/tasks` | List tasks or create/copy a task |
| `GET` | `/api/v1/tasks/summary` | Poll all task states and global pacing |
| `POST` | `/api/v1/tasks/reorder` | Persist the full task order |
| `GET`, `PATCH`, `DELETE` | `/api/v1/tasks/<task_id>` | Read, edit or delete one task |
| `POST` | `/api/v1/tasks/<task_id>/copy` | Duplicate a task |
| `POST` | `/api/v1/tasks/<task_id>/start` | Start recurring work or one run |
| `POST` | `/api/v1/tasks/<task_id>/pause` | Pause one task |
| `GET` | `/api/v1/tasks/<task_id>/status` | Read runtime state and pacing |
| `GET` | `/api/v1/tasks/<task_id>/results` | Read revisioned task results |
| `GET` | `/api/v1/tasks/<task_id>/runs` | Read durable run history |

Every task-specific request carries a `task_id`; browser selection is client
state, not a mutable server-global "current task".

Definition updates, reorder, start, pause and deletion may include the last
observed revision. A stale revision returns HTTP 409 with the current public
task record when that record still exists.

## WebUI contract

The Monitor Tasks workspace is backed by the task API and includes:

- create, duplicate, rename, reorder, pause/resume and delete actions;
- an Edit Conditions action that loads the selected task into Vacancy Search;
- a Save Task action that persists edited conditions without starting a scan;
- selected-task progress, result count, next scan, last error and run history;
- installation-wide active/waiting request counts and Provider cooldown state;
- two-second background polling with request-token and revision guards.

Selecting a task also changes the top command controls, Vacancy Search form,
Vacancy Monitor status/results and Price Calendar draft scope. Browser storage
remembers the selected task, while a deleted or unknown selection falls back to
the default task.

## Legacy endpoint compatibility

Until the task UI fully replaces the single-session workflow:

- `/start` without `task_id` updates and starts the default task;
- `/start` with `task_id` starts only that task;
- `run_once` schedules one run for the selected/default task;
- `/stop` pauses the selected/default task rather than stopping all tasks;
- `/status` and existing result endpoints project the selected/default task;
- responses keep the historical `ok`, `message`, `restarted`, `run_once` and
  `config` fields and add `task_id`;
- global shutdown remains an application lifecycle action, not the legacy
  `/stop` behavior.

## Test contract

Phase 1 acceptance uses deterministic tests with injected clocks and Provider
fixtures:

- three-task fairness with different hotel counts and cadences;
- shared concurrency and cooldown across task, calendar and one-time work;
- cancellation while waiting and while a request is active;
- restart reconciliation and orphaned-run cleanup;
- optimistic update conflicts and concurrent reorder operations;
- no cross-task result, progress or notification checkpoint leakage;
- unchanged legacy route response fields.

Phase 1 completion is covered by repository, runtime-context, coordinator,
service-lifecycle, task-API, legacy-route, notification-isolation, shared
price-calendar pacing and static WebUI contract tests.
