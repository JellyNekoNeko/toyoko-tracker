# Toyoko Tracker 0.7.0 staged delivery plan

0.7.0 remains a development version until every phase below passes its
acceptance gate. Intermediate phases are delivered as ordinary commits. They do
not create a Git tag, GitHub Release, desktop upload, or PyPI publication.

## Product direction

0.7.0 upgrades Toyoko Tracker from one vacancy-search session into a
multi-trip accommodation decision workspace. Existing WebUI, pipx, PyPI and
desktop users retain their current configuration and can migrate without
re-entering hotels or notification credentials.

## Phase 0 — persistence and compatibility foundation

Deliverables:

- Versioned workspace schema in the existing SQLite database.
- Tables reserved for monitor tasks, task runs, price-alert rules,
  notification policies, travel lists and hotels in those lists.
- Safe import of the current search configuration into a default task.
- Notification credentials remain global and are excluded from task JSON.
- Architecture and compatibility contracts are frozen before scheduler work.

Acceptance gate:

- Repeated startup migrations are idempotent.
- Existing hotel, event, analytics and price-calendar tables remain intact.
- A legacy single-search installation receives exactly one default task.
- No notification secret appears in the task table.

## Phase 1 — multiple monitor tasks

Status: **Delivered**. The task repository, fair scheduler, single lifecycle
service, task-native API, selected-task compatibility projection and live
WebUI task center are implemented.

Deliverables:

- Task list and task editor in the WebUI.
- Create, duplicate, rename, reorder, pause and delete actions.
- Independent dates, hotels, guests, room preferences and scan cadence.
- Cooperative scheduler with one global provider pacing layer.
- Per-task progress, results, last error, next scan and run history.
- Compatibility endpoints keep the original Start and Stop controls working
  against the currently selected task.

Acceptance gate:

- At least three tasks can remain active and receive fair scan turns.
- Pausing one task does not interrupt other tasks.
- Restart restores desired task states without duplicating workers.
- Global provider cooldown and concurrency limits apply across every task.

## Phase 2 — price alerts and notification policy

Status: **Delivered**. Task-scoped price rules, durable observations and
notification batches, quiet-hour scheduling, aggregation, daily digests,
critical override, per-channel history, retry behavior and price-calendar
badges are implemented. Phase 3 is the next development stage.

Deliverables:

- Target price, member price, price-drop and vacancy-transition rules.
- Rules for one date, a date interval, one hotel or all task hotels.
- Quiet hours, aggregation windows, daily digest and critical-rule override.
- Notification history with channel status and redacted failure details.
- Alert badges in the price calendar.

Acceptance gate:

- Identical events are aggregated inside the configured time window.
- Quiet-hour events are queued for the next permitted delivery time.
- Critical alerts follow the explicit task policy.
- Each delivery is traceable from rule to event to channel outcome.

## Phase 3 — flexible dates, multi-night stays and comparison

Deliverables:

- Earliest/latest date window with requested stay length.
- Weekend and next-30-days shortcuts.
- Continuous-stay validation and total/average price calculation.
- Detection of room-type changes across nights.
- Single-hotel calendar and multi-hotel comparison views.
- Heat-map results and daily cheapest-hotel highlights.

Acceptance gate:

- Date combinations are generated deterministically and deduplicated.
- Full-stay availability differs clearly from isolated nightly availability.
- Comparisons state missing-price and provider-capability limitations.
- Long searches remain paced and resumable.

## Phase 4 — decision intelligence and travel lists

Deliverables:

- Historical minimum, average, maximum and percentile.
- Rule-based labels for low, normal and high current prices.
- Split-stay suggestions optimized by moves, distance and total price.
- Named travel lists with notes, budget and hotel priorities.
- Link tasks, alert rules and comparison views to a travel list.
- Exportable trip summary.

Acceptance gate:

- Price assessments expose sample count and observation window.
- Split stays never claim continuous availability without nightly evidence.
- Ranking weights are visible and reproducible.
- Travel lists survive upgrades and can be exported independently.

## Phase 5 — native desktop lifecycle

Deliverables:

- System tray/menu-bar status and task controls.
- Optional close-to-background behavior.
- Optional launch at sign-in.
- Sleep/wake and network-recovery handling.
- Notification deep links to the relevant task, hotel and date.
- Desktop badge/count where the operating system supports it.

Acceptance gate:

- Windows, macOS and Linux quit semantics are explicit and consistent.
- Background mode shows a persistent tray/menu-bar affordance.
- Wake and reconnection do not create duplicate scheduler processes.
- Unsupported platform integrations degrade to the WebUI controls.

## Phase 6 — data tools, diagnostics and release closure

Deliverables:

- Export/import for settings, tasks, rules, lists and selected history.
- Automatic pre-upgrade database backup and rollback metadata.
- Storage location, schema version, database size and cleanup controls.
- Copyable redacted diagnostic report.
- Cross-platform regression matrix for WebUI and every desktop architecture.
- Updated Chinese, English, Japanese and Korean documentation.

Acceptance gate:

- Backup archives contain a manifest and integrity hashes.
- Import provides a preview and conflict strategy.
- Diagnostic reports redact credentials and private tokens.
- Full tests, package checks and desktop smoke tests pass before publishing.

## Compatibility contracts

1. The existing `auto_save.json` remains readable throughout 0.7.0.
2. The original `/start`, `/stop`, `/status` and results endpoints remain
   available until the task UI fully replaces the single-session workflow.
3. Notification credentials are global installation settings; task records
   store only search and alert preferences.
4. Provider rate limits are installation-wide rather than task-local.
5. Database migrations are forward-only, transactional and idempotent.
6. No intermediate phase changes the public version beyond `0.7.0`.

## Delivery order

Each phase is committed and tested separately. A later phase may add migrations,
but it must preserve data created by earlier 0.7.0 development builds.

The assignable work-package IDs, owners, dependency waves and current active
assignments are maintained in `docs/TASK_ALLOCATION_0.7.0.md`.
