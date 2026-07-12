from __future__ import annotations

from typing import Any, Callable, List, Optional

from bs4 import BeautifulSoup

from .models import AppConfig
from .parsing import RenderedPage
from .settings import HEADERS, TIMEOUT

try:
    from playwright.sync_api import sync_playwright
    HAS_PLAYWRIGHT = True
except Exception:
    sync_playwright = None
    HAS_PLAYWRIGHT = False

def _noop(_message: str) -> None:
    return None


_log: Callable[[str], None] = _noop
_set_action: Callable[[str], None] = _noop


def set_renderer_hooks(log: Callable[[str], None], set_action: Callable[[str], None]) -> None:
    global _log, _set_action
    _log = log
    _set_action = set_action


def _playwright_launch_args(cfg: AppConfig) -> List[str]:
    return [
        "--lang=en-US,en;q=0.9",
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--disable-gpu",
        "--window-size=1280,1600",
    ]


def _playwright_route_request(route: Any) -> None:
    try:
        request_obj = route.request
        if request_obj.resource_type in {"image", "media", "font"}:
            route.abort()
            return
        host = ""
        try:
            from urllib.parse import urlparse
            host = urlparse(request_obj.url).netloc.lower()
        except Exception:
            host = ""
        if any(x in host for x in ("googletagmanager", "google-analytics", "doubleclick")):
            route.abort()
            return
        route.continue_()
    except Exception:
        try:
            route.continue_()
        except Exception:
            pass


def _fetch_rendered_playwright_page(page: Any, url: str) -> RenderedPage:
    page.goto(url, wait_until="domcontentloaded", timeout=TIMEOUT * 1000)
    try:
        page.wait_for_selector("main", timeout=3000)
    except Exception:
        try:
            page.wait_for_selector("body", timeout=3000)
        except Exception:
            pass
    try:
        page.wait_for_selector('span[class*="SearchResultRoomPlanChildCard_value"]', timeout=2500)
    except Exception:
        pass
    try:
        page.wait_for_timeout(400)
    except Exception:
        pass
    html = page.content()
    try:
        body_text = page.locator("body").inner_text()
    except Exception:
        body_text = ""
    return RenderedPage(BeautifulSoup(html, "html.parser"), body_text)


class PlaywrightRenderer:
    """Reusable Playwright browser session for a worker loop."""

    def __init__(self, cfg: AppConfig):
        if not HAS_PLAYWRIGHT or sync_playwright is None:
            raise RuntimeError("Playwright is not available")
        _log("Launching headless Chromium via Playwright...")
        _set_action("Launching headless Chromium via Playwright...")
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=True, args=_playwright_launch_args(cfg))
        self._context = self._browser.new_context(
            user_agent=HEADERS.get("User-Agent", None),
            viewport={"width": 1280, "height": 1600},
        )
        self._context.set_default_timeout(TIMEOUT * 1000)
        self._context.set_default_navigation_timeout(TIMEOUT * 1000)
        try:
            self._context.route("**/*", _playwright_route_request)
        except Exception as e:
            _log(f"[playwright] route optimization skipped: {e}")
        self._page = self._context.new_page()
        _log("Playwright Chromium is ready.")
        _set_action("Playwright Chromium is ready.")

    def fetch(self, url: str) -> RenderedPage:
        return _fetch_rendered_playwright_page(self._page, url)

    def close(self) -> None:
        for obj in (getattr(self, "_context", None), getattr(self, "_browser", None)):
            try:
                if obj:
                    obj.close()
            except Exception:
                pass
        self._context = None
        self._browser = None
        try:
            if getattr(self, "_pw", None):
                self._pw.stop()
        except Exception:
            pass
        self._pw = None

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass


def fetch_rendered_playwright(cfg: AppConfig, url: str) -> RenderedPage:
    renderer = PlaywrightRenderer(cfg)
    try:
        return renderer.fetch(url)
    finally:
        renderer.close()


def fetch_rendered_any(cfg: AppConfig, renderer: Optional[Any], url: str) -> RenderedPage:
    if not HAS_PLAYWRIGHT:
        raise RuntimeError("Playwright is not available")
    if isinstance(renderer, PlaywrightRenderer):
        return renderer.fetch(url)
    return fetch_rendered_playwright(cfg, url)
