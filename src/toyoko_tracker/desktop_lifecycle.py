"""Desktop lifecycle, notification deep-link, badge, and recovery support."""

from __future__ import annotations

import json
import os
import shlex
import socket
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Optional
from urllib.parse import parse_qs, urlencode, urlparse

from .settings import (
    APP_NAME,
    DESKTOP_DEEP_LINK_INBOX_PATH,
    DESKTOP_PREFERENCES_PATH,
    DESKTOP_STATE_PATH,
    INSTANCE_STATE_PATH,
)


DEEP_LINK_SCHEME = "toyoko-tracker"
DEEP_LINK_HOST = "open"
SUPPORTED_VIEWS = {
    "home",
    "search",
    "tasks",
    "monitor",
    "price",
    "travel",
    "search-settings",
    "push-settings",
    "interface",
}
DEFAULT_PREFERENCES: Dict[str, bool] = {
    "close_to_background": True,
    "launch_at_login": False,
    "badge_enabled": True,
    "recovery_enabled": True,
}
_STATE_DEFAULTS: Dict[str, Any] = {
    "unread_count": 0,
    "last_deep_link": "",
    "last_notification_at": 0.0,
    "recent_notification_keys": [],
    "recovery_count": 0,
    "last_recovery_at": 0.0,
    "last_recovery_reason": "",
}
_FILE_LOCK = threading.RLock()
_CONTROLLER_LOCK = threading.RLock()
_ACTIVE_CONTROLLER: Optional["DesktopLifecycleController"] = None


def _read_json(path: str, fallback: Dict[str, Any]) -> Dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as stream:
            value = json.load(stream)
        return value if isinstance(value, dict) else dict(fallback)
    except (OSError, ValueError, TypeError):
        return dict(fallback)


def _atomic_write_json(path: str, value: Dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + f".{os.getpid()}.tmp")
    with open(temporary, "w", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.write("\n")
    os.replace(temporary, target)


def load_preferences() -> Dict[str, bool]:
    with _FILE_LOCK:
        stored = _read_json(DESKTOP_PREFERENCES_PATH, DEFAULT_PREFERENCES)
    return {
        key: bool(stored.get(key, default))
        for key, default in DEFAULT_PREFERENCES.items()
    }


def update_preferences(patch: Dict[str, Any]) -> Dict[str, bool]:
    supported = {
        key: bool(value)
        for key, value in patch.items()
        if key in DEFAULT_PREFERENCES
    }
    with _FILE_LOCK:
        preferences = load_preferences()
        preferences.update(supported)
        _atomic_write_json(DESKTOP_PREFERENCES_PATH, preferences)
    return preferences


def _load_state() -> Dict[str, Any]:
    with _FILE_LOCK:
        state = _read_json(DESKTOP_STATE_PATH, _STATE_DEFAULTS)
    merged = dict(_STATE_DEFAULTS)
    merged.update(state)
    merged["unread_count"] = max(0, int(merged.get("unread_count") or 0))
    merged["recent_notification_keys"] = list(
        merged.get("recent_notification_keys") or []
    )[-128:]
    return merged


def _save_state(state: Dict[str, Any]) -> None:
    with _FILE_LOCK:
        _atomic_write_json(DESKTOP_STATE_PATH, state)


def build_deep_link(
    *,
    view: str = "monitor",
    task_id: str = "",
    hotel_code: str = "",
    stay_date: str = "",
    event_id: str = "",
) -> str:
    selected_view = view if view in SUPPORTED_VIEWS else "monitor"
    query = {
        key: str(value)
        for key, value in {
            "view": selected_view,
            "task_id": task_id,
            "hotel_code": hotel_code,
            "stay_date": stay_date,
            "event_id": event_id,
        }.items()
        if str(value or "").strip()
    }
    return f"{DEEP_LINK_SCHEME}://{DEEP_LINK_HOST}?{urlencode(query)}"


def parse_deep_link(value: str) -> Dict[str, str]:
    parsed = urlparse(str(value or "").strip())
    if parsed.scheme != DEEP_LINK_SCHEME or parsed.netloc != DEEP_LINK_HOST:
        raise ValueError("invalid Toyoko Tracker desktop deep link")
    query = parse_qs(parsed.query, keep_blank_values=False)
    view = str((query.get("view") or ["monitor"])[0])
    if view not in SUPPORTED_VIEWS:
        view = "monitor"
    def field(name: str, limit: int) -> str:
        return str((query.get(name) or [""])[0])[:limit]

    return {
        "view": view,
        "task_id": field("task_id", 120),
        "hotel_code": field("hotel_code", 120),
        "stay_date": field("stay_date", 10),
        "event_id": field("event_id", 120),
    }


def deep_link_to_local_url(base_url: str, value: str) -> str:
    payload = parse_deep_link(value)
    query = urlencode({key: val for key, val in payload.items() if val})
    return f"{str(base_url).rstrip('/')}/?{query}"


def is_desktop_frontend() -> bool:
    return bool(
        getattr(sys, "frozen", False)
        or os.environ.get("TOYOKO_TRACKER_FRONTEND") == "desktop"
    )


def record_desktop_notification(
    title: str,
    body: str,
    deep_link: str,
    *,
    dedupe_key: str = "",
) -> Dict[str, Any]:
    if not is_desktop_frontend():
        return desktop_status()
    with _FILE_LOCK:
        state = _load_state()
        keys = list(state.get("recent_notification_keys") or [])
        key = str(dedupe_key or deep_link or f"{title}|{body}")
        if key and key not in keys:
            state["unread_count"] = int(state.get("unread_count") or 0) + 1
            keys.append(key)
        state["recent_notification_keys"] = keys[-128:]
        state["last_deep_link"] = str(deep_link or "")
        state["last_notification_at"] = time.time()
        _save_state(state)
    controller = active_controller()
    if controller is not None:
        controller.notification_received(title, body, deep_link)
    return desktop_status()


def mark_desktop_notifications_read() -> Dict[str, Any]:
    with _FILE_LOCK:
        state = _load_state()
        state["unread_count"] = 0
        _save_state(state)
    controller = active_controller()
    if controller is not None:
        controller.refresh_badge()
    return desktop_status()


def queue_deep_link(value: str) -> bool:
    parse_deep_link(value)
    with _FILE_LOCK:
        inbox = _read_json(DESKTOP_DEEP_LINK_INBOX_PATH, {"links": []})
        links = list(inbox.get("links") or [])
        links.append({"url": value, "queued_at": time.time()})
        _atomic_write_json(DESKTOP_DEEP_LINK_INBOX_PATH, {"links": links[-32:]})
    return True


def pop_deep_links() -> list[str]:
    with _FILE_LOCK:
        inbox = _read_json(DESKTOP_DEEP_LINK_INBOX_PATH, {"links": []})
        links = [
            str(item.get("url") or "")
            for item in list(inbox.get("links") or [])
            if isinstance(item, dict) and item.get("url")
        ]
        if links:
            _atomic_write_json(DESKTOP_DEEP_LINK_INBOX_PATH, {"links": []})
    return links


def _pid_is_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def forward_deep_link_to_running(value: str) -> bool:
    try:
        with open(INSTANCE_STATE_PATH, "r", encoding="utf-8") as stream:
            state = json.load(stream)
        pid = int(state.get("pid") or 0)
    except (OSError, ValueError, TypeError):
        return False
    if (
        str(state.get("frontend") or "") != "desktop"
        or pid == os.getpid()
        or not _pid_is_alive(pid)
    ):
        return False
    queue_deep_link(value)
    return True


def _launch_command() -> list[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable, "--background"]
    return [sys.executable, "-m", "toyoko_tracker.desktop", "--background"]


def _deep_link_command() -> list[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable]
    return [sys.executable, "-m", "toyoko_tracker.desktop"]


def _mac_launch_agent_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / "com.jellyneko.toyoko-tracker.plist"


def _linux_autostart_path() -> Path:
    root = Path(os.environ.get("XDG_CONFIG_HOME") or (Path.home() / ".config"))
    return root / "autostart" / "toyoko-tracker.desktop"


def autostart_status() -> Dict[str, Any]:
    enabled = False
    method = "unsupported"
    try:
        if sys.platform == "darwin":
            enabled = _mac_launch_agent_path().exists()
            method = "launch-agent"
        elif sys.platform.startswith("linux"):
            enabled = _linux_autostart_path().exists()
            method = "xdg-autostart"
        elif os.name == "nt":
            import winreg

            method = "registry-run"
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
            ) as key:
                winreg.QueryValueEx(key, "ToyokoTracker")
            enabled = True
    except (OSError, ImportError):
        enabled = False
    return {"enabled": enabled, "method": method}


def set_autostart(enabled: bool) -> Dict[str, Any]:
    command = _launch_command()
    if sys.platform == "darwin":
        path = _mac_launch_agent_path()
        if enabled:
            path.parent.mkdir(parents=True, exist_ok=True)
            arguments = "".join(f"<string>{_xml_escape(item)}</string>" for item in command)
            path.write_text(
                "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
                "<!DOCTYPE plist PUBLIC \"-//Apple//DTD PLIST 1.0//EN\" "
                "\"http://www.apple.com/DTDs/PropertyList-1.0.dtd\">\n"
                "<plist version=\"1.0\"><dict>"
                "<key>Label</key><string>com.jellyneko.toyoko-tracker</string>"
                f"<key>ProgramArguments</key><array>{arguments}</array>"
                "<key>RunAtLoad</key><true/>"
                "</dict></plist>\n",
                encoding="utf-8",
            )
        else:
            path.unlink(missing_ok=True)
    elif sys.platform.startswith("linux"):
        path = _linux_autostart_path()
        if enabled:
            path.parent.mkdir(parents=True, exist_ok=True)
            escaped = " ".join(shlex.quote(item) for item in command)
            path.write_text(
                "[Desktop Entry]\n"
                "Type=Application\n"
                f"Name={APP_NAME}\n"
                f"Exec={escaped}\n"
                "Terminal=false\n"
                "X-GNOME-Autostart-enabled=true\n",
                encoding="utf-8",
            )
        else:
            path.unlink(missing_ok=True)
    elif os.name == "nt":
        import winreg

        with winreg.CreateKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
        ) as key:
            if enabled:
                winreg.SetValueEx(
                    key,
                    "ToyokoTracker",
                    0,
                    winreg.REG_SZ,
                    subprocess.list2cmdline(command),
                )
            else:
                try:
                    winreg.DeleteValue(key, "ToyokoTracker")
                except FileNotFoundError:
                    pass
    else:
        raise OSError("desktop launch-at-login is unsupported on this platform")
    preferences = update_preferences({"launch_at_login": bool(enabled)})
    return {"preferences": preferences, "autostart": autostart_status()}


def _xml_escape(value: str) -> str:
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def register_deep_link_scheme() -> Dict[str, Any]:
    method = (
        "bundle"
        if sys.platform == "darwin" and getattr(sys, "frozen", False)
        else "source-session"
        if sys.platform == "darwin"
        else "unsupported"
    )
    registered = sys.platform == "darwin" and bool(getattr(sys, "frozen", False))
    try:
        if sys.platform.startswith("linux"):
            command = _deep_link_command()
            applications = Path.home() / ".local" / "share" / "applications"
            desktop_file = applications / "toyoko-tracker.desktop"
            applications.mkdir(parents=True, exist_ok=True)
            desktop_file.write_text(
                "[Desktop Entry]\n"
                "Type=Application\n"
                f"Name={APP_NAME}\n"
                f"Exec={' '.join(shlex.quote(item) for item in command)} %u\n"
                "Icon=toyoko-tracker\n"
                "Terminal=false\n"
                "Categories=Network;Utility;\n"
                f"MimeType=x-scheme-handler/{DEEP_LINK_SCHEME};\n",
                encoding="utf-8",
            )
            xdg_mime = _which("xdg-mime")
            if xdg_mime:
                subprocess.run(
                    [
                        xdg_mime,
                        "default",
                        desktop_file.name,
                        f"x-scheme-handler/{DEEP_LINK_SCHEME}",
                    ],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=5,
                    check=False,
                )
            method = "xdg-mime"
            registered = True
        elif os.name == "nt":
            import winreg

            root = rf"Software\Classes\{DEEP_LINK_SCHEME}"
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, root) as key:
                winreg.SetValueEx(key, "", 0, winreg.REG_SZ, f"URL:{APP_NAME}")
                winreg.SetValueEx(key, "URL Protocol", 0, winreg.REG_SZ, "")
            with winreg.CreateKey(
                winreg.HKEY_CURRENT_USER, root + r"\shell\open\command"
            ) as key:
                command = subprocess.list2cmdline([*_deep_link_command(), "%1"])
                winreg.SetValueEx(key, "", 0, winreg.REG_SZ, command)
            method = "registry-url-protocol"
            registered = True
    except (OSError, ImportError, subprocess.SubprocessError):
        registered = False
    return {"registered": registered, "method": method}


def _which(name: str) -> Optional[str]:
    from shutil import which

    return which(name)


def _online_probe() -> bool:
    try:
        socket.getaddrinfo("www.toyoko-inn.com", 443, type=socket.SOCK_STREAM)
        return True
    except OSError:
        return False


class RecoveryMonitor:
    """Detect resume and network return, then request idempotent service recovery."""

    def __init__(
        self,
        callback: Callable[[str], None],
        *,
        interval: float = 15.0,
        resume_threshold: float = 45.0,
        probe: Callable[[], bool] = _online_probe,
        monotonic: Callable[[], float] = time.monotonic,
        wall_clock: Callable[[], float] = time.time,
    ) -> None:
        self.callback = callback
        self.interval = max(1.0, float(interval))
        self.resume_threshold = max(self.interval * 2, float(resume_threshold))
        self.probe = probe
        self.monotonic = monotonic
        self.wall_clock = wall_clock
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._last_tick = self.monotonic()
        self._last_wall_tick = self.wall_clock()
        self._last_online: Optional[bool] = None

    def check_once(self) -> list[str]:
        reasons: list[str] = []
        now = self.monotonic()
        wall_now = self.wall_clock()
        gap = max(now - self._last_tick, wall_now - self._last_wall_tick)
        self._last_tick = now
        self._last_wall_tick = wall_now
        if gap >= self.resume_threshold:
            reasons.append("resume")
        online = bool(self.probe())
        if self._last_online is False and online:
            reasons.append("network-restored")
        self._last_online = online
        for reason in reasons:
            self.callback(reason)
        return reasons

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._last_tick = self.monotonic()
        self._last_wall_tick = self.wall_clock()
        self._last_online = None
        self._thread = threading.Thread(
            target=self._run,
            name="toyoko-desktop-recovery",
            daemon=True,
        )
        self._thread.start()

    def _run(self) -> None:
        while not self._stop.wait(self.interval):
            try:
                self.check_once()
            except Exception:
                pass

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)


@dataclass
class DesktopCapabilities:
    desktop: bool
    tray: bool
    background: bool
    autostart: bool
    badge: bool
    deep_links: bool
    recovery: bool


class DesktopLifecycleController:
    def __init__(
        self,
        base_url: str,
        *,
        recovery_callback: Optional[Callable[[str], None]] = None,
    ) -> None:
        self.base_url = str(base_url).rstrip("/")
        self.preferences = load_preferences()
        self.window: Any = None
        self.tray: Any = None
        self.quitting = False
        self.visible = True
        self._inbox_stop = threading.Event()
        self._inbox_thread: Optional[threading.Thread] = None
        self._recovery_callback = recovery_callback or (lambda reason: None)
        self.recovery_monitor = RecoveryMonitor(self._recover)
        self.scheme = {"registered": False, "method": "pending"}

    def attach_window(self, window: Any) -> None:
        self.window = window
        self.refresh_badge()

    def attach_tray(self, tray: Any) -> None:
        self.tray = tray
        self.refresh_badge()

    def start(self) -> None:
        set_active_controller(self)
        self.scheme = register_deep_link_scheme()
        if self.preferences.get("recovery_enabled", True):
            self.recovery_monitor.start()
        if self._inbox_thread is None or not self._inbox_thread.is_alive():
            self._inbox_stop.clear()
            self._inbox_thread = threading.Thread(
                target=self._poll_deep_links,
                name="toyoko-desktop-deep-links",
                daemon=True,
            )
            self._inbox_thread.start()

    def stop(self) -> None:
        self.recovery_monitor.stop()
        self._inbox_stop.set()
        if self._inbox_thread is not None:
            self._inbox_thread.join(timeout=2)
        tray = self.tray
        if tray is not None:
            try:
                tray.stop()
            except Exception:
                pass
        if active_controller() is self:
            set_active_controller(None)

    def apply_preferences(self, patch: Dict[str, Any]) -> Dict[str, bool]:
        self.preferences = update_preferences(patch)
        if self.preferences.get("recovery_enabled", True):
            self.recovery_monitor.start()
        else:
            self.recovery_monitor.stop()
        self.refresh_badge()
        return dict(self.preferences)

    def on_window_closing(self, *_args: Any) -> bool:
        tray_available = bool(
            self.tray is not None and getattr(self.tray, "available", True)
        )
        if (
            self.quitting
            or not self.preferences.get("close_to_background", True)
            or not tray_available
        ):
            return True
        self.hide_window()
        return False

    def show_window(self, deep_link: str = "", *, mark_read: bool = False) -> None:
        if deep_link:
            try:
                url = deep_link_to_local_url(self.base_url, deep_link)
                with _FILE_LOCK:
                    state = _load_state()
                    state["last_deep_link"] = deep_link
                    _save_state(state)
                if self.window is not None:
                    self.window.load_url(url)
            except (ValueError, AttributeError):
                pass
        if self.window is not None:
            try:
                self.window.show()
            except Exception:
                pass
        self.visible = True
        if mark_read:
            mark_desktop_notifications_read()

    def hide_window(self) -> None:
        if self.window is not None:
            try:
                self.window.hide()
            except Exception:
                pass
        self.visible = False

    def quit(self) -> None:
        self.quitting = True
        if self.window is not None:
            try:
                self.window.destroy()
            except Exception:
                pass

    def notification_received(
        self,
        _title: str,
        _body: str,
        _deep_link: str,
    ) -> None:
        self.refresh_badge()

    def refresh_badge(self) -> None:
        state = _load_state()
        unread = int(state.get("unread_count") or 0)
        if not self.preferences.get("badge_enabled", True):
            unread = 0
        if self.tray is not None:
            try:
                self.tray.set_badge(unread)
            except Exception:
                pass
        if self.window is not None:
            try:
                self.window.set_title(
                    f"{APP_NAME} ({unread})" if unread else APP_NAME
                )
            except Exception:
                pass
        if sys.platform == "darwin":
            try:
                from AppKit import NSApp

                tile = NSApp.dockTile()
                tile.setBadgeLabel_(str(unread) if unread else None)
            except Exception:
                pass

    def _poll_deep_links(self) -> None:
        while not self._inbox_stop.wait(0.8):
            for value in pop_deep_links():
                self.show_window(value, mark_read=True)

    def _recover(self, reason: str) -> None:
        if not self.preferences.get("recovery_enabled", True):
            return
        self._recovery_callback(reason)
        with _FILE_LOCK:
            state = _load_state()
            state["recovery_count"] = int(state.get("recovery_count") or 0) + 1
            state["last_recovery_at"] = time.time()
            state["last_recovery_reason"] = reason
            _save_state(state)

    def status(self) -> Dict[str, Any]:
        state = _load_state()
        tray_available = bool(self.tray is not None and getattr(self.tray, "available", True))
        autostart = autostart_status()
        return {
            "ok": True,
            "frontend": "desktop",
            "preferences": dict(self.preferences),
            "state": {
                "unread_count": int(state.get("unread_count") or 0),
                "last_deep_link": str(state.get("last_deep_link") or ""),
                "last_notification_at": float(state.get("last_notification_at") or 0),
                "recovery_count": int(state.get("recovery_count") or 0),
                "last_recovery_at": float(state.get("last_recovery_at") or 0),
                "last_recovery_reason": str(state.get("last_recovery_reason") or ""),
            },
            "autostart": autostart,
            "scheme": dict(self.scheme),
            "visible": self.visible,
            "capabilities": DesktopCapabilities(
                desktop=True,
                tray=tray_available,
                background=tray_available,
                autostart=autostart["method"] != "unsupported",
                badge=True,
                deep_links=True,
                recovery=True,
            ).__dict__,
        }


def set_active_controller(controller: Optional[DesktopLifecycleController]) -> None:
    global _ACTIVE_CONTROLLER
    with _CONTROLLER_LOCK:
        _ACTIVE_CONTROLLER = controller


def active_controller() -> Optional[DesktopLifecycleController]:
    with _CONTROLLER_LOCK:
        return _ACTIVE_CONTROLLER


def desktop_status() -> Dict[str, Any]:
    controller = active_controller()
    if controller is not None:
        return controller.status()
    state = _load_state()
    preferences = load_preferences()
    autostart = autostart_status()
    desktop = is_desktop_frontend()
    return {
        "ok": True,
        "frontend": "desktop" if desktop else "webui",
        "preferences": preferences,
        "state": {
            "unread_count": int(state.get("unread_count") or 0),
            "last_deep_link": str(state.get("last_deep_link") or ""),
            "last_notification_at": float(state.get("last_notification_at") or 0),
            "recovery_count": int(state.get("recovery_count") or 0),
            "last_recovery_at": float(state.get("last_recovery_at") or 0),
            "last_recovery_reason": str(state.get("last_recovery_reason") or ""),
        },
        "autostart": autostart,
        "scheme": {"registered": False, "method": "runtime"},
        "visible": None,
        "capabilities": DesktopCapabilities(
            desktop=desktop,
            tray=False,
            background=False,
            autostart=desktop and autostart["method"] != "unsupported",
            badge=desktop,
            deep_links=desktop,
            recovery=desktop,
        ).__dict__,
    }
