# Phase 6 Data and Diagnostics Guide

Open **Interface Settings → Data & Backups** in either the WebUI or desktop
application.

## Export

1. Enable **Include price, alert, and run history** when history is needed.
2. Select **Export backup**.
3. Keep the downloaded ZIP intact. Its manifest and SHA-256 hashes are checked
   automatically during import.

Portable exports omit notification and mail credentials. Existing credentials
on the destination installation stay unchanged.

## Import

1. Select a backup ZIP.
2. Select **Preview import**.
3. Review the validated row and conflict counts.
4. Choose **Keep existing**, **Overwrite conflicts**, or **Replace data
   included in backup**.
5. Select **Apply import**.

A full rollback archive is written before data changes. Monitoring services are
stopped during the atomic database swap and reloaded afterwards. Pause an
active flexible-date search before importing.

## Upgrade backup and rollback

Desktop installation creates a full local backup after the update package and
signer are verified, but before application replacement begins. The current
rollback record is shown in storage status and stored as `rollback.json` in the
per-user configuration directory.

## Cleanup

Choose one category and retention period. **Preview cleanup** reports affected
items without committing database changes. **Run cleanup** removes only the
selected rebuildable or historical category. The latest backup is retained.

## Diagnostics

Use **Refresh diagnostics** to inspect database integrity, storage
writability, schema versions, platform details, packages, and recent redacted
logs. **Copy report** copies plain text. **Download support bundle** creates a
self-verifying ZIP after credential scanning.

Support bundles do not include raw settings, databases, proxy values, tokens,
passwords, cookies, or private notification identifiers.
