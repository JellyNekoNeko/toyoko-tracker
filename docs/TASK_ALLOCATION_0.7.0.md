# Toyoko Tracker 0.7.0 task allocation

This document turns `ROADMAP_0.7.0.md` into assignable work packages. The
version remains `0.7.0 Development` until every phase gate passes. Intermediate
work is committed and tested without creating tags, Releases, desktop uploads,
or PyPI publications.

## Work lanes

The lane names describe code ownership rather than permanent people. They can
be assigned to Codex agents or maintainers one phase at a time.

| Lane | Primary ownership |
| --- | --- |
| **A — Data & API** | SQLite migrations, repositories, DTOs, CRUD APIs, import/export |
| **B — Runtime & Algorithms** | Scheduler, provider pacing, rules, date/stay algorithms, recovery |
| **C — WebUI & i18n** | HTML/CSS/JS, interaction state, accessibility, Chinese/English/Japanese/Korean text |
| **D — QA, Desktop & Release** | fixtures, regression, desktop platforms, CI, documentation and release gates |

## Operating rules

1. A phase is delivered only after its acceptance gate passes.
2. Database migrations are transactional, forward-only and idempotent.
3. `runtime.py` and `app.py` have one integration owner per wave to reduce
   merge conflicts.
4. `static/app.js`, `static/app.css` and embedded runtime HTML are integrated
   by Lane C after the API contract is frozen.
5. Provider pacing is installation-wide. No feature may create a private
   request loop that bypasses it.
6. Tests use provider fixtures and injectable clocks rather than live hotel
   websites or real sleeps.
7. Notification credentials remain global installation settings and are
   excluded from tasks, travel lists, reports and default exports.
8. Phase completion commits may be pushed to `main`; publishing actions wait
   for the final Phase 6 decision.

## Phase 0 — persistence and compatibility foundation

Status: **Delivered** in commit `592e103`.

| ID | Owner | Work package | Output | Status |
| --- | --- | --- | --- | --- |
| P0-01 | A | Versioned workspace schema | Tasks, runs, alerts, policies and travel-list tables | Done |
| P0-02 | A | Legacy default-task import | Existing search config imported without notification secrets | Done |
| P0-03 | A/B | Compatibility contracts | Legacy config, routes, global pacing and migration rules frozen | Done |
| P0-04 | D | Migration tests | Idempotency, table preservation and secret-exclusion coverage | Done |
| P0-05 | D | Staged roadmap | `docs/ROADMAP_0.7.0.md` | Done |

## Phase 1 — multiple monitor tasks

### Assigned work

| ID | Owner | Work package | Depends on | Required output |
| --- | --- | --- | --- | --- |
| P1-01 | A | Task repository and transactions | Phase 0 | CRUD, copy, reorder, revision conflicts, desired/runtime state and run records |
| P1-02 | A | Task/AppConfig mapping | P1-01 | Search-only serializer, validation and default-field upgrades |
| P1-03 | B | Installation-wide Provider pacer | Phase 0 | Shared concurrency, minimum interval, cooldown, cancellation and adaptive backoff |
| P1-04 | B | Fair task coordinator | P1-01/02/03 | Ready queue, fair turns, cadence calculation and bounded priority |
| P1-05 | B | Per-task runtime context | P1-04 | Progress, results, errors, checkpoints, cancellation and restart recovery |
| P1-06 | A | Task APIs | P1-01/02/05 | Task CRUD, start/pause, reorder, runs, results and status endpoints |
| P1-07 | A/B | Legacy route adapter | P1-05/06 | `/start`, `/stop`, `/status` and results projected to selected/default task |
| P1-08 | C | Task list and editor | P1-06 contract | Create, duplicate, rename, reorder, pause, delete and edit task conditions |
| P1-09 | C | Task runtime dashboard | P1-05/06 | Per-task progress, results, next run, history and global cooldown display |
| P1-10 | D | Scheduler and compatibility regression | P1-03–09 | Virtual-clock fairness, cooldown, recovery, concurrent CRUD and legacy API tests |
| P1-11 | D | Phase documentation | P1-07/08 | State model, pacing behavior, API compatibility and user guide |

### Execution waves

- **Wave 1, parallel**
  - Lane A: P1-01, then P1-02.
  - Lane B: P1-03.
  - Lane C: P1-08 mock and interaction prototype against the frozen DTO draft.
  - Lane D: P1-10 virtual clock, provider fixtures and legacy-contract tests.
- **Wave 2**
  - Lane B: P1-04, then P1-05.
  - Lane A: P1-06.
  - Lane C: connect P1-08 to the real API.
- **Wave 3**
  - Lane A/B: P1-07.
  - Lane C: P1-09.
  - Lane D: P1-10 final regression and P1-11.

### Phase gate

- Three active tasks receive fair scan opportunities.
- A large task does not starve smaller tasks.
- Pausing one task leaves the others active.
- A Provider 429/503 cooldown affects every task and price-calendar request.
- Restart restores desired task states with one coordinator.
- Legacy start/stop/status/results contracts continue to pass.

## Phase 2 — price alerts and notification policy

| ID | Owner | Work package | Depends on | Required output |
| --- | --- | --- | --- | --- |
| P2-01 | A | Alert and policy repository | Phase 1 | CRUD, revisions, rule/event links and persistent notification queue schema |
| P2-02 | B | Rule evaluation engine | P2-01/P1-05 | Target price, member price, price drop and vacancy-transition evaluation |
| P2-03 | B | Aggregation, quiet hours and digest scheduler | P2-01/02 | UTC due times, quiet windows, aggregation batches, digest and critical override |
| P2-04 | B | Delivery adapters and traceability | P2-03 | Rule → event → batch → channel delivery chain with redacted failures |
| P2-05 | A/B | Legacy notification compatibility | P2-02/04 | Existing availability notifications mapped into the unified pipeline |
| P2-06 | A | Alert, policy and history APIs | P2-01–05 | CRUD, preview, filters, calendar badge summary and redacted history |
| P2-07 | C | Rule and notification-policy UI | P2-06 | Rule editor, scope, thresholds, quiet hours, aggregation and digest settings |
| P2-08 | C | Notification history and calendar badges | P2-06 | Per-channel outcomes and date/task/hotel-aware alert badges |
| P2-09 | D | Time, aggregation and idempotency regression | P2-02–08 | DST, cross-midnight, restart, duplicate observation and partial-channel tests |
| P2-10 | D | Phase documentation | P2-07/08 | Rule examples and exact immediate/queued/digest behavior |

### Parallel order

- Lane A: P2-01 → P2-06.
- Lane B: P2-02 → P2-03 → P2-04 → P2-05.
- Lane C: P2-07 and P2-08 after the API draft; mocks may start earlier.
- Lane D: P2-09 fixtures begin with P2-02; P2-10 follows UI wording freeze.

### Phase gate

- First observations establish baselines without false price-drop alerts.
- Quiet-hour and digest jobs survive restart without duplicate delivery.
- Every delivery is traceable to its task, rule and observation.
- Existing notification settings do not send a second duplicate message.
- Stored history and errors contain no credentials.

## Phase 3 — flexible dates, multi-night stays and comparison

| ID | Owner | Work package | Depends on | Required output |
| --- | --- | --- | --- | --- |
| P3-00 | A/B | Domain and Provider capability contract | Phase 1 | Flexible-search DTOs, status enums, currency/tax/evidence semantics and schema v2 |
| P3-01 | B | Date combination engine | P3-00 | Date window, stay length, weekend and next-30-days deterministic combinations |
| P3-02 | A | Quote repository and resumable jobs | P3-00 | Jobs, candidates, quotes, progress, evidence and cleanup policy |
| P3-03 | B | Flexible-search scheduler | P3-01/02/P1 pacer | Pause, resume, cancel, batching and shared Provider pacing |
| P3-04 | B | Continuous-stay evaluator | P3-01/02 | Full-stay status, nightly evidence, total/average price and room changes |
| P3-05 | A/B | Hotel comparison and heat-map aggregation | P3-02/04 | Comparable quote sets, cheapest hotel, filters and deterministic heat levels |
| P3-06 | A | Flexible-search APIs and runtime integration | P3-03/04/05 | Job control, candidates, evidence, comparison matrix and saved views |
| P3-07 | C | Flexible-date and comparison UI | P3-00/06 | Inputs, shortcuts, progress, heat map, comparison table and capability notices |
| P3-08 | D | Phase regression and performance | P3-01–07 | Date edge cases, restart, fixture matrix, large-window and browser tests |

### Execution waves

1. P3-00 is the serial architecture gate.
2. P3-01, P3-02, the P3-07 prototype and P3-08 fixture design run in parallel.
3. P3-03 starts after the date engine and repository.
4. P3-04 and P3-05 run in parallel.
5. P3-06 performs the single-owner runtime integration.
6. P3-07 connects the final APIs; P3-08 closes the phase.

### Phase gate

- Date combinations are unique, bounded and reproducible.
- Long jobs pause, resume and recover without bypassing global pacing.
- Multi-night conclusions show whether evidence is Provider-verified or a
  nightly composite.
- Currency, tax basis, missing prices and Provider limitations are visible.
- Large comparison matrices remain usable on desktop and narrow screens.

## Phase 4 — decision intelligence and travel lists

| ID | Owner | Work package | Depends on | Required output |
| --- | --- | --- | --- | --- |
| P4-00 | A | Historical-data contract | Phase 3 | Source, dedupe, sample window, anomaly and percentile rules |
| P4-01 | A | Historical statistics repository | P4-00 | Min/average/max/median/percentiles and current-price position |
| P4-02 | B | Price assessment rules | P4-01 | Low/normal/high labels with sample count, window and explanation |
| P4-03 | B | Split-stay optimizer | P3-04/05 | Reproducible ranking by moves, distance and total price with nightly evidence |
| P4-04 | A | Travel-list repository and schema v3 | Stable Phase 1–3 IDs | Lists, hotel items, priorities, notes, budget and association tables |
| P4-05 | A | Travel-list APIs and associations | P4-04 | Link/unlink tasks, rules and saved comparison views |
| P4-06 | C | Decision center and travel-list UI | P4-02/03/05 | Overview, hotels, prices, split plans, evidence and ranking details |
| P4-07 | A/C | Readable trip-summary export | P4-02/03/05 | Versioned JSON plus Markdown/HTML without credentials |
| P4-08 | D | Reproducibility and data-integrity tests | P4-01–07 | Golden statistics, split paths, migrations, associations and export scanning |

### Parallel order

- P4-00/01 and P4-04 may start in parallel.
- P4-02 follows statistics; P4-03 follows the Phase 3 evidence model.
- P4-05 follows travel-list storage and stable resource IDs.
- P4-06 integrates after P4-02/03/05; P4-07 may run beside it.
- P4-08 designs fixtures early and owns the final gate.

### Phase gate

- Every price assessment exposes sample count, time window and method.
- Split-stay suggestions have evidence for every night and reproducible scores.
- Travel-list deletion preserves linked task/rule records as defined.
- Exported summaries pass the sensitive-field scan.

## Phase 5 — native desktop lifecycle

| ID | Owner | Work package | Platform | Depends on |
| --- | --- | --- | --- | --- |
| P5-01 | A/D | Lifecycle core and adapter protocol | All | Phase 1 |
| P5-02 | D-mac | Menu-bar and window lifecycle | macOS arm64/x64 | P5-01 |
| P5-03 | D-win | Tray and window lifecycle | Windows x64/ARM64 | P5-01 |
| P5-04 | D-linux | GTK/AppIndicator and fallback | Linux x86_64/ARM64 | P5-01 |
| P5-05 | D | Launch-at-login adapters | All | P5-01/02/03/04 |
| P5-06 | B | Sleep, wake and network recovery | All | Phase 1/P5-01 |
| P5-07 | B/C/D | Notification deep links | All | Phase 1–4/P5-01 |
| P5-08 | C/D | Badge and unread count | All, capability-based | Phase 2/P5-02–04 |
| P5-09 | C | Desktop settings and i18n | All | P5-01/05/08 |
| P5-10 | D | Six-target desktop acceptance | Six build targets | P5-01–09 |

### Platform waves

- P5-01 and P5-06 are the core line.
- macOS, Windows and Linux adapters are separate work packages and may run in
  parallel when platform runners or machines are available.
- P5-05, P5-07 and P5-08 integrate after the platform adapters.
- P5-09 freezes user-facing behavior; P5-10 closes the phase.

### Phase gate

- Closing, hiding and quitting have consistent, documented semantics.
- Repeated wake/network events still leave one scheduler and local server.
- macOS arm64/x64, Windows x64/ARM64 and Linux x86_64/ARM64 all start and exit.
- Missing tray/badge/deep-link capability falls back to WebUI controls.

## Phase 6 — data tools, diagnostics and release closure

| ID | Owner | Work package | Platform | Depends on |
| --- | --- | --- | --- | --- |
| P6-01 | A | Consistent backup archive | All | Final Phase 0–4 schema |
| P6-02 | A | Import preview and conflict strategy | All | P6-01 |
| P6-03 | A/D | Pre-upgrade backup and rollback metadata | All desktop targets | P6-01/updater |
| P6-04 | A/C | Data and storage management UI | WebUI/Desktop | P6-01–03 |
| P6-05 | A/B | Diagnostic and redaction engine | All | Phase 1/P5 |
| P6-06 | C/D | Diagnostic center and support bundle | WebUI/Desktop | P6-05 |
| P6-07 | D | WebUI cross-platform regression | macOS/Windows/Linux | Phase 1–6 |
| P6-08A | D-mac | Desktop release regression | macOS arm64/x64 | Phase 5/P6-03/06 |
| P6-08B | D-win | Desktop release regression | Windows x64/ARM64 | Phase 5/P6-03/06 |
| P6-08C | D-linux | Desktop release regression | Linux x86_64/ARM64 | Phase 5/P6-03/06 |
| P6-09 | D | CI gates and artifact verification | All | P6-07/08 |
| P6-10 | C/D | Four-language documentation | All | UI and platform behavior freeze |
| P6-11 | D/Product | Release-candidate acceptance | All | P6-01–10 |

### Release order

1. P6-01 → P6-02 and P6-03 → P6-04.
2. P6-05 → P6-06 runs in parallel with the data line.
3. P6-07 and P6-08A/B/C run as separate platform gates.
4. P6-09 verifies six assets, versions, architectures, hashes, attestations and
   signature results.
5. P6-10 freezes documentation.
6. P6-11 produces the RC report and publication decision.

### Phase gate

- Backups use a manifest, format version and SHA-256 hashes.
- Import preview is read-only and failed imports roll back transactionally.
- Diagnostic and support bundles pass credential and private-token scans.
- WebUI tests and all six desktop smoke/signature checks pass.
- RC work does not create formal tags; publishing begins only after explicit
  final approval.

## Current assignment

Phase 1 is the active phase. The first work wave is assigned as follows:

| Lane | Active assignment | Completion signal |
| --- | --- | --- |
| A | P1-01 task repository, followed by P1-02 mapping | Transactional CRUD and config round-trip tests pass |
| B | P1-03 installation-wide Provider pacer | Three simulated tasks share concurrency and cooldown |
| C | P1-08 task-center mock/prototype | Task switching, ordering and local mutations pass UI contract checks |
| D | P1-10 test harness and P1-11 document skeleton | Virtual clock, provider fixtures and legacy contract suite ready |

P1-04 begins only after P1-01/02/03 interfaces are reviewed together.

The frozen Phase 1 integration contracts are documented in
`docs/PHASE1_ARCHITECTURE.md`.

### Wave 1 implementation status

| Work package | Status | Evidence |
| --- | --- | --- |
| P1-01 | Implemented | CRUD, copy, delete cascade, reorder and revision-conflict tests |
| P1-02 | Implemented | Search-only round trip, validation and secret-exclusion tests |
| P1-03 | Implemented | Virtual-clock pacing, cooldown, cancellation and real-thread capacity tests |
| P1-08 | Prototype implemented | Five-language responsive task-center UI and stale-selection guards |
| P1-10 | In progress | Wave 1 contracts are covered; coordinator, API and recovery cases follow their implementations |
| P1-11 | In progress | State, pacing, API direction and legacy projection are frozen |

The next implementation wave starts with P1-04 and P1-05, then connects P1-06
and the task-center prototype to persisted task records.
