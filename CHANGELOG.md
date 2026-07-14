# Changelog

## v0.7.0 - Development

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
