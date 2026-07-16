from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = (ROOT / "src" / "toyoko_tracker" / "runtime.py").read_text(
    encoding="utf-8"
)
APP_JS = (ROOT / "src" / "toyoko_tracker" / "static" / "app.js").read_text(
    encoding="utf-8"
)
APP_CSS = (ROOT / "src" / "toyoko_tracker" / "static" / "app.css").read_text(
    encoding="utf-8"
)


def test_task_center_navigation_and_view_contract():
    assert 'data-app-view="tasks"' in RUNTIME
    assert 'id="view-tasks"' in RUNTIME
    assert "'tasks'" in APP_JS.split("const APP_VIEWS =", 1)[1].split(";", 1)[0]


def test_task_center_exposes_phase_one_live_actions_and_runtime_metrics():
    for action in (
        "edit",
        "duplicate",
        "rename",
        "move-up",
        "move-down",
        "pause",
        "delete",
    ):
        assert f'data-task-action="{action}"' in RUNTIME
    assert 'id="task-create-button"' in RUNTIME
    assert 'id="task-future-card"' in RUNTIME
    for element_id in (
        "task-detail-progress",
        "task-detail-next",
        "task-detail-results",
        "task-detail-error",
        "task-run-history",
        "task-summary-pacer",
    ):
        assert f'id="{element_id}"' in RUNTIME


def test_task_center_uses_task_native_api_and_selected_task_projection():
    for path in (
        "/api/v1/tasks/summary",
        "/api/v1/tasks/reorder",
        "/api/v1/tasks/${encodeURIComponent(taskId)}",
        "/runs?limit=5",
    ):
        assert path in APP_JS
    assert "taskCenterMockSelectionRequest" not in APP_JS
    assert "task_id=${encodeURIComponent(taskId)}" in APP_JS
    assert "payload.task_id = TASK_CENTER_ACTIVE_ID" in APP_JS
    assert "expected_revision:task.revision" in APP_JS
    assert 'id="btn_save_task"' in RUNTIME
    assert "function callSaveTask()" in APP_JS


def test_task_switching_has_request_token_and_revision_guards():
    assert "TASK_CENTER_REQUEST_TOKEN" in APP_JS
    assert "TASK_CENTER_REVISION" in APP_JS
    assert "requestToken !== TASK_CENTER_REQUEST_TOKEN" in APP_JS
    assert "revision !== TASK_CENTER_REVISION" in APP_JS


def test_task_center_has_all_supported_locales_and_mobile_layout():
    block = APP_JS.split("const TASK_CENTER_UI =", 1)[1].split(
        "const TREND_READABLE_UI", 1
    )[0]
    for language in ("zh_cn", "zh_tw", "ja", "ko", "en"):
        assert f"{language}:" in block
        assert "navTasks:" in block
    assert ".task-center-layout{grid-template-columns:1fr;}" in APP_CSS
    assert ".task-detail-actions{grid-template-columns:1fr 1fr;}" in APP_CSS


def test_phase_two_alert_editor_policy_history_and_calendar_badges_are_wired():
    for element_id in (
        "alert_rule_type",
        "alert_rule_hotel",
        "alert_rule_value",
        "alert_rule_percent",
        "alert_rule_cooldown",
        "alert_rule_critical",
        "btn_alert_rule_add",
        "btn_alert_rule_cancel",
        "alert_policy_timezone",
        "alert_policy_quiet_start",
        "alert_policy_quiet_end",
        "alert_policy_aggregation",
        "alert_policy_digest_mode",
        "alert_policy_digest_time",
        "btn_alert_policy_save",
        "alert-history-list",
    ):
        assert f'id="{element_id}"' in RUNTIME
    for path in (
        "/api/v1/alerts/rules",
        "/api/v1/alerts/policy",
        "/api/v1/alerts/history",
        "/api/v1/alerts/batches/",
    ):
        assert path in APP_JS
    assert "payload.alert_badges" in APP_JS
    assert "price-alert-badge" in APP_CSS
