"""Redacted diagnostics and portable support bundles."""

from __future__ import annotations

import importlib.metadata
import json
import os
import platform
import re
import sqlite3
import sys
import tempfile
import zipfile
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, Sequence

from .data_tools import _json_bytes, _sha256_bytes, redact_secrets, storage_status
from .settings import CONFIG_DIR, HOTEL_DATABASE_PATH, __version__


SUPPORT_FORMAT = "toyoko-tracker-support"
SUPPORT_VERSION = 1
_CREDENTIAL_PATTERNS = (
    re.compile(r"pypi-[A-Za-z0-9_-]{20,}"),
    re.compile(r"\b\d{6,12}:[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"(?i)\b(?:bearer|basic)\s+[A-Za-z0-9._~+/=-]{12,}"),
    re.compile(
        r"(?i)\b(?:password|passphrase|smtp_pass|bot_token|bark_key|sendkey|api[_-]?key)"
        r"\s*[:=]\s*(?!\[redacted\]|false|true|null|none|\{\}|\"\")\S{6,}"
    ),
)
_INLINE_SECRET = re.compile(
    r"(?i)(password|passphrase|smtp_pass|bot_token|bark_key|sendkey|api[_-]?key|authorization)"
    r"(\s*[:=]\s*)([^&\s,;]+)"
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _display_path(value: str | Path) -> str:
    text = str(value)
    home = str(Path.home())
    if text == home:
        return "~"
    if text.startswith(home + os.sep):
        return "~" + text[len(home):]
    return text


def redact_text(value: Any, known_secrets: Iterable[str] = ()) -> str:
    text = str(value or "")
    for secret in known_secrets:
        cleaned = str(secret or "")
        if len(cleaned) >= 4:
            text = text.replace(cleaned, "[redacted]")
    text = _INLINE_SECRET.sub(
        lambda match: f"{match.group(1)}{match.group(2)}[redacted]",
        text,
    )
    text = re.sub(r"pypi-[A-Za-z0-9_-]{20,}", "pypi-[redacted]", text)
    text = re.sub(
        r"\b(\d{6,12}):[A-Za-z0-9_-]{20,}\b",
        r"\1:[redacted]",
        text,
    )
    return text


def _package_versions() -> dict[str, str]:
    output: dict[str, str] = {}
    for name in ("Flask", "requests", "beautifulsoup4", "pywebview", "PyInstaller", "playwright"):
        try:
            output[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            output[name] = "not installed"
    return output


def _database_health(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"exists": False, "integrity": "missing", "quick_check": "missing"}
    try:
        with (
            closing(
                sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=10)
            ) as connection,
            connection,
        ):
            quick = connection.execute("PRAGMA quick_check").fetchone()
            integrity = str(quick[0]) if quick else "unknown"
            return {
                "exists": True,
                "integrity": integrity,
                "page_count": int(connection.execute("PRAGMA page_count").fetchone()[0]),
                "freelist_count": int(connection.execute("PRAGMA freelist_count").fetchone()[0]),
            }
    except sqlite3.DatabaseError as exc:
        return {"exists": True, "integrity": "error", "error": redact_text(exc)}


def _write_health(path: Path) -> dict[str, Any]:
    path.mkdir(parents=True, exist_ok=True)
    try:
        fd, temporary_name = tempfile.mkstemp(prefix=".diagnostic-", dir=path)
        os.close(fd)
        Path(temporary_name).unlink(missing_ok=True)
        return {"writable": True}
    except OSError as exc:
        return {"writable": False, "error": redact_text(exc)}


def diagnostic_snapshot(
    *,
    runtime: Optional[Mapping[str, Any]] = None,
    logs: Optional[Sequence[str]] = None,
    known_secrets: Iterable[str] = (),
    config_dir: Optional[str | Path] = None,
    database_path: Optional[str | Path] = None,
) -> dict[str, Any]:
    root = Path(config_dir or CONFIG_DIR)
    database = Path(database_path or HOTEL_DATABASE_PATH)
    runtime_data = redact_secrets(dict(runtime or {}))
    recent_logs = [
        redact_text(line, known_secrets)
        for line in list(logs or [])[-200:]
    ]
    storage = storage_status(config_dir=root, database_path=database)
    storage["config_dir"] = _display_path(storage["config_dir"])
    storage["database_path"] = _display_path(storage["database_path"])
    rollback = storage.get("rollback")
    if isinstance(rollback, Mapping):
        storage["rollback"] = {
            key: _display_path(value) if key.endswith(("archive", "path")) else value
            for key, value in redact_secrets(rollback).items()
        }
    snapshot = {
        "format": "toyoko-tracker-diagnostic",
        "format_version": 1,
        "created_at": _utc_now(),
        "application": {
            "name": "Toyoko Tracker",
            "version": __version__,
            "frontend": str(runtime_data.get("frontend") or ("desktop" if getattr(sys, "frozen", False) else "webui")),
            "frozen": bool(getattr(sys, "frozen", False)),
            "pid": os.getpid(),
        },
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "python": platform.python_version(),
            "implementation": platform.python_implementation(),
        },
        "packages": _package_versions(),
        "health": {
            "database": _database_health(database),
            "storage": _write_health(root),
            "network_configuration": {
                "http_proxy_configured": bool(os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy")),
                "https_proxy_configured": bool(os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")),
                "no_proxy_configured": bool(os.environ.get("NO_PROXY") or os.environ.get("no_proxy")),
            },
        },
        "storage": storage,
        "runtime": runtime_data,
        "recent_logs": recent_logs,
    }
    return redact_secrets(snapshot)


def render_diagnostic_report(snapshot: Mapping[str, Any]) -> str:
    app = snapshot.get("application") or {}
    system = snapshot.get("platform") or {}
    health = snapshot.get("health") or {}
    storage = snapshot.get("storage") or {}
    runtime = snapshot.get("runtime") or {}
    lines = [
        "Toyoko Tracker diagnostic report",
        f"Created: {snapshot.get('created_at', '-')}",
        f"Version: {app.get('version', '-')}",
        f"Frontend: {app.get('frontend', '-')}",
        f"Platform: {system.get('system', '-')} {system.get('release', '-')} ({system.get('machine', '-')})",
        f"Python: {system.get('python', '-')} / {system.get('implementation', '-')}",
        f"Configuration: {storage.get('config_dir', '-')}",
        f"Database: {storage.get('database_path', '-')}",
        f"Database integrity: {(health.get('database') or {}).get('integrity', '-')}",
        f"Storage writable: {(health.get('storage') or {}).get('writable', False)}",
        f"Workspace schema: {storage.get('workspace_schema_version', 0)} / {storage.get('supported_schema_version', 0)}",
        f"Runtime state: {runtime.get('state') or runtime.get('status') or '-'}",
        f"Selected hotels: {runtime.get('selected_count') or runtime.get('hotel_count') or '-'}",
        "",
        "Table rows:",
    ]
    for table, count in sorted((storage.get("tables") or {}).items()):
        lines.append(f"- {table}: {count}")
    lines.extend(("", "Recent logs:"))
    lines.extend(str(line) for line in snapshot.get("recent_logs") or ["-"])
    return redact_text("\n".join(lines))


def find_credential_material(
    value: bytes | str,
    known_secrets: Iterable[str] = (),
) -> list[str]:
    text = value.decode("utf-8", "ignore") if isinstance(value, bytes) else str(value)
    findings: list[str] = []
    for index, secret in enumerate(known_secrets):
        cleaned = str(secret or "")
        if len(cleaned) >= 4 and cleaned in text:
            findings.append(f"known-secret-{index + 1}")
    for index, pattern in enumerate(_CREDENTIAL_PATTERNS):
        if pattern.search(text):
            findings.append(f"credential-pattern-{index + 1}")
    return findings


def create_support_bundle(
    destination: str | Path,
    *,
    runtime: Optional[Mapping[str, Any]] = None,
    logs: Optional[Sequence[str]] = None,
    known_secrets: Iterable[str] = (),
    config_dir: Optional[str | Path] = None,
    database_path: Optional[str | Path] = None,
) -> dict[str, Any]:
    destination_path = Path(destination)
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    secrets = tuple(str(value) for value in known_secrets if value)
    snapshot = diagnostic_snapshot(
        runtime=runtime,
        logs=logs,
        known_secrets=secrets,
        config_dir=config_dir,
        database_path=database_path,
    )
    payloads = {
        "diagnostics.json": _json_bytes(snapshot),
        "report.txt": render_diagnostic_report(snapshot).encode("utf-8"),
    }
    findings = {
        name: find_credential_material(content, secrets)
        for name, content in payloads.items()
    }
    findings = {name: items for name, items in findings.items() if items}
    if findings:
        raise ValueError(f"support bundle credential scan failed: {findings}")
    manifest = {
        "format": SUPPORT_FORMAT,
        "format_version": SUPPORT_VERSION,
        "created_at": _utc_now(),
        "credential_scan": "passed",
        "files": [
            {"path": name, "size": len(content), "sha256": _sha256_bytes(content)}
            for name, content in sorted(payloads.items())
        ],
    }
    temporary = destination_path.with_suffix(destination_path.suffix + ".part")
    temporary.unlink(missing_ok=True)
    with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr("manifest.json", _json_bytes(manifest))
        for name, content in payloads.items():
            bundle.writestr(name, content)
    os.replace(temporary, destination_path)
    return {
        "path": str(destination_path),
        "filename": destination_path.name,
        "size": destination_path.stat().st_size,
        "manifest": manifest,
    }


def verify_support_bundle(
    path: str | Path,
    *,
    known_secrets: Iterable[str] = (),
) -> dict[str, Any]:
    with zipfile.ZipFile(path) as bundle:
        manifest = json.loads(bundle.read("manifest.json"))
        if manifest.get("format") != SUPPORT_FORMAT:
            raise ValueError("support bundle format is invalid")
        findings: dict[str, list[str]] = {}
        for item in manifest.get("files") or []:
            content = bundle.read(str(item["path"]))
            if len(content) != int(item["size"]) or _sha256_bytes(content) != item["sha256"]:
                raise ValueError(f"support bundle checksum mismatch: {item['path']}")
            matches = find_credential_material(content, known_secrets)
            if matches:
                findings[str(item["path"])] = matches
        return {
            "valid": not findings,
            "credential_findings": findings,
            "manifest": manifest,
        }
