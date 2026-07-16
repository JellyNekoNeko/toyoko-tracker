# Changelog

## v0.7.0 - Development

- Started Phase 1 multi-task monitoring with transactional task CRUD, copy,
  reorder, revision conflicts, desired/runtime state, run history and
  search-only `AppConfig` mapping.
- Added the installation-wide Provider pacer foundation for shared
  concurrency, per-Provider spacing, 429/503 cooldown and cancellable waits.
- Added a multilingual, responsive monitor-task center prototype for creating,
  copying, renaming, reordering, pausing and deleting local preview tasks.
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
