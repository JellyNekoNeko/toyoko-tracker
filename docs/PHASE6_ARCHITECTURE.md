# Phase 6 Data, Diagnostics, and Release-Closure Architecture

Phase 6 closes the 0.7.0 development plan without changing the public version
or publishing a release. WebUI and desktop builds use the same persistent
files, archive format, diagnostic engine, and acceptance contracts.

## Backup archive contract

Portable backups are ZIP files with:

- `manifest.json`
- `data/database.sqlite3`
- zero or more JSON files below `data/files/`

The manifest records format version `1`, application and workspace schema
versions, component selection, exported tables, row counts, archive purpose,
credential policy, and a SHA-256 digest plus byte size for every payload.
SQLite is copied with the backup API, checked with `PRAGMA integrity_check`,
and pruned only in the detached snapshot.

Portable exports include user-owned settings, tasks, alert rules, travel
lists, and flexible-date jobs. Price, alert, event, and task-run history is
optional. Provider catalog and scan cache rows are rebuildable and therefore
excluded. Credential fields are omitted; a boolean configured-state map is
kept so an import never erases an existing local credential accidentally.

Full local backups are used before imports and desktop upgrades. They retain
the raw persistent JSON files because they are rollback artifacts stored in
the application's per-user data directory rather than shareable exports.

## Import transaction

Import is a two-step operation:

1. **Preview** validates member paths, size limits, manifest version, every
   SHA-256 digest, SQLite integrity, row counts, and primary-key conflicts. It
   opens the current database read-only from the product perspective and does
   not change user records.
2. **Apply** first creates a full rollback archive. It merges into a staged
   copy of the current database with foreign keys temporarily deferred, runs
   integrity and relationship checks, then atomically swaps the staged file.
   JSON settings are written atomically. Any failure before or during the swap
   leaves or restores the original database and files.

Conflict strategies are:

- `keep_existing`: import only records whose primary keys are absent.
- `overwrite`: update conflicting records and add missing records.
- `replace_imported`: clear and replace only the table groups present in the
  archive, preserving excluded and rebuildable groups.

## Upgrade rollback

PyPI/pipx upgrades create a `pre-upgrade` data backup before invoking the
package manager. After a desktop update archive passes download, SHA-256,
extraction, and native signer-continuity checks, the same backup gate runs
before replacement. `rollback.json` records current and target versions,
install method or asset name, data archive digest, staged application,
replacement helper, and previous application location. A backup failure stops
the upgrade before package or application replacement.

## Storage management

The data card reports:

- configuration and database locations
- database and total storage size
- backup/import/update storage
- workspace schema compatibility
- row counts and rollback metadata

Cleanup is category-scoped. It can remove cache, old analytics, price-calendar
cache, event/alert history, completed flexible-date jobs, task-run history,
uploaded import archives, update staging, or old backups. Core tasks, rules,
travel lists, settings, and the newest backup are not removed by cleanup.

## Diagnostic boundary

Diagnostic snapshots contain platform, Python and dependency versions,
frontend type, runtime state, database quick-check, storage writability,
schema/table summaries, proxy-presence booleans, and recent logs.

They do not contain raw configuration files, database contents, environment
values, notification destinations, passwords, tokens, or cookies. Recursive
key filtering, inline-value masking, known-secret replacement, and a final
credential-pattern scan run before a support bundle is written. The support
bundle has its own manifest and per-file SHA-256 hashes.

## Cross-platform closure

Normal CI now covers Python 3.9, 3.12, and 3.14 on Windows and Linux plus
Python 3.12 on macOS. The desktop workflow keeps six native targets:

- Windows x64 and ARM64
- Linux x64 and ARM64
- macOS Apple Silicon and Intel

Each target builds natively, launches the frozen application, verifies the
local WebUI and Phase 6 UI, checks archive structure and executable
architecture, records native signature status, and uploads a target-specific
acceptance manifest. Tagged release jobs additionally require all six archive
names before creating checksums, attestations, or Release assets.

## Compatibility

- Archive format and workspace schema versions are independent.
- Existing `auto_save.json` files remain readable.
- Credentials remain installation-global and are not imported from portable
  backups.
- No Phase 6 operation changes `0.7.0`, creates a tag, publishes PyPI, or
  creates a GitHub Release.
