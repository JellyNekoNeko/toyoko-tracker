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


def test_task_center_exposes_phase_one_prototype_actions():
    for action in ("duplicate", "rename", "move-up", "move-down", "pause", "delete"):
        assert f'data-task-action="{action}"' in RUNTIME
    assert 'id="task-create-button"' in RUNTIME
    assert 'id="task-future-card"' in RUNTIME


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
