import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from toyoko_tracker import desktop_lifecycle as lifecycle
from toyoko_tracker.app import app


def _patch_storage(tmp_path: Path):
    return (
        patch.object(
            lifecycle,
            "DESKTOP_PREFERENCES_PATH",
            str(tmp_path / "desktop_preferences.json"),
        ),
        patch.object(
            lifecycle,
            "DESKTOP_STATE_PATH",
            str(tmp_path / "desktop_state.json"),
        ),
        patch.object(
            lifecycle,
            "DESKTOP_DEEP_LINK_INBOX_PATH",
            str(tmp_path / "desktop_deep_links.json"),
        ),
    )


def test_deep_link_round_trip_and_local_url():
    link = lifecycle.build_deep_link(
        view="price",
        task_id="task-1",
        hotel_code="00001",
        stay_date="2026-08-01",
        event_id="event-1",
    )

    assert lifecycle.parse_deep_link(link) == {
        "view": "price",
        "task_id": "task-1",
        "hotel_code": "00001",
        "stay_date": "2026-08-01",
        "event_id": "event-1",
    }
    assert lifecycle.deep_link_to_local_url("http://127.0.0.1:4170", link).startswith(
        "http://127.0.0.1:4170/?view=price&task_id=task-1"
    )


def test_invalid_deep_link_is_rejected():
    try:
        lifecycle.parse_deep_link("https://example.com/")
    except ValueError as exc:
        assert "deep link" in str(exc)
    else:
        raise AssertionError("invalid deep link should be rejected")


def test_preferences_and_unread_badge_are_persistent_and_deduplicated(tmp_path):
    patches = _patch_storage(tmp_path)
    with patches[0], patches[1], patches[2], patch.dict(
        os.environ, {"TOYOKO_TRACKER_FRONTEND": "desktop"}
    ):
        preferences = lifecycle.update_preferences(
            {"close_to_background": False, "badge_enabled": True}
        )
        link = lifecycle.build_deep_link(event_id="event-1")
        lifecycle.record_desktop_notification(
            "Available", "Hotel 1", link, dedupe_key="event-1"
        )
        lifecycle.record_desktop_notification(
            "Available", "Hotel 1", link, dedupe_key="event-1"
        )

        status = lifecycle.desktop_status()
        assert preferences["close_to_background"] is False
        assert status["state"]["unread_count"] == 1
        assert status["state"]["last_deep_link"] == link
        assert lifecycle.mark_desktop_notifications_read()["state"]["unread_count"] == 0


def test_deep_link_inbox_forwards_to_running_controller(tmp_path):
    patches = _patch_storage(tmp_path)
    link = lifecycle.build_deep_link(task_id="task-2")
    with patches[0], patches[1], patches[2]:
        lifecycle.queue_deep_link(link)
        assert lifecycle.pop_deep_links() == [link]
        assert lifecycle.pop_deep_links() == []


def test_deep_link_forwarding_only_targets_a_desktop_instance(tmp_path):
    patches = _patch_storage(tmp_path)
    instance_path = tmp_path / "instance.json"
    link = lifecycle.build_deep_link(task_id="task-2")
    with (
        patches[0],
        patches[1],
        patches[2],
        patch.object(lifecycle, "INSTANCE_STATE_PATH", str(instance_path)),
        patch.object(lifecycle, "_pid_is_alive", return_value=True),
    ):
        instance_path.write_text(
            json.dumps({"pid": 999, "frontend": "webui"}),
            encoding="utf-8",
        )
        assert lifecycle.forward_deep_link_to_running(link) is False
        instance_path.write_text(
            json.dumps({"pid": 999, "frontend": "desktop"}),
            encoding="utf-8",
        )
        assert lifecycle.forward_deep_link_to_running(link) is True
        assert lifecycle.pop_deep_links() == [link]


def test_recovery_monitor_detects_resume_and_network_restore():
    ticks = iter([0.0, 10.0, 80.0, 90.0])
    online = iter([True, False, True])
    callback = Mock()
    monitor = lifecycle.RecoveryMonitor(
        callback,
        interval=5,
        resume_threshold=30,
        monotonic=lambda: next(ticks),
        probe=lambda: next(online),
    )

    assert monitor.check_once() == []
    assert monitor.check_once() == ["resume"]
    assert monitor.check_once() == ["network-restored"]
    assert callback.call_args_list[0].args == ("resume",)
    assert callback.call_args_list[1].args == ("network-restored",)


def test_recovery_monitor_uses_wall_clock_when_monotonic_pauses_during_sleep():
    monotonic = iter([0.0, 5.0])
    wall = iter([100.0, 180.0])
    callback = Mock()
    monitor = lifecycle.RecoveryMonitor(
        callback,
        interval=5,
        resume_threshold=30,
        monotonic=lambda: next(monotonic),
        wall_clock=lambda: next(wall),
        probe=lambda: True,
    )

    assert monitor.check_once() == ["resume"]
    callback.assert_called_once_with("resume")


class _FakeWindow:
    def __init__(self):
        self.hidden = False
        self.shown = False
        self.destroyed = False
        self.url = ""
        self.title = ""

    def hide(self):
        self.hidden = True

    def show(self):
        self.shown = True

    def destroy(self):
        self.destroyed = True

    def load_url(self, url):
        self.url = url

    def set_title(self, title):
        self.title = title


class _FakeTray:
    available = True

    def set_badge(self, _unread):
        pass

    def stop(self):
        pass


def test_controller_close_hides_with_tray_and_quit_destroys(tmp_path):
    patches = _patch_storage(tmp_path)
    with patches[0], patches[1], patches[2]:
        controller = lifecycle.DesktopLifecycleController("http://127.0.0.1:4170")
        window = _FakeWindow()
        controller.attach_window(window)
        controller.attach_tray(_FakeTray())

        assert controller.on_window_closing() is False
        assert window.hidden is True
        controller.quit()
        assert window.destroyed is True
        assert controller.on_window_closing() is True


def test_macos_launch_agent_autostart(tmp_path):
    launch_agent = tmp_path / "com.jellyneko.toyoko-tracker.plist"
    preferences = tmp_path / "desktop_preferences.json"
    with (
        patch.object(lifecycle.sys, "platform", "darwin"),
        patch.object(lifecycle, "_mac_launch_agent_path", return_value=launch_agent),
        patch.object(lifecycle, "DESKTOP_PREFERENCES_PATH", str(preferences)),
    ):
        enabled = lifecycle.set_autostart(True)
        assert launch_agent.exists()
        assert "--background" in launch_agent.read_text(encoding="utf-8")
        assert enabled["autostart"]["enabled"] is True
        disabled = lifecycle.set_autostart(False)
        assert not launch_agent.exists()
        assert disabled["autostart"]["enabled"] is False


def test_linux_xdg_autostart(tmp_path):
    autostart = tmp_path / "toyoko-tracker.desktop"
    preferences = tmp_path / "desktop_preferences.json"
    with (
        patch.object(lifecycle.sys, "platform", "linux"),
        patch.object(lifecycle, "_linux_autostart_path", return_value=autostart),
        patch.object(lifecycle, "DESKTOP_PREFERENCES_PATH", str(preferences)),
    ):
        lifecycle.set_autostart(True)
        content = autostart.read_text(encoding="utf-8")
        assert "X-GNOME-Autostart-enabled=true" in content
        assert "--background" in content
        lifecycle.set_autostart(False)
        assert not autostart.exists()


def test_windows_run_autostart(tmp_path):
    values = {}

    class Key:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    fake_winreg = SimpleNamespace(
        HKEY_CURRENT_USER=object(),
        REG_SZ=1,
        CreateKey=lambda *_args: Key(),
        OpenKey=lambda *_args: Key(),
        SetValueEx=lambda _key, name, _reserved, _kind, value: values.__setitem__(
            name, value
        ),
        QueryValueEx=lambda _key, name: (
            (values[name], 1)
            if name in values
            else (_ for _ in ()).throw(FileNotFoundError(name))
        ),
        DeleteValue=lambda _key, name: values.pop(name),
    )
    with (
        patch.object(lifecycle.sys, "platform", "win32"),
        patch.object(lifecycle.os, "name", "nt"),
        patch.object(
            lifecycle,
            "update_preferences",
            return_value=dict(lifecycle.DEFAULT_PREFERENCES),
        ),
        patch.dict(sys.modules, {"winreg": fake_winreg}),
    ):
        result = lifecycle.set_autostart(True)
        assert "--background" in values["ToyokoTracker"]
        assert result["autostart"]["enabled"] is True
        lifecycle.set_autostart(False)
        assert "ToyokoTracker" not in values


def test_desktop_lifecycle_api_reports_webui_fallback_and_updates_preferences(
    tmp_path,
):
    patches = _patch_storage(tmp_path)
    app.config.update(TESTING=True)
    with patches[0], patches[1], patches[2], patch.dict(
        os.environ, {"TOYOKO_TRACKER_FRONTEND": ""}
    ):
        lifecycle.set_active_controller(None)
        with app.test_client() as client:
            status = client.get("/api/v1/desktop/lifecycle")
            updated = client.patch(
                "/api/v1/desktop/lifecycle",
                json={
                    "close_to_background": False,
                    "badge_enabled": False,
                    "recovery_enabled": True,
                },
            )
            cleared = client.post("/api/v1/desktop/notifications/read")

    assert status.status_code == 200
    assert status.get_json()["frontend"] == "webui"
    assert updated.status_code == 200
    assert updated.get_json()["preferences"]["close_to_background"] is False
    assert cleared.get_json()["state"]["unread_count"] == 0
