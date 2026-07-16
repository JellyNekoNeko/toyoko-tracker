# Changelog

## v0.7.0 - Development

- Completed Phase 3 flexible-date search with deterministic custom, weekend
  and next-30-day combinations, durable pause/resume jobs and shared Provider
  pacing.
- Added multi-night continuous-stay validation, regular/member total and
  average prices, isolated-night evidence, common-room selection and explicit
  room-change detection.
- Added multi-hotel comparison tables, deterministic five-level price heat
  maps, per-check-in and per-night cheapest-hotel markers, missing-price
  states and Provider capability notices.
- Added workspace schema v3, flexible-stay APIs, restart recovery, a
  five-language responsive comparison UI and the Phase 3 architecture/user
  guide.
- Completed Phase 2 price alerts with task-scoped target-price, member-price,
  price-drop and vacancy-transition rules, date/hotel scopes, revisions and
  persistent observation baselines.
- Added timezone-aware quiet hours, aggregation windows, daily digests,
  critical-rule override, Windows IANA timezone data and restart-safe
  notification batches.
- Added rule-to-event-to-batch-to-channel history, redacted delivery failures,
  failed-channel-only retry and legacy availability-event mirroring.
- Added the price-alert and notification-policy editor, alert history, alert
  APIs and date-aware badges in the price calendar.
- Completed Phase 1 multi-task monitoring with one process-wide scheduler,
  task-native CRUD/control/results/run APIs and selected-task compatibility for
  the original Start, Stop, Status and results routes.
- Connected the multilingual Monitor Tasks workspace to live persisted data,
  including create, copy, rename, reorder, edit/save conditions, pause/resume,
  delete, progress, next scan, results, errors, run history and global Provider
  pacing status.
- Routed recurring tasks, one-time scans and price-calendar requests through
  the installation-wide Provider gate, with shared cooldown handling and
  task-local cancellation.
- Added lifecycle recovery and shutdown draining so restart resumes durable
  active tasks through one coordinator without duplicating workers.
- Isolated notification checkpoints and in-memory results by task while
  retaining global notification destinations and credentials.
- Added the Phase 1 fair task coordinator with rotating ready queues, bounded
  hotel batches and priorities, target-start cadence and cancellable turns.
- Added isolated per-task runtime contexts for progress, results, errors,
  checkpoints, cancellation, run history and restart reconciliation.
- Added the scheduler kernel joining durable tasks, runtime contexts and the
  installation-wide Provider gate, including recurring and one-time rounds.
- Added workspace schema v2 with a separate `runtime_revision`, so background
  progress updates no longer create task-editor revision conflicts.
- Started Phase 1 multi-task monitoring with transactional task CRUD, copy,
  reorder, revision conflicts, desired/runtime state, run history and
  search-only `AppConfig` mapping.
- Added the installation-wide Provider pacer foundation for shared
  concurrency, per-Provider spacing, 429/503 cooldown and cancellable waits.
- Added a multilingual, responsive monitor-task center for managing persisted
  monitoring tasks.
- Added the frozen Phase 1 state, pacing, coordinator and legacy-route
  integration contract in `docs/PHASE1_ARCHITECTURE.md`.
- Phase 0 established the versioned 0.7.0 workspace schema for monitor tasks,
  task runs, price alerts, notification policies and travel lists, including a
  secret-free import of the existing search configuration as the default task.
- Added the staged 0.7.0 delivery and compatibility contract in
  `docs/ROADMAP_0.7.0.md`.
- Added phase-by-phase work-package ownership, dependency waves and acceptance
  gates in `docs/TASK_ALLOCATION_0.7.0.md`.
- Added an on-demand price calendar for every selected hotel, including daily
  availability, regular/member prices, monthly summaries, persistent cache,
  paced background refresh, and direct official-booking links.
- Added PyPI Trusted Publishing through a dedicated OIDC release workflow.
- Added pipx installation detection and pipx-aware in-app upgrades.
- Added automatic frozen-desktop downloads with SHA-256 verification, safe
  extraction, native signer continuity checks, staged replacement, restart,
  and rollback copies.
- Added optional macOS Developer ID signing/notarization and Windows
  Authenticode signing to the multi-architecture desktop workflow.
- Added GitHub Sigstore build-provenance attestations for desktop archives.

## v0.6.0 - 2026-07-15

- Added area and radius-based hotel selection with map visualization.
- Added multilingual primary-language and English UI, hotel, room, and notification content.
- Added HTTP/API scanning with Playwright fallback and smart parallel scanning.
- Added search history, availability logs, notification event controls, and additional push channels.
- Refactored the original monolithic application into focused runtime, parsing, notification, rendering, model, and settings modules.
