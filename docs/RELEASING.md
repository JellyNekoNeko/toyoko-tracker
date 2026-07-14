# Release automation / 发布自动化

Toyoko Tracker uses separate release tags for the Python WebUI and frozen
desktop bundles while keeping both version numbers identical.

Toyoko Tracker 的 Python WebUI 和桌面应用使用不同的发布标签，但两者的
版本号必须保持一致。

## PyPI Trusted Publishing

The workflow is `.github/workflows/publish.yml`. Configure the existing
`toyoko-tracker` project on PyPI with this Trusted Publisher:

| Field | Value |
|---|---|
| Owner | `JellyNekoNeko` |
| Repository | `toyoko-tracker` |
| Workflow | `publish.yml` |
| Environment | `pypi` |

Create a GitHub environment named `pypi`; deployment approval rules are
recommended. No PyPI API token is stored in GitHub. The official PyPA action
uses a short-lived OIDC credential and publishes attestations with the package.

在 PyPI 项目的 **Publishing → Add a new publisher → GitHub** 中填写上表。
然后在 GitHub 仓库中创建名为 `pypi` 的 Environment，建议开启发布审批。

## Native desktop signing / 桌面应用签名

The `Desktop bundles` workflow always creates SHA-256 checksums and GitHub
Sigstore build-provenance attestations. Native platform signing is enabled when
the following repository or environment secrets are configured.

`Desktop bundles` 工作流始终会生成 SHA-256 校验和使用 GitHub Sigstore
签名的构建来源证明。配置下列 Secrets 后会同时进行平台原生签名。

### macOS

| Secret | Description |
|---|---|
| `APPLE_CERTIFICATE_BASE64` | Base64-encoded Developer ID Application `.p12` |
| `APPLE_CERTIFICATE_PASSWORD` | Password of the `.p12` file |
| `APPLE_SIGNING_IDENTITY` | Example: `Developer ID Application: NAME (TEAMID)` |
| `APPLE_ID` | Apple account used by `notarytool` |
| `APPLE_TEAM_ID` | Apple Developer Team ID |
| `APPLE_APP_PASSWORD` | App-specific password for notarization |

Encode the certificate on macOS:

```bash
base64 -i DeveloperID.p12 | pbcopy
```

The workflow applies hardened-runtime signing, verifies the app, submits it to
Apple notarization, staples the ticket, and rebuilds the ZIP archive.

### Windows

| Secret | Description |
|---|---|
| `WINDOWS_CERTIFICATE_BASE64` | Base64-encoded Authenticode `.pfx` |
| `WINDOWS_CERTIFICATE_PASSWORD` | Password of the `.pfx` file |

Encode the certificate in PowerShell:

```powershell
[Convert]::ToBase64String([IO.File]::ReadAllBytes("codesign.pfx")) | Set-Clipboard
```

The workflow signs `ToyokoTracker.exe` with SHA-256 and a trusted timestamp,
then verifies the Authenticode signature before packaging.

### Verify release provenance

```bash
gh attestation verify ToyokoTracker-macos-arm64.zip \
  --repo JellyNekoNeko/toyoko-tracker
```

## Automatic desktop update / 桌面自动更新

Frozen desktop apps perform the following steps after the user selects
**Install update**:

1. Select the archive matching the current OS and CPU.
2. Download the archive and `SHA256SUMS.txt` from the same desktop release.
3. Require an exact SHA-256 match.
4. Reject archive path traversal, device entries, and links that leave the
   extracted application tree.
5. If the installed macOS or Windows app has a valid native signature, require
   the update to have the same signing identity.
6. Extract the new app into the per-user configuration directory.
7. Start a detached platform update helper and close the running app.
8. Move the current installation to `.previous`, install the staged version,
   and relaunch Toyoko Tracker.
9. Restore the previous installation if replacement fails.

用户点击“安装更新”后，桌面版会自动下载对应架构的压缩包，
强制验证 SHA-256，安全解压，保留 `.previous` 回滚副本，替换应用并重启。
当自动替换受安装目录权限影响时，系统会打开对应的 Release 下载页。

## Publishing a version / 发布新版本

1. Set the same version in `pyproject.toml` and
   `src/toyoko_tracker/desktop_version.py`.
2. Commit and push the release changes.
3. Push `vX.Y.Z` to publish the WebUI package to PyPI.
4. Push `desktop-vX.Y.Z` to build, sign, attest, and publish all desktop assets.

```bash
git tag -a vX.Y.Z -m "WebUI vX.Y.Z"
git tag -a desktop-vX.Y.Z -m "Desktop vX.Y.Z"
git push origin vX.Y.Z desktop-vX.Y.Z
```
