from __future__ import annotations

import os
import queue
import shutil
import smtplib
import subprocess
import sys
import threading
import time
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime
from email.message import EmailMessage
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import quote, urlparse

import requests

from .event_center import begin_delivery, finish_delivery, publish_event
from .i18n import normalize_primary_language as _normalize_primary_language
from .models import AppConfig, HotelResult
from .settings import (
    DEFAULT_BARK_SERVER,
    DEFAULT_BARK_CRITICAL_SOUND,
    DEFAULT_BARK_CRITICAL_VOLUME,
    DEFAULT_ENGINE,
    DEFAULT_MEMBERSHIP_STATUS,
    DEFAULT_PRIMARY_LANGUAGE,
    DEFAULT_ROOM_REQUIREMENT,
    DEFAULT_SMART_PARALLEL_WORKERS,
    DEFAULT_SMOKING,
)

def _noop(_message: str) -> None:
    return None


_log: Callable[[str], None] = _noop
_set_action: Callable[[str], None] = _noop

_ALERT_STATE: Dict[str, Dict[str, Any]] = {}
_AVAILABILITY_LOGS: List[Dict[str, Any]] = []
_AVAILABILITY_LOG_REVISION = 0
_ALERT_STATE_LOCK = threading.RLock()
_PUSH_STATUS_LOCK = threading.Lock()
_PUSH_STATUS: Dict[str, Dict[str, Any]] = {}
_MAIL_QUEUE: "queue.Queue[Dict[str, Any]]" = queue.Queue()
_MAIL_THREAD: Optional[threading.Thread] = None
_MAIL_STOP = threading.Event()
_MAX_CLOCK_SKEW_SECONDS = 300


def set_notification_hooks(log: Callable[[str], None], set_action: Callable[[str], None]) -> None:
    global _log, _set_action
    _log = log
    _set_action = set_action


def clear_alert_state() -> None:
    global _AVAILABILITY_LOG_REVISION
    with _ALERT_STATE_LOCK:
        _ALERT_STATE.clear()
        _AVAILABILITY_LOGS.clear()
        _AVAILABILITY_LOG_REVISION += 1


def availability_log_revision() -> int:
    with _ALERT_STATE_LOCK:
        return _AVAILABILITY_LOG_REVISION


def availability_log_snapshot() -> List[Dict[str, Any]]:
    now = time.time()
    out: List[Dict[str, Any]] = []
    with _ALERT_STATE_LOCK:
        items = deepcopy(_AVAILABILITY_LOGS[-100:])
    for item in reversed(items):
        entry = deepcopy(item)
        start_ts = float(entry.get("appeared_ts") or 0)
        end_ts = entry.get("disappeared_ts")
        entry["duration_sec"] = (
            max(0, int((float(end_ts) if end_ts else now) - start_ts))
            if start_ts else None
        )
        out.append(entry)
    return out


def notification_checkpoint_snapshot() -> Dict[str, Any]:
    with _ALERT_STATE_LOCK:
        return {
            "alert_state": deepcopy(_ALERT_STATE),
            "availability_logs": deepcopy(_AVAILABILITY_LOGS[-100:]),
        }


def restore_notification_checkpoint(payload: Dict[str, Any]) -> None:
    global _AVAILABILITY_LOG_REVISION
    alert_state = payload.get("alert_state") if isinstance(payload, dict) else {}
    availability_logs = payload.get("availability_logs") if isinstance(payload, dict) else []
    with _ALERT_STATE_LOCK:
        _ALERT_STATE.clear()
        if isinstance(alert_state, dict):
            _ALERT_STATE.update(deepcopy(alert_state))
        _AVAILABILITY_LOGS.clear()
        if isinstance(availability_logs, list):
            _AVAILABILITY_LOGS.extend(deepcopy(availability_logs[-100:]))
        _AVAILABILITY_LOG_REVISION += 1


def _alert_state_snapshot(key: str) -> Dict[str, Any]:
    with _ALERT_STATE_LOCK:
        return deepcopy(_ALERT_STATE.get(key, {"available": False, "sent": 0, "last": 0.0}))


def _set_alert_state(key: str, state: Dict[str, Any]) -> None:
    with _ALERT_STATE_LOCK:
        _ALERT_STATE[key] = deepcopy(state)


def _set_push_status(channel: str, state: str, message: str = "") -> None:
    with _PUSH_STATUS_LOCK:
        _PUSH_STATUS[channel] = {
            "state": state,
            "message": message,
            "ts": time.time(),
        }


def notification_status_snapshot(cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
    channels = [
        ("telegram", "Telegram机器人", "Telegram Bot", bool(cfg.get("enable_telegram"))),
        ("local", "本地通知", "Local Notifications", bool(cfg.get("enable_local"))),
        ("email", "邮件", "Email", bool(cfg.get("enable_email"))),
        ("bark", "Bark", "Bark", bool(cfg.get("enable_bark"))),
        ("serverchan", "Server酱", "Server Chan", bool(cfg.get("enable_serverchan"))),
    ]
    now = time.time()
    with _PUSH_STATUS_LOCK:
        latest = deepcopy(_PUSH_STATUS)
    out: List[Dict[str, Any]] = []
    for key, label_zh, label_en, enabled in channels:
        item = latest.get(key, {})
        state = str(item.get("state") or "waiting")
        if not enabled:
            state = "disabled"
        timestamp = float(item.get("ts") or 0)
        age = now - timestamp if timestamp else None
        if age is not None and age < -_MAX_CLOCK_SKEW_SECONDS:
            age = None
        out.append({
            "key": key,
            "label_zh": label_zh,
            "label_en": label_en,
            "enabled": enabled,
            "state": state,
            "message": item.get("message") or "",
            "age_sec": max(0, int(age)) if age is not None else None,
        })
    return out


def _room_title_zh(title: Optional[str]) -> str:
    return _room_title_primary(title, "zh_cn")


def _room_title_primary(title: Optional[str], primary_language: Optional[str] = None) -> str:
    if not title:
        return ""
    lang = _normalize_primary_language(primary_language)
    t = str(title).lower()
    room_key = ""
    if "economy" in t and "single" in t:
        room_key = "economy_single"
    elif "single" in t:
        room_key = "single"
    elif "economy" in t and "double" in t:
        room_key = "economy_double"
    elif "double" in t:
        room_key = "double"
    elif "economy" in t and "twin" in t:
        room_key = "economy_twin"
    elif "twin" in t:
        room_key = "twin"
    elif "heartful" in t or "accessible" in t:
        room_key = "accessible"
    labels = {
        "zh_cn": {
            "economy_single": "经济单人房", "single": "单人房",
            "economy_double": "经济大床房", "double": "大床房",
            "economy_twin": "经济双床房", "twin": "双床房", "accessible": "无障碍房",
        },
        "zh_tw": {
            "economy_single": "經濟單人房", "single": "單人房",
            "economy_double": "經濟雙人床房", "double": "雙人床房",
            "economy_twin": "經濟雙床房", "twin": "雙床房", "accessible": "無障礙房",
        },
        "ja": {
            "economy_single": "エコノミーシングル", "single": "シングル",
            "economy_double": "エコノミーダブル", "double": "ダブル",
            "economy_twin": "エコノミーツイン", "twin": "ツイン", "accessible": "ハートフルルーム",
        },
        "ko": {
            "economy_single": "이코노미 싱글", "single": "싱글",
            "economy_double": "이코노미 더블", "double": "더블",
            "economy_twin": "이코노미 트윈", "twin": "트윈", "accessible": "배리어프리룸",
        },
        "en": {
            "economy_single": "Economy Single", "single": "Single",
            "economy_double": "Economy Double", "double": "Double",
            "economy_twin": "Economy Twin", "twin": "Twin", "accessible": "Accessible Room",
        },
    }
    return labels.get(lang, labels["zh_cn"]).get(room_key, "")


def _local_notification_text(text: str) -> str:
    if not isinstance(text, str):
        return text
    return (text
            .replace("🟢", "[START]")
            .replace("✅", "[OK]")
            .replace("🔁", "[REMINDER]")
            .replace("❌", "[NO]")
            .replace("❗", "[CHECK]")
            .replace("❓", "[UNKNOWN]")
            .replace("→", "->"))


# ========= Notification（Telegram/Local/Mail）=========
def _tg_enabled(cfg: AppConfig) -> bool:
    return cfg.enable_telegram and bool(cfg.bot_token) and bool(cfg.chat_id)


def notify_telegram(cfg: AppConfig, message: str) -> None:
    if not _tg_enabled(cfg):
        return
    try:
        _set_push_status("telegram", "pushing", "sending")
        _set_action("[tg] sending message...")
        url = f"https://api.telegram.org/bot{cfg.bot_token}/sendMessage"
        payload = {"chat_id": cfg.chat_id, "text": message}
        resp = requests.post(url, data=payload, timeout=15)
        ok = False
        err = None
        if resp is not None:
            try:
                data = resp.json()
                ok = bool(data.get("ok"))
                if not ok:
                    err = data.get("description") or str(data)
            except Exception:
                err = f"HTTP {resp.status_code} non-JSON"
        if ok:
            _set_action("[tg] sent OK")
            _set_push_status("telegram", "success", "sent OK")
            _log("[tg] sent OK")
        else:
            _set_action(f"[tg] failed: {err or 'unknown error'}")
            _set_push_status("telegram", "failed", err or "unknown error")
            _log(f"[tg] failed: {err or 'unknown error'}")
    except Exception as e:
        _set_action(f"[tg] exception: {e}")
        _set_push_status("telegram", "failed", str(e))
        _log(f"[tg] exception: {e}")


def _bark_enabled(cfg: AppConfig) -> bool:
    return bool(getattr(cfg, "enable_bark", False) and getattr(cfg, "bark_key", ""))


def validate_bark_key(key: str) -> tuple[bool, str]:
    value = str(key or "").strip().strip("/")
    if not value:
        return False, "Bark Key is empty"
    if value.startswith(("http://", "https://")):
        parsed = urlparse(value)
        parts = [p for p in parsed.path.split("/") if p]
        value = parts[0] if parts else ""
    if len(value) > 48:
        return False, "Bark Key looks too long. 请填写 Bark 首页的 Device Key，不是 Device Token。"
    if len(value) < 8:
        return False, "Bark Key looks too short"
    return True, ""


def _normalize_bark_config(cfg: AppConfig) -> tuple[str, str]:
    server = (getattr(cfg, "bark_server", DEFAULT_BARK_SERVER) or DEFAULT_BARK_SERVER).strip().rstrip("/")
    key = str(getattr(cfg, "bark_key", "") or "").strip().strip("/")
    if key.startswith(("http://", "https://")):
        parsed = urlparse(key)
        if parsed.scheme and parsed.netloc:
            server = f"{parsed.scheme}://{parsed.netloc}".rstrip("/")
            path_parts = [p for p in parsed.path.split("/") if p]
            if path_parts:
                key = path_parts[0]
    return server, key


def _bark_response_ok(resp: requests.Response) -> tuple[bool, str]:
    parsed = None
    try:
        parsed = resp.json()
    except Exception:
        parsed = None
    if not (200 <= resp.status_code < 300):
        if isinstance(parsed, dict):
            message = parsed.get("message") or parsed.get("error") or str(parsed)
            if "failed to get device token" in str(message).lower():
                message = (
                    "Bark server cannot find this device key. "
                    "请确认 Bark Key 来自同一个 Bark Server，公共服务请使用 https://api.day.app。"
                )
            return False, f"HTTP {resp.status_code} code={parsed.get('code')} {message}"
        return False, f"HTTP {resp.status_code}"
    if parsed is None:
        return True, "sent OK"
    try:
        data = parsed
    except Exception:
        return True, "sent OK"
    code = data.get("code")
    if code in (200, 0, None) or bool(data.get("success")):
        return True, str(data.get("message") or "sent OK")
    message = data.get("message") or data.get("error") or str(data)
    return False, f"code={code} {message}"


def _send_bark_attempts(
    server: str,
    key: str,
    title: str,
    body: str,
    url: Optional[str],
    extra_payload: Optional[Dict[str, Any]] = None,
) -> tuple[bool, str]:
    payload = {
        "title": title,
        "body": body,
        "sound": "minuet",
        "group": "Toyoko Tracker",
    }
    if url:
        payload["url"] = url
    if extra_payload:
        payload.update(extra_payload)

    push_payload = {"device_key": key, **payload}
    attempts = [
        ("POST /{key}", "post", f"{server}/{key}", {"json": payload}),
        ("POST /push", "post", f"{server}/push", {"json": push_payload}),
    ]
    short_title = quote(str(title or "Toyoko Chan"), safe="")
    short_body = quote(str(body or ""), safe="")
    if len(short_title) + len(short_body) < 6000:
        params = {"url": url} if url else {}
        if extra_payload:
            params.update({k: v for k, v in extra_payload.items() if k in {"level", "volume", "sound", "group"}})
        attempts.append(("GET /{key}/{title}/{body}", "get", f"{server}/{key}/{short_title}/{short_body}", {"params": params}))

    errors: List[str] = []
    for label, method, endpoint, kwargs in attempts:
        try:
            if method == "post":
                resp = requests.post(endpoint, timeout=15, **kwargs)
            else:
                resp = requests.get(endpoint, timeout=15, **kwargs)
            ok, message = _bark_response_ok(resp)
            if ok:
                return True, f"{label}: {message}"
            body_preview = (resp.text or "").replace("\n", " ")[:160]
            errors.append(f"{label}: {message} {body_preview}".strip())
        except Exception as attempt_error:
            errors.append(f"{label}: {attempt_error}")
    return False, " | ".join(errors) or "all Bark send attempts failed"


def notify_bark(cfg: AppConfig, title: str, body: str, url: Optional[str] = None) -> None:
    if not _bark_enabled(cfg):
        return
    try:
        _set_push_status("bark", "pushing", "sending")
        server, key = _normalize_bark_config(cfg)
        valid, validation_error = validate_bark_key(key)
        if not valid:
            _set_push_status("bark", "failed", validation_error)
            _set_action(f"[bark] failed: {validation_error}")
            _log(f"[bark] failed: {validation_error}")
            return

        # Bark/APNs can reject very long payloads. Other channels keep the full
        # rich message, while Bark gets a compact version with the booking URL.
        compact_body = str(body or "")
        max_body_chars = 2800
        if len(compact_body) > max_body_chars:
            compact_body = compact_body[:max_body_chars].rstrip() + "\n...\n(内容已为 Bark 精简 / shortened for Bark)"
        if url and url not in compact_body:
            compact_body = f"{compact_body}\n\n{url}".strip()

        critical = bool(getattr(cfg, "bark_critical_enabled", False))
        volume = max(0, min(10, int(getattr(cfg, "bark_critical_volume", DEFAULT_BARK_CRITICAL_VOLUME) or 0)))
        critical_payload = None
        if critical:
            critical_payload = {"level": "critical", "volume": volume}
            sound = str(getattr(cfg, "bark_critical_sound", DEFAULT_BARK_CRITICAL_SOUND) or DEFAULT_BARK_CRITICAL_SOUND).strip()
            if sound:
                critical_payload["sound"] = sound

        ok, message = _send_bark_attempts(
            server,
            key,
            title,
            compact_body,
            url,
            critical_payload,
        )
        if ok:
            prefix = "critical " if critical else ""
            _set_action(f"[bark] {prefix}sent OK")
            _set_push_status("bark", "success", message)
            _log(f"[bark] {prefix}sent OK: {message}")
            return

        _set_action(f"[bark] failed: {message[:160]}")
        _set_push_status("bark", "failed", message[:240])
        _log(f"[bark] failed: {message}")
    except Exception as e:
        _set_action(f"[bark] exception: {e}")
        _set_push_status("bark", "failed", str(e))
        _log(f"[bark] exception: {e}")


def _serverchan_enabled(cfg: AppConfig) -> bool:
    return bool(getattr(cfg, "enable_serverchan", False) and getattr(cfg, "serverchan_sendkey", ""))


def notify_serverchan(cfg: AppConfig, title: str, body: str) -> None:
    if not _serverchan_enabled(cfg):
        return
    try:
        _set_push_status("serverchan", "pushing", "sending")
        sendkey = str(getattr(cfg, "serverchan_sendkey", "")).strip()
        endpoint = f"https://sctapi.ftqq.com/{sendkey}.send"
        resp = requests.post(endpoint, data={"title": title, "desp": body}, timeout=15)
        ok = 200 <= resp.status_code < 300
        if ok:
            try:
                data = resp.json()
                ok = int(data.get("code", 0)) == 0
            except Exception:
                ok = True
        if ok:
            _set_action("[serverchan] sent OK")
            _set_push_status("serverchan", "success", "sent OK")
            _log("[serverchan] sent OK")
        else:
            _set_action(f"[serverchan] failed: HTTP {resp.status_code}")
            _set_push_status("serverchan", "failed", f"HTTP {resp.status_code}")
            _log(f"[serverchan] failed: HTTP {resp.status_code} {resp.text[:160]}")
    except Exception as e:
        _set_action(f"[serverchan] exception: {e}")
        _set_push_status("serverchan", "failed", str(e))
        _log(f"[serverchan] exception: {e}")


def notify_push_channels(
    cfg: AppConfig,
    title: str,
    body: str,
    url: Optional[str] = None,
    *,
    event_id: str = "",
    desktop_url: Optional[str] = None,
) -> None:
    channels = (
        ("telegram", bool(getattr(cfg, "enable_telegram", False)), lambda: notify_telegram(cfg, body)),
        ("email", bool(getattr(cfg, "enable_email", False)), lambda: notify_email(cfg, title, body, event_id=event_id)),
        (
            "local",
            bool(getattr(cfg, "enable_local", False)),
            lambda: notify_local(cfg, title, body, desktop_url),
        ),
        ("bark", bool(getattr(cfg, "enable_bark", False)), lambda: notify_bark(cfg, title, body, url)),
        ("serverchan", bool(getattr(cfg, "enable_serverchan", False)), lambda: notify_serverchan(cfg, title, body)),
    )
    for channel, enabled, sender in channels:
        if not enabled:
            continue
        if event_id and not begin_delivery(event_id, channel):
            _log(f"[{channel}] duplicate event skipped: {event_id[:8]}")
            continue
        try:
            sender()
            with _PUSH_STATUS_LOCK:
                delivery_state = str((_PUSH_STATUS.get(channel) or {}).get("state") or "queued")
                detail = str((_PUSH_STATUS.get(channel) or {}).get("message") or "")
            if event_id:
                finish_delivery(
                    event_id,
                    channel,
                    "failed" if delivery_state == "failed" else (
                        "success" if delivery_state == "success" else "queued"
                    ),
                    detail,
                )
        except Exception as exc:
            if event_id:
                finish_delivery(event_id, channel, "failed", str(exc))
            raise


def _publish_and_notify(
    cfg: AppConfig,
    event_type: str,
    dedupe_key: str,
    title: str,
    body: str,
    url: Optional[str] = None,
    *,
    enabled: bool = True,
    dedupe_window_seconds: int = 30,
    payload: Optional[Dict[str, Any]] = None,
) -> str:
    task_id = str(getattr(cfg, "task_id", "") or "")
    event_payload = {
        "title": title,
        "body": body,
        "url": url or "",
        "task_id": task_id or None,
    }
    if payload:
        event_payload.update(payload)
    event = publish_event(
        event_type,
        dedupe_key,
        event_payload,
        dedupe_window_seconds=dedupe_window_seconds,
    )
    desktop_url = ""
    if enabled and event.created:
        try:
            from .desktop_lifecycle import build_deep_link, record_desktop_notification

            desktop_url = build_deep_link(
                view="monitor",
                task_id=task_id,
                hotel_code=str(event_payload.get("code") or ""),
                stay_date=str(
                    event_payload.get("stay_date")
                    or event_payload.get("start_date")
                    or getattr(cfg, "start_date", "")
                    or ""
                ),
                event_id=event.event_id,
            )
            record_desktop_notification(
                title,
                body,
                desktop_url,
                dedupe_key=event.event_id,
            )
        except Exception as exc:
            _log(f"[desktop] notification state skipped: {exc}")
    if enabled:
        notify_push_channels(
            cfg,
            title,
            body,
            url,
            event_id=event.event_id,
            desktop_url=desktop_url or None,
        )
    if task_id:
        try:
            from .alerting import record_legacy_event

            outcomes: Dict[str, Dict[str, str]] = {}
            for item in notification_status_snapshot(asdict(cfg)):
                if not item.get("enabled") or not enabled:
                    continue
                state = str(item.get("state") or "queued")
                outcomes[str(item["key"])] = {
                    "state": (
                        "sent"
                        if state == "success"
                        else "queued"
                        if state in {"pushing", "waiting", "queued"}
                        else "failed"
                    ),
                    "detail": str(item.get("message") or ""),
                }
            record_legacy_event(
                source_event_id=event.event_id,
                task_id=task_id,
                event_type=event_type,
                payload=event_payload,
                outcomes=outcomes,
            )
        except Exception as exc:
            _log(f"[alerts] legacy event mirror skipped: {exc}")
    return event.event_id


def notify_local(
    cfg: AppConfig,
    title: str,
    body: str,
    url: Optional[str] = None,
) -> None:
    if not getattr(cfg, "enable_local", False):
        _log("[local] skipped: enable_local = False")
        return
    try:
        _set_push_status("local", "pushing", "notifying")
        _set_action("[local] notifying...")
        # Windows consoles/toasters may not render emoji properly — sanitize to ASCII
        if os.name == "nt":
            title = _local_notification_text(title)
            body = _local_notification_text(body)
        if sys.platform == "darwin":
            title = _local_notification_text(title)
            body = _local_notification_text(body)
            # macOS requires notification permission for the sending app.
            # Prefer terminal-notifier when installed; fall back to osascript.
            tn = shutil.which("terminal-notifier")
            sent = False
            if tn:
                try:
                    command = [
                        tn,
                        "-title",
                        title,
                        "-message",
                        body,
                        "-group",
                        "toyoko-inn-tracker",
                        "-sound",
                        "default",
                    ]
                    if url:
                        command.extend(["-open", url])
                    proc = subprocess.run(
                        command,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        timeout=5,
                    )
                    if proc.returncode == 0:
                        sent = True
                        _set_push_status("local", "success", "terminal-notifier sent OK")
                        _log("[local] terminal-notifier sent OK")
                    else:
                        err = (proc.stderr or proc.stdout or "").strip()
                        _log(f"[local] terminal-notifier failed: {err or 'non-zero exit'}")
                except Exception as _tn_e:
                    _log(f"[local] terminal-notifier failed: {_tn_e}")
            if not sent:
                script = (
                    'on run argv\n'
                    '  display notification (item 2 of argv) with title (item 1 of argv) '
                    'subtitle "Toyoko Tracker" sound name "Glass"\n'
                    'end run'
                )
                try:
                    proc = subprocess.run(
                        ["osascript", "-e", script, title, body],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        timeout=5,
                    )
                    if proc.returncode == 0:
                        sent = True
                        _set_push_status("local", "success", "osascript sent OK")
                        _log("[local] osascript sent OK")
                    else:
                        err = (proc.stderr or proc.stdout or "").strip()
                        _log(f"[local] osascript failed: {err or 'non-zero exit'}")
                except Exception as _e2:
                    _log(f"[local] osascript failed: {_e2}")
            if not sent:
                _set_push_status("local", "failed", "macOS notification not delivered")
                _log("[local] macOS notification was not delivered. Check System Settings > Notifications for Terminal/Python/osascript.")
        elif os.name == "nt":
            # Non-blocking Windows balloon tip via PowerShell + NotifyIcon (no user confirmation required)
            try:
                powershell = (
                    shutil.which("powershell.exe")
                    or shutil.which("powershell")
                    or shutil.which("pwsh.exe")
                    or shutil.which("pwsh")
                )
                if not powershell:
                    raise FileNotFoundError("PowerShell was not found")
                # Prepare a short PowerShell script that shows a system tray balloon tip and exits
                ps_script = (
                    "Add-Type -AssemblyName System.Windows.Forms; "
                    "Add-Type -AssemblyName System.Drawing; "
                    "$ni = New-Object System.Windows.Forms.NotifyIcon; "
                    "$ni.Icon = [System.Drawing.SystemIcons]::Information; "
                    "$ni.Visible = $true; "
                    "$ni.BalloonTipTitle = $env:TOYOKO_NOTIFICATION_TITLE; "
                    "$ni.BalloonTipText = $env:TOYOKO_NOTIFICATION_BODY; "
                    "if ($env:TOYOKO_NOTIFICATION_URL) { "
                    "$ni.add_BalloonTipClicked({ "
                    "Start-Process $env:TOYOKO_NOTIFICATION_URL; "
                    "}); "
                    "} "
                    "$ni.ShowBalloonTip(4000); "  # show for ~4s
                    "Start-Sleep -Milliseconds 6500; "
                    "$ni.Dispose();"
                )
                notification_env = os.environ.copy()
                notification_env["TOYOKO_NOTIFICATION_TITLE"] = title
                notification_env["TOYOKO_NOTIFICATION_BODY"] = body
                notification_env["TOYOKO_NOTIFICATION_URL"] = str(url or "")
                subprocess.Popen(
                    [powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_script],
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    env=notification_env,
                )
                _set_push_status("local", "success", "NotifyIcon invoked")
                _log("[local] powershell NotifyIcon balloon shown (non-blocking)")
            except Exception as _e_win_balloon:
                _set_push_status("local", "failed", str(_e_win_balloon))
                _log(f"[local] NotifyIcon balloon failed: {_e_win_balloon}")
        else:
            try:
                notify_send = shutil.which("notify-send")
                if not notify_send:
                    raise FileNotFoundError("notify-send was not found; install libnotify")
                xdg_open = shutil.which("xdg-open") if url else None
                if url and xdg_open:
                    def wait_for_notification_action() -> None:
                        process = None
                        try:
                            process = subprocess.Popen(
                                [
                                    notify_send,
                                    "--app-name=ToyokoTracker",
                                    "--hint=string:desktop-entry:ToyokoTracker",
                                    "--action=default=Open",
                                    title,
                                    body,
                                ],
                                stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL,
                                text=True,
                            )
                            action, _ = process.communicate(timeout=300)
                            if process.returncode == 0 and action.strip() == "default":
                                subprocess.Popen(
                                    [xdg_open, url],
                                    stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL,
                                )
                        except Exception as action_error:
                            if process is not None and process.poll() is None:
                                process.kill()
                            _log(f"[local] notify-send action failed: {action_error}")

                    threading.Thread(
                        target=wait_for_notification_action,
                        name="toyoko-notify-action",
                        daemon=True,
                    ).start()
                    _set_push_status("local", "success", "notify-send action queued")
                    _log("[local] notify-send action notification queued")
                    return
                command = [
                    notify_send,
                    "--hint=string:desktop-entry:ToyokoTracker",
                    title,
                    body,
                ]
                proc = subprocess.run(
                    command,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=5,
                )
                if proc.returncode != 0:
                    detail = (proc.stderr or proc.stdout or "non-zero exit").strip()
                    raise RuntimeError(detail)
                _set_push_status("local", "success", "notify-send sent OK")
                _log("[local] notify-send sent OK")
            except Exception as _e4:
                _set_push_status("local", "failed", str(_e4))
                _log(f"[local] notify-send failed: {_e4}")
    except Exception as e:
        _set_push_status("local", "failed", str(e))
        _log(f"[local] exception: {e}")


def _email_enabled(cfg: AppConfig) -> bool:
    return bool(cfg.enable_email and cfg.smtp_host and cfg.email_from and cfg.email_to)

def _send_email_now(
    cfg_snapshot: Dict[str, Any],
    subject: str,
    body: str,
    event_id: str = "",
) -> None:
    """
    低层“立即发送”函数：使用配置快照（dict）防止并发修改。
    逻辑与旧版同步发送一致。
    """
    try:
        host = cfg_snapshot.get("smtp_host") or ""
        port = int(cfg_snapshot.get("smtp_port") or 0)
        use_tls = bool(cfg_snapshot.get("smtp_tls"))
        user = cfg_snapshot.get("smtp_user") or ""
        passwd = cfg_snapshot.get("smtp_pass") or ""
        email_from = cfg_snapshot.get("email_from") or ""
        email_to = cfg_snapshot.get("email_to") or ""

        if not (host and email_from and email_to and port):
            _set_push_status("email", "failed", "incomplete SMTP configuration")
            _log("[mail] skipped: incomplete SMTP configuration")
            return

        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = email_from
        tos = [x.strip() for x in str(email_to).split(",") if x.strip()]
        msg["To"] = ", ".join(tos) if tos else email_to
        msg.set_content(body)

        if port == 465:
            server = smtplib.SMTP_SSL(host, port, timeout=20)
        else:
            server = smtplib.SMTP(host, port, timeout=20)
            if use_tls:
                try:
                    server.ehlo()
                    server.starttls()
                    server.ehlo()
                except Exception:
                    pass

        if user and passwd:
            server.login(user, passwd)
        server.send_message(msg)
        try:
            server.quit()
        except Exception:
            server.close()

        _log("[mail] sent OK (worker)")
        _set_push_status("email", "success", "sent OK")
        if event_id:
            finish_delivery(event_id, "email", "success", "sent OK")
    except Exception as e:
        _set_push_status("email", "failed", str(e))
        if event_id:
            finish_delivery(event_id, "email", "failed", str(e))
        _log(f"[mail] exception (worker): {e}")


def _ensure_mail_worker_started() -> None:
    global _MAIL_THREAD
    if _MAIL_THREAD and _MAIL_THREAD.is_alive():
        return
    _MAIL_STOP.clear()

    def _mail_worker():
        _log("[mail] worker started")
        while not _MAIL_STOP.is_set():
            try:
                item = _MAIL_QUEUE.get(timeout=0.5)
            except Exception:
                continue
            try:
                _send_email_now(
                    item["cfg"], item["subject"], item["body"], str(item.get("event_id") or "")
                )
            finally:
                try:
                    _MAIL_QUEUE.task_done()
                except Exception:
                    pass
        _log("[mail] worker stopped")

    _MAIL_THREAD = threading.Thread(target=_mail_worker, name="mail-worker", daemon=True)
    _MAIL_THREAD.start()

def notify_email(cfg: AppConfig, subject: str, body: str, event_id: str = "") -> None:
    """
    """
    if not _email_enabled(cfg):
        return
    try:
        _ensure_mail_worker_started()
        cfg_snapshot = deepcopy(asdict(cfg))
        _MAIL_QUEUE.put_nowait({
            "cfg": cfg_snapshot, "subject": subject, "body": body,
            "event_id": event_id,
        })
        _set_action("[mail] queued")
        _set_push_status("email", "pushing", "queued")
        _log("[mail] queued")
    except Exception as e:
        _set_action(f"[mail] queue exception: {e}")
        _set_push_status("email", "failed", str(e))
        _log(f"[mail] queue exception: {e}")


PUSH_I18N = {
    "tracking_started": {"zh_cn": "检索已启动", "zh_tw": "搜尋已啟動", "ja": "検索を開始しました", "ko": "검색을 시작했습니다", "en": "Tracking Started"},
    "tracking_stopped": {"zh_cn": "检索已停止", "zh_tw": "搜尋已停止", "ja": "検索を停止しました", "ko": "검색을 중지했습니다", "en": "Tracking Stopped"},
    "room_available": {"zh_cn": "发现空房", "zh_tw": "發現空房", "ja": "空室を見つけました", "ko": "빈 객실을 찾았습니다", "en": "Room Available"},
    "room_reminder": {"zh_cn": "空房重复提醒", "zh_tw": "空房重複提醒", "ja": "空室の再通知", "ko": "빈 객실 반복 알림", "en": "Room Reminder"},
    "no_longer_available": {"zh_cn": "空房已消失", "zh_tw": "空房已消失", "ja": "空室がなくなりました", "ko": "빈 객실이 사라졌습니다", "en": "No Longer Available"},
    "room_count_changed": {"zh_cn": "可用房间数量变动", "zh_tw": "可用房間數量變動", "ja": "空室数が変わりました", "ko": "이용 가능 객실 수 변경", "en": "Available Room Count Changed"},
    "search_check_required": {"zh_cn": "搜索异常提醒", "zh_tw": "搜尋異常提醒", "ja": "検索確認が必要です", "ko": "검색 확인 필요", "en": "Search Check Required"},
    "time": {"zh_cn": "时间", "zh_tw": "時間", "ja": "時刻", "ko": "시간", "en": "Time"},
    "dates": {"zh_cn": "日期", "zh_tw": "日期", "ja": "日付", "ko": "날짜", "en": "Dates"},
    "area": {"zh_cn": "区域", "zh_tw": "區域", "ja": "地域", "ko": "지역", "en": "Area"},
    "guests_rooms": {"zh_cn": "人数/房间", "zh_tw": "人數/房間", "ja": "人数/部屋", "ko": "인원/객실", "en": "Guests/Rooms"},
    "smoking_pref": {"zh_cn": "吸烟偏好", "zh_tw": "吸菸偏好", "ja": "喫煙条件", "ko": "흡연 조건", "en": "Smoking"},
    "room_type_pref": {"zh_cn": "房型偏好", "zh_tw": "房型偏好", "ja": "部屋タイプ条件", "ko": "객실 타입 조건", "en": "Room Type"},
    "membership": {"zh_cn": "会员状态", "zh_tw": "會員狀態", "ja": "会員状態", "ko": "회원 상태", "en": "Membership"},
    "engine": {"zh_cn": "引擎", "zh_tw": "引擎", "ja": "エンジン", "ko": "엔진", "en": "Engine"},
    "smart_parallel": {"zh_cn": "智能并行", "zh_tw": "智慧並行", "ja": "スマート並列", "ko": "스마트 병렬", "en": "Smart Parallel"},
    "hotels": {"zh_cn": "酒店", "zh_tw": "飯店", "ja": "ホテル", "ko": "호텔", "en": "Hotels"},
    "hotel_code": {"zh_cn": "酒店编号", "zh_tw": "飯店編號", "ja": "ホテル番号", "ko": "호텔 코드", "en": "Hotel Code"},
    "hotel": {"zh_cn": "酒店", "zh_tw": "飯店", "ja": "ホテル", "ko": "호텔", "en": "Hotel"},
    "rooms_prices": {"zh_cn": "房型与价格", "zh_tw": "房型與價格", "ja": "部屋タイプと料金", "ko": "객실 타입 및 가격", "en": "Rooms & Prices"},
    "display_price": {"zh_cn": "显示价", "zh_tw": "顯示價", "ja": "表示料金", "ko": "표시 가격", "en": "Display Price"},
    "member_price": {"zh_cn": "会员价", "zh_tw": "會員價", "ja": "会員料金", "ko": "회원가", "en": "Member"},
    "non_member_price": {"zh_cn": "非会员价", "zh_tw": "非會員價", "ja": "非会員料金", "ko": "비회원가", "en": "Non-member"},
    "left": {"zh_cn": "剩余", "zh_tw": "剩餘", "ja": "残数", "ko": "잔여", "en": "Left"},
    "booking": {"zh_cn": "预订", "zh_tw": "預訂", "ja": "予約", "ko": "예약", "en": "Booking"},
    "map": {"zh_cn": "地图", "zh_tw": "地圖", "ja": "地図", "ko": "지도", "en": "Map"},
    "reminder_count": {"zh_cn": "提醒次数", "zh_tw": "提醒次數", "ja": "通知回数", "ko": "알림 횟수", "en": "Reminder"},
    "cooldown": {"zh_cn": "冷却", "zh_tw": "冷卻", "ja": "クールダウン", "ko": "쿨다운", "en": "Cooldown"},
    "previous_count": {"zh_cn": "原可用数量", "zh_tw": "原可用數量", "ja": "変更前の空室数", "ko": "이전 가능 수", "en": "Previous Count"},
    "current_count": {"zh_cn": "当前可用数量", "zh_tw": "目前可用數量", "ja": "現在の空室数", "ko": "현재 가능 수", "en": "Current Count"},
    "change": {"zh_cn": "变化", "zh_tw": "變化", "ja": "変化", "ko": "변경", "en": "Change"},
    "status": {"zh_cn": "状态", "zh_tw": "狀態", "ja": "状態", "ko": "상태", "en": "Status"},
    "check": {"zh_cn": "需确认", "zh_tw": "需確認", "ja": "要確認", "ko": "확인 필요", "en": "Check"},
    "room_type_unknown": {"zh_cn": "房型", "zh_tw": "房型", "ja": "部屋タイプ", "ko": "객실 타입", "en": "Room Type"},
    "hotel_name_unknown": {"zh_cn": "酒店名未知", "zh_tw": "飯店名未知", "ja": "ホテル名不明", "ko": "호텔명 알 수 없음", "en": "hotel name unknown"},
    "all_unspecified": {"zh_cn": "全部/未指定", "zh_tw": "全部/未指定", "ja": "すべて/未指定", "ko": "전체/미지정", "en": "All/Unspecified"},
    "preferred": {"zh_cn": "优先", "zh_tw": "優先", "ja": "優先", "ko": "우선", "en": "preferred"},
    "guest_unit": {"zh_cn": "人", "zh_tw": "人", "ja": "名", "ko": "명", "en": "guest(s)"},
    "room_unit": {"zh_cn": "间", "zh_tw": "間", "ja": "室", "ko": "실", "en": "room(s)"},
    "worker_lines": {"zh_cn": "条线路", "zh_tw": "條線路", "ja": "ライン", "ko": "개 라인", "en": "lines"},
    "off": {"zh_cn": "关闭", "zh_tw": "關閉", "ja": "オフ", "ko": "꺼짐", "en": "OFF"},
    "none": {"zh_cn": "无", "zh_tw": "無", "ja": "なし", "ko": "없음", "en": "none"},
}


def _push_label(cfg: AppConfig, key: str) -> str:
    lang = _normalize_primary_language(getattr(cfg, "primary_language", DEFAULT_PRIMARY_LANGUAGE))
    data = PUSH_I18N.get(key, {})
    return data.get(lang) or data.get("en") or data.get("zh_cn") or key


def _push_title(cfg: AppConfig, icon: str, key: str) -> str:
    return f"{icon} {_push_label(cfg, key)}"


def _primary_or_english(cfg: AppConfig, primary: Optional[str], english: Optional[str]) -> str:
    lang = _normalize_primary_language(getattr(cfg, "primary_language", DEFAULT_PRIMARY_LANGUAGE))
    if lang == "en":
        return str(english or primary or "")
    return str(primary or english or "")


def _display_hotel_codes(cfg: AppConfig) -> str:
    selected = {
        str(hotel.get("code") or ""): str(hotel.get("display_code") or hotel.get("code") or "")
        for hotel in (getattr(cfg, "selected_hotels", []) or [])
    }
    values = [selected.get(str(code), str(code)) for code in (cfg.hotel_codes or [])]
    return ", ".join(values) if values else f"({_push_label(cfg, 'none')})"


def send_start_notifications(cfg: AppConfig) -> None:
    try:
        notify_enabled = bool(getattr(cfg, "notify_start", True))
        codes = _display_hotel_codes(cfg)
        area = _format_area_for_push(cfg)
        parallel = (
            f"{getattr(cfg, 'smart_parallel_workers', DEFAULT_SMART_PARALLEL_WORKERS)} {_push_label(cfg, 'worker_lines')}"
            if getattr(cfg, "smart_parallel_enabled", False)
            else _push_label(cfg, "off")
        )
        summary_lines = [
            _push_title(cfg, "🟢", "tracking_started"),
            f"{_push_label(cfg, 'time')}: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"{_push_label(cfg, 'dates')}: {cfg.start_date} → {cfg.end_date}",
            f"{_push_label(cfg, 'area')}: {area}",
            f"{_push_label(cfg, 'guests_rooms')}: {cfg.people} {_push_label(cfg, 'guest_unit')} / {cfg.rooms} {_push_label(cfg, 'room_unit')}",
            f"{_push_label(cfg, 'smoking_pref')}: {_smoking_preference_label(getattr(cfg, 'smoking', DEFAULT_SMOKING), cfg)}",
            f"{_push_label(cfg, 'room_type_pref')}: {_room_requirement_label(getattr(cfg, 'om_requirement', DEFAULT_ROOM_REQUIREMENT), cfg)}",
            f"{_push_label(cfg, 'membership')}: {_membership_label(getattr(cfg, 'membership_status', DEFAULT_MEMBERSHIP_STATUS), cfg)}",
            f"{_push_label(cfg, 'engine')}: {getattr(cfg, 'engine', DEFAULT_ENGINE)} | {_push_label(cfg, 'smart_parallel')}: {parallel}",
            f"{_push_label(cfg, 'hotels')} ({len(cfg.hotel_codes)}): {codes}",
        ]
        msg = "\n".join(summary_lines)
        title = _push_title(cfg, "🟢", "tracking_started")
        _publish_and_notify(
            cfg, "search.started", f"start|{cfg.start_date}|{cfg.end_date}|{codes}",
            title, msg, enabled=notify_enabled, dedupe_window_seconds=2,
            payload={"hotel_count": len(cfg.hotel_codes)},
        )
        _log("[start] event recorded" + (" and sent to enabled channels" if notify_enabled else ""))
    except Exception as e:
        _log(f"[start] start notifications error: {e}")


def send_stop_notifications(cfg: AppConfig) -> None:
    try:
        notify_enabled = bool(getattr(cfg, "notify_stop", True))
        title = _push_title(cfg, "⏹️", "tracking_stopped")
        lines = [
            title,
            f"{_push_label(cfg, 'time')}: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"{_push_label(cfg, 'dates')}: {cfg.start_date} → {cfg.end_date}",
            f"{_push_label(cfg, 'area')}: {_format_area_for_push(cfg)}",
            f"{_push_label(cfg, 'hotels')} ({len(cfg.hotel_codes)}): {_display_hotel_codes(cfg)}",
        ]
        _publish_and_notify(
            cfg, "search.stopped",
            f"stop|{cfg.start_date}|{cfg.end_date}|{_display_hotel_codes(cfg)}",
            title, "\n".join(lines), enabled=notify_enabled, dedupe_window_seconds=2,
            payload={"hotel_count": len(cfg.hotel_codes)},
        )
        _log("[stop] event recorded" + (" and sent to enabled channels" if notify_enabled else ""))
    except Exception as e:
        _log(f"[stop] stop notifications error: {e}")


def _format_area_for_push(cfg: AppConfig) -> str:
    parts = []
    for value in (getattr(cfg, "area_region_label", ""), getattr(cfg, "area_detail_label", "")):
        value = str(value or "").strip()
        if value:
            parts.append(value)
    return " > ".join(parts) if parts else _push_label(cfg, "all_unspecified")


def _membership_label(value: str, cfg: Optional[AppConfig] = None) -> str:
    lang = _normalize_primary_language(getattr(cfg, "primary_language", DEFAULT_PRIMARY_LANGUAGE)) if cfg else DEFAULT_PRIMARY_LANGUAGE
    labels = {
        "member": {"zh_cn": "会员", "zh_tw": "會員", "ja": "会員", "ko": "회원", "en": "Member"},
        "non_member": {"zh_cn": "非会员", "zh_tw": "非會員", "ja": "非会員", "ko": "비회원", "en": "Non-member"},
        "unknown": {"zh_cn": "未知/同时显示", "zh_tw": "未知/同時顯示", "ja": "不明/両方表示", "ko": "알 수 없음/둘 다 표시", "en": "Unknown/Both"},
    }
    item = labels.get(value, labels["unknown"])
    return item.get(lang, item["en"])


def _smoking_preference_label(value: str, cfg: Optional[AppConfig] = None) -> str:
    lang = _normalize_primary_language(getattr(cfg, "primary_language", DEFAULT_PRIMARY_LANGUAGE)) if cfg else DEFAULT_PRIMARY_LANGUAGE
    labels = {
        "noSmoking": {"zh_cn": "禁烟", "zh_tw": "禁菸", "ja": "禁煙", "ko": "금연", "en": "Non-Smoking"},
        "Smoking": {"zh_cn": "吸烟", "zh_tw": "吸菸", "ja": "喫煙", "ko": "흡연", "en": "Smoking"},
        "all": {"zh_cn": "不限制", "zh_tw": "不限制", "ja": "指定なし", "ko": "제한 없음", "en": "Any"},
    }
    item = labels.get(value, labels["all"])
    return item.get(lang, item["en"])


def _room_requirement_label(value: str, cfg: Optional[AppConfig] = None) -> str:
    lang = _normalize_primary_language(getattr(cfg, "primary_language", DEFAULT_PRIMARY_LANGUAGE)) if cfg else DEFAULT_PRIMARY_LANGUAGE
    labels = {
        "any": {"zh_cn": "不限制", "zh_tw": "不限制", "ja": "指定なし", "ko": "제한 없음", "en": "Any"},
        "single": {"zh_cn": "单人房", "zh_tw": "單人房", "ja": "シングル", "ko": "싱글", "en": "Single"},
        "double": {"zh_cn": "大床房", "zh_tw": "雙人床房", "ja": "ダブル", "ko": "더블", "en": "Double"},
        "twin": {"zh_cn": "双床房", "zh_tw": "雙床房", "ja": "ツイン", "ko": "트윈", "en": "Twin"},
    }
    item = labels.get((value or "any").lower())
    if not item:
        return str(value or "any")
    return item.get(lang, item["en"])


def _room_smoking_label(value: Optional[str], cfg: Optional[AppConfig] = None) -> str:
    lang = _normalize_primary_language(getattr(cfg, "primary_language", DEFAULT_PRIMARY_LANGUAGE)) if cfg else DEFAULT_PRIMARY_LANGUAGE
    labels = {
        "smoking": {"zh_cn": "吸烟", "zh_tw": "吸菸", "ja": "喫煙", "ko": "흡연", "en": "Smoking"},
        "non_smoking": {"zh_cn": "禁烟", "zh_tw": "禁菸", "ja": "禁煙", "ko": "금연", "en": "Non-Smoking"},
        "unknown": {"zh_cn": "吸烟信息未知", "zh_tw": "吸菸資訊未知", "ja": "喫煙情報不明", "ko": "흡연 정보 알 수 없음", "en": "Smoking unknown"},
    }
    icon = "🚬" if value == "smoking" else "🚭" if value == "non_smoking" else ""
    item = labels.get(value or "unknown", labels["unknown"])
    return f"{icon} {item.get(lang, item['en'])}".strip()


def _legacy_membership_label(value: str) -> str:
    if value == "member":
        return "会员 / Member"
    if value == "non_member":
        return "非会员 / Non-member"
    return "未知/同时显示 / Unknown/Both"


def _legacy_smoking_preference_label(value: str) -> str:
    if value == "noSmoking":
        return "禁烟 / Non-Smoking"
    if value == "Smoking":
        return "吸烟 / Smoking"
    return "不限制 / Any"


def _legacy_room_requirement_label(value: str) -> str:
    labels = {
        "any": "不限制 / Any",
        "single": "单人房 / Single",
        "double": "大床房 / Double",
        "twin": "双床房 / Twin",
    }
    return labels.get((value or "any").lower(), str(value or "any"))


def _legacy_room_smoking_label(value: Optional[str]) -> str:
    if value == "smoking":
        return "🚬 吸烟 / Smoking"
    if value == "non_smoking":
        return "🚭 禁烟 / Non-Smoking"
    return "吸烟信息未知 / Smoking unknown"


def _selected_hotel_info(cfg: AppConfig, code: str) -> Dict[str, Any]:
    for hotel in getattr(cfg, "selected_hotels", []) or []:
        if str(hotel.get("code", "")) == str(code):
            return hotel
    return {}


def _price_lines_for_push(cfg: AppConfig, non_member: Optional[str], member: Optional[str]) -> List[str]:
    membership = getattr(cfg, "membership_status", DEFAULT_MEMBERSHIP_STATUS)
    lines: List[str] = []
    if membership == "member":
        lines.append(f"   {_push_label(cfg, 'display_price')}: {member or non_member or '-'} ({_push_label(cfg, 'member_price')} {_push_label(cfg, 'preferred')})")
    elif membership == "non_member":
        lines.append(f"   {_push_label(cfg, 'display_price')}: {non_member or '-'} ({_push_label(cfg, 'non_member_price')})")
    else:
        lines.append(f"   {_push_label(cfg, 'display_price')}: {member or non_member or '-'} ({_membership_label('unknown', cfg)})")
    lines.append(f"   {_push_label(cfg, 'member_price')}: {member or '-'}")
    lines.append(f"   {_push_label(cfg, 'non_member_price')}: {non_member or '-'}")
    return lines


def _format_offer_lines_for_push(cfg: AppConfig, r: HotelResult) -> List[str]:
    """
    Build multi-offer lines for notifications. Prefer r.offers_display (already filtered by budget/room requirement),
    fall back to single-offer fields if necessary.
    """
    lines: List[str] = []

    # Use all qualifying offers when present
    offers = getattr(r, "offers_display", None)
    if isinstance(offers, list) and offers:
        for idx, o in enumerate(offers, 1):
            room_en = o.get("room_title") or "-"
            room_zh = o.get("room_title_primary") or o.get("room_title_zh") or _room_title_primary(room_en, getattr(cfg, "primary_language", DEFAULT_PRIMARY_LANGUAGE)) or _push_label(cfg, "room_type_unknown")
            smoking = _room_smoking_label(o.get("room_smoking"), cfg)
            left = o.get("remaining_norm") or "-"
            lines.append(f"{idx}. {_primary_or_english(cfg, room_zh, room_en)} | {smoking}")
            lines.extend(_price_lines_for_push(cfg, o.get("price_text"), o.get("member_price_text")))
            lines.append(f"   {_push_label(cfg, 'left')}: {left}")
        return lines
    # Fallback to single fields (legacy)
    room_en = r.min_price_room or "-"
    room_zh = _room_title_primary(room_en, getattr(cfg, "primary_language", DEFAULT_PRIMARY_LANGUAGE)) or (_push_label(cfg, "room_type_unknown") if room_en != "-" else "-")
    left = r.min_remaining or "-"
    lines.append(f"1. {_primary_or_english(cfg, room_zh, room_en)}")
    lines.extend(_price_lines_for_push(cfg, r.min_price_text, r.min_member_price_text))
    lines.append(f"   {_push_label(cfg, 'left')}: {left}")
    return lines


def _remaining_to_count(value: Any) -> int:
    text = str(value or "").strip()
    if not text:
        return 0
    if text.startswith("≥") or text.startswith(">="):
        digits = "".join(ch for ch in text if ch.isdigit())
        return int(digits or "10")
    try:
        return max(0, int(text))
    except Exception:
        return 0


def _available_room_count(r: HotelResult) -> int:
    offers = getattr(r, "offers_display", None)
    if isinstance(offers, list) and offers:
        total = sum(_remaining_to_count(o.get("remaining_norm")) for o in offers)
        return total if total > 0 else 1
    count = _remaining_to_count(getattr(r, "min_remaining", None))
    if count > 0:
        return count
    return 1 if getattr(r, "available", False) else 0


def _log_room_summary(cfg: AppConfig, r: HotelResult) -> tuple[str, str, str]:
    offers = getattr(r, "offers_display", None)
    if isinstance(offers, list) and offers:
        parts = []
        prices = []
        for o in offers[:3]:
            room_en = o.get("room_title") or "-"
            room_primary = o.get("room_title_primary") or _room_title_primary(room_en, getattr(cfg, "primary_language", DEFAULT_PRIMARY_LANGUAGE)) or ""
            parts.append(_primary_or_english(cfg, room_primary, room_en))
            price = o.get("member_price_text") or o.get("price_text") or "-"
            prices.append(price)
        suffix = "..." if len(offers) > 3 else ""
        return " / ".join(prices) + suffix, " | ".join(parts) + suffix, parts[0] if parts else "-"
    room_en = r.min_price_room or "-"
    room_primary = _room_title_primary(room_en, getattr(cfg, "primary_language", DEFAULT_PRIMARY_LANGUAGE)) or ""
    room = _primary_or_english(cfg, room_primary, room_en)
    return r.min_member_price_text or r.min_price_text or "-", room, room


def _hotel_name_for_log(cfg: AppConfig, r: HotelResult) -> str:
    selected = _selected_hotel_info(cfg, r.code)
    primary = r.name_primary or selected.get("name_primary") or selected.get("name_zh") or r.name_zh or r.name or f"({_push_label(cfg, 'hotel_name_unknown')})"
    english = r.name_en or selected.get("name_en") or r.name or "(hotel name unknown)"
    return _primary_or_english(cfg, primary, english)


def _upsert_availability_log(cfg: AppConfig, r: HotelResult, start_date: str, end_date: str, key: str, now: float, count: int) -> None:
    global _AVAILABILITY_LOG_REVISION
    price, room, _room_primary = _log_room_summary(cfg, r)
    with _ALERT_STATE_LOCK:
        for entry in reversed(_AVAILABILITY_LOGS):
            if entry.get("key") == key and entry.get("disappeared_ts") is None:
                entry.update({
                    "hotel": _hotel_name_for_log(cfg, r),
                    "price": price,
                    "room_type": room,
                    "count": count,
                    "updated_ts": now,
                })
                _AVAILABILITY_LOG_REVISION += 1
                return
        _AVAILABILITY_LOGS.append({
            "key": key,
            "task_id": str(getattr(cfg, "task_id", "") or "") or None,
            "code": r.display_code or _selected_hotel_info(cfg, r.code).get("display_code") or r.code,
            "hotel": _hotel_name_for_log(cfg, r),
            "appeared_ts": now,
            "appeared_at": datetime.fromtimestamp(now).strftime("%Y-%m-%d %H:%M:%S"),
            "disappeared_ts": None,
            "disappeared_at": "",
            "duration_sec": None,
            "price": price,
            "room_type": room,
            "count": count,
            "start_date": start_date,
            "end_date": end_date,
            "url": r.url,
        })
        del _AVAILABILITY_LOGS[:-100]
        _AVAILABILITY_LOG_REVISION += 1


def _close_availability_log(key: str, now: float) -> None:
    global _AVAILABILITY_LOG_REVISION
    with _ALERT_STATE_LOCK:
        for entry in reversed(_AVAILABILITY_LOGS):
            if entry.get("key") == key and entry.get("disappeared_ts") is None:
                entry["disappeared_ts"] = now
                entry["disappeared_at"] = datetime.fromtimestamp(now).strftime("%Y-%m-%d %H:%M:%S")
                entry["duration_sec"] = max(
                    0, int(now - float(entry.get("appeared_ts") or now))
                )
                _AVAILABILITY_LOG_REVISION += 1
                return


def _build_result_push_message(
    cfg: AppConfig,
    r: HotelResult,
    start_date: str,
    end_date: str,
    heading_zh: str,
    heading_en: str,
    extra_lines: Optional[List[str]] = None,
) -> str:
    selected = _selected_hotel_info(cfg, r.code)
    name_zh = r.name_primary or selected.get("name_primary") or selected.get("name_zh") or r.name_zh or r.name or f"({_push_label(cfg, 'hotel_name_unknown')})"
    name_en = r.name_en or selected.get("name_en") or r.name or "(hotel name unknown)"
    map_url = selected.get("map_url") or ""
    heading = _primary_or_english(cfg, heading_zh, heading_en or heading_zh)
    hotel_name = _primary_or_english(cfg, name_zh, name_en)
    lines = [
        heading,
        f"{_push_label(cfg, 'time')}: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"{_push_label(cfg, 'hotel_code')}: {r.display_code or selected.get('display_code') or r.code}",
        f"{_push_label(cfg, 'hotel')}: {hotel_name}",
        f"{_push_label(cfg, 'area')}: {_format_area_for_push(cfg)}",
        f"{_push_label(cfg, 'dates')}: {start_date} → {end_date}",
        f"{_push_label(cfg, 'guests_rooms')}: {cfg.people} {_push_label(cfg, 'guest_unit')} / {cfg.rooms} {_push_label(cfg, 'room_unit')}",
        f"{_push_label(cfg, 'smoking_pref')}: {_smoking_preference_label(getattr(cfg, 'smoking', DEFAULT_SMOKING), cfg)}",
        f"{_push_label(cfg, 'room_type_pref')}: {_room_requirement_label(getattr(cfg, 'om_requirement', DEFAULT_ROOM_REQUIREMENT), cfg)}",
        f"{_push_label(cfg, 'membership')}: {_membership_label(getattr(cfg, 'membership_status', DEFAULT_MEMBERSHIP_STATUS), cfg)}",
    ]
    if extra_lines:
        lines.extend(extra_lines)
    if r.available:
        lines.append("")
        lines.append(f"{_push_label(cfg, 'rooms_prices')}:")
        lines.extend(_format_offer_lines_for_push(cfg, r))
    lines.append("")
    lines.append(f"{_push_label(cfg, 'booking')}: {r.url}")
    if map_url:
        lines.append(f"{_push_label(cfg, 'map')}: {map_url}")
    return "\n".join([x for x in lines if x is not None])

def process_notifications(cfg: AppConfig, results: List[HotelResult], start_date: str, end_date: str) -> List[str]:
    newly_available: List[str] = []
    task_scope = str(getattr(cfg, "task_id", "") or "")
    for r in results:
        # A TTL cache hit keeps the UI responsive, but only live or conditionally
        # revalidated data is allowed to advance alert state.
        if getattr(r, "from_cache", False) and not getattr(r, "cache_validated", False):
            continue
        if getattr(r, "requirement_unmet", False):
            continue
        key_prefix = f"{task_scope}|" if task_scope else ""
        key = f"{key_prefix}{r.code}|{start_date}|{end_date}"
        st = _alert_state_snapshot(key)
        was_available = bool(st.get("available", False))
        is_available = bool(r.available)
        previous_count = int(st.get("count", 0) or 0)
        current_count = _available_room_count(r) if is_available else 0
        now = time.time()

        if is_available and not was_available:
            newly_available.append(r.code)
            _upsert_availability_log(cfg, r, start_date, end_date, key, now, current_count)
            title = _push_title(cfg, "✅", "room_available")
            msg = _build_result_push_message(
                cfg,
                r,
                start_date,
                end_date,
                title,
                "",
            )
            notify_enabled = bool(getattr(cfg, "notify_available", True))
            _publish_and_notify(
                cfg, "availability.available", f"{key}|available", title, msg, r.url,
                enabled=notify_enabled,
                payload={
                    "task_id": task_scope or None,
                    "code": r.code,
                    "count": current_count,
                    "provider": r.provider,
                },
            )
            st = {
                "available": True, "sent": 1 if notify_enabled else 0,
                "last": now, "count": current_count,
            }

        elif is_available and was_available:
            _upsert_availability_log(cfg, r, start_date, end_date, key, now, current_count)
            if current_count != previous_count and previous_count > 0:
                delta = current_count - previous_count
                title = _push_title(cfg, "🔢", "room_count_changed")
                msg = _build_result_push_message(
                    cfg,
                    r,
                    start_date,
                    end_date,
                    title,
                    "",
                    [
                        f"{_push_label(cfg, 'previous_count')}: {previous_count}",
                        f"{_push_label(cfg, 'current_count')}: {current_count}",
                        f"{_push_label(cfg, 'change')}: {'+' if delta > 0 else ''}{delta}",
                    ],
                )
                _publish_and_notify(
                    cfg, "availability.count_changed",
                    f"{key}|count|{previous_count}|{current_count}",
                    title, msg, r.url,
                    enabled=bool(getattr(cfg, "notify_availability_count_change", True)),
                    payload={
                        "task_id": task_scope or None,
                        "code": r.code, "previous_count": previous_count,
                        "current_count": current_count, "provider": r.provider,
                    },
                )
            if not getattr(cfg, "notify_available", True):
                st["available"] = True
                st["count"] = current_count
                _set_alert_state(key, st)
                continue
            repeat_limit = max(0, min(11, int(cfg.available_alert_repeat)))
            if repeat_limit <= 0:
                st["available"] = True
                st["count"] = current_count
                _set_alert_state(key, st)
                continue
            interval = max(60, int(cfg.available_alert_repeat_interval_sec))
            sent = int(st.get("sent", 0) or 0)
            reminders_sent = max(0, sent - 1)
            repeat_forever = repeat_limit >= 11
            last_sent = float(st.get("last", 0) or 0)
            elapsed = now - last_sent
            if elapsed < -_MAX_CLOCK_SKEW_SECONDS:
                # A restored checkpoint from a clock that was far ahead must
                # not postpone reminders until that wall-clock time returns.
                st["last"] = now
                elapsed = 0
            if (repeat_forever or reminders_sent < repeat_limit) and elapsed >= interval:
                next_reminder = reminders_sent + 1
                limit_text = "INF" if repeat_forever else str(repeat_limit)
                title = _push_title(cfg, "🔁", "room_reminder")
                msg = _build_result_push_message(
                    cfg,
                    r,
                    start_date,
                    end_date,
                    title,
                    "",
                    [f"{_push_label(cfg, 'reminder_count')}: {next_reminder}/{limit_text}", f"{_push_label(cfg, 'cooldown')}: {interval}s"],
                )
                _publish_and_notify(
                    cfg, "availability.reminder",
                    f"{key}|reminder|{next_reminder}", title, msg, r.url,
                    payload={
                        "task_id": task_scope or None,
                        "code": r.code,
                        "reminder": next_reminder,
                        "provider": r.provider,
                    },
                )
                st["sent"] = sent + 1
                st["last"] = now

        elif r.available is False and was_available:
            _close_availability_log(key, now)
            title = _push_title(cfg, "❌", "no_longer_available")
            msg = _build_result_push_message(
                cfg,
                r,
                start_date,
                end_date,
                title,
                "",
            )
            _publish_and_notify(
                cfg, "availability.unavailable", f"{key}|unavailable",
                title, msg, r.url,
                enabled=bool(getattr(cfg, "notify_unavailable", True)),
                payload={
                    "task_id": task_scope or None,
                    "code": r.code,
                    "provider": r.provider,
                },
            )
            st = {"available": False, "sent": 0, "last": now, "count": 0}

        elif r.available is None:
            title = _push_title(cfg, "❓", "search_check_required")
            msg = _build_result_push_message(
                cfg,
                r,
                start_date,
                end_date,
                title,
                "",
                [f"{_push_label(cfg, 'status')}: ❓ {_push_label(cfg, 'check')}"],
            )
            _publish_and_notify(
                cfg, "search.hotel_error",
                f"{key}|error|{r.http_status or ''}|{r.error_summary or ''}",
                title, msg, r.url,
                enabled=bool(getattr(cfg, "notify_search_error", False)),
                dedupe_window_seconds=300,
                payload={
                    "task_id": task_scope or None,
                    "code": r.code, "provider": r.provider,
                    "http_status": r.http_status, "error": r.error_summary,
                },
            )

        if r.available is not None:
            st["available"] = is_available
            st["count"] = current_count
            _set_alert_state(key, st)
    return newly_available
