# Phase 6 Acceptance Record

Status: **Implementation complete; publication not started.**

## Product gates

| Gate | Evidence |
| --- | --- |
| Versioned backup manifest and SHA-256 | `data_tools.create_export_archive`, archive verification tests |
| Read-only preview and conflict counts | `/api/v1/data/import/preview`, immutable-database hash test |
| Transactional import and rollback | staged SQLite merge, pre-import full backup, failure-injection test |
| Upgrade backup metadata | desktop updater runtime hook and `rollback.json` test |
| Storage management | status and category-scoped dry-run/apply APIs plus Interface Settings card |
| Credential-free diagnostics | recursive redaction, known-secret masking, final pattern scan |
| Self-verifying support bundle | support manifest and per-file SHA-256 verification test |
| WebUI platform regression | Windows/Linux Python matrix plus macOS Python 3.12 |
| Six desktop target closure | native build/smoke/archive/architecture/signature manifest workflow |
| Four-language documentation | English, Chinese, Japanese, and Korean Phase 6 guides |

## Desktop matrix

| Target | Native runner | Startup gate | Artifact gate |
| --- | --- | --- | --- |
| Windows x64 | `windows-2025` | HTTP + visible main window + Phase 6 UI | ZIP, PE x64, signature status |
| Windows ARM64 | `windows-11-arm` | HTTP + visible main window + Phase 6 UI | ZIP, PE ARM64, signature status |
| Linux x64 | `ubuntu-24.04` | Xvfb + HTTP + Phase 6 UI | tar.gz, ELF x64 |
| Linux ARM64 | `ubuntu-24.04-arm` | Xvfb + HTTP + Phase 6 UI | tar.gz, ELF ARM64 |
| macOS arm64 | `macos-15` | native app process + HTTP + Phase 6 UI | ZIP, Mach-O ARM64, codesign status |
| macOS x64 | `macos-15-intel` | native app process + HTTP + Phase 6 UI | ZIP, Mach-O x64, codesign status |

Every job uploads its archive and a target-specific acceptance manifest. A tag
release job checks that all six required archive names exist before checksums,
attestation, or GitHub Release publication.

## Remaining publication decision

The repository stays at `0.7.0 Development`. No tag, GitHub Release, desktop
publication, or PyPI upload is part of this implementation commit. The final
publication decision remains an explicit follow-up action after reviewing the
CI and six desktop runner results.
