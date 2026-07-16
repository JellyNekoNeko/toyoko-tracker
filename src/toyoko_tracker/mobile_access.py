from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import os
import secrets
import shutil
import socket
import subprocess
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import timedelta
from io import BytesIO
from typing import Any, Callable, Deque, Dict, List, Optional, Tuple
from urllib.parse import urlsplit

from flask import Flask, Response, jsonify, redirect, request, session

from .settings import APP_VERSION, MOBILE_ACCESS_PATH


_PAIRING_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_PAIRING_ATTEMPTS = 6
_PAIRING_WINDOW_SECONDS = 60
_PUBLIC_PATHS = {
    "/manifest.webmanifest",
    "/service-worker.js",
    "/pair",
}


def _atomic_write_json(path: str, data: Dict[str, Any]) -> None:
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    temp_path = f"{path}.{os.getpid()}.tmp"
    with open(temp_path, "w", encoding="utf-8") as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temp_path, path)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def _new_pairing_code() -> str:
    raw = "".join(secrets.choice(_PAIRING_ALPHABET) for _ in range(10))
    return f"{raw[:5]}-{raw[5:]}"


def _normalize_pairing_code(value: Any) -> str:
    return "".join(ch for ch in str(value or "").upper() if ch.isalnum())


def _revision_for(code: str) -> str:
    return hashlib.sha256(_normalize_pairing_code(code).encode("ascii")).hexdigest()[:24]


def is_loopback_address(value: Optional[str]) -> bool:
    try:
        return ipaddress.ip_address(value or "").is_loopback
    except ValueError:
        return False


def _candidate_ipv4_addresses() -> Tuple[List[str], Optional[str]]:
    addresses = set()
    preferred = None
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            addresses.add(info[4][0])
    except OSError:
        pass
    try:
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        probe.connect(("192.0.2.1", 9))
        preferred = probe.getsockname()[0]
        addresses.add(preferred)
        probe.close()
    except OSError:
        pass
    return sorted(addresses), preferred


def local_ipv4_addresses() -> List[str]:
    addresses, preferred = _candidate_ipv4_addresses()
    usable = [address for address in addresses if _is_usable_lan_address(address)]
    return sorted(usable, key=lambda address: (0 if address == preferred else 1, address))


def direct_public_ipv4_addresses() -> List[str]:
    addresses, preferred = _candidate_ipv4_addresses()
    usable = [address for address in addresses if _is_direct_public_address(address)]
    return sorted(usable, key=lambda address: (0 if address == preferred else 1, address))


def _is_usable_lan_address(value: str) -> bool:
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return False
    benchmark_network = ipaddress.ip_network("198.18.0.0/15")
    return address.is_private and not (
        address.is_loopback
        or address.is_link_local
        or address.is_unspecified
        or address.is_multicast
        or address in benchmark_network
    )


def _is_direct_public_address(value: str) -> bool:
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return False
    return address.version == 4 and address.is_global


def _tailscale_details_from_status(data: Any) -> Dict[str, Any]:
    if not isinstance(data, dict):
        return {"available": False, "online": False}
    self_status = data.get("Self")
    if not isinstance(self_status, dict):
        return {"available": False, "online": False}
    tailscale_network = ipaddress.ip_network("100.64.0.0/10")
    address = ""
    for value in self_status.get("TailscaleIPs") or []:
        try:
            parsed = ipaddress.ip_address(str(value))
        except ValueError:
            continue
        if parsed.version == 4 and parsed in tailscale_network:
            address = str(parsed)
            break
    dns_name = str(self_status.get("DNSName") or "").rstrip(".")
    return {
        "available": bool(address),
        "online": bool(address and self_status.get("Online", True)),
        "address": address,
        "dns_name": dns_name,
    }


def tailscale_details() -> Dict[str, Any]:
    executable = shutil.which("tailscale")
    if not executable:
        return {"available": False, "online": False}
    try:
        result = subprocess.run(
            [executable, "status", "--json"],
            capture_output=True,
            check=False,
            text=True,
            timeout=2,
        )
        if result.returncode != 0:
            return {"available": False, "online": False}
        return _tailscale_details_from_status(json.loads(result.stdout))
    except (OSError, subprocess.SubprocessError, ValueError, TypeError):
        return {"available": False, "online": False}


@dataclass(frozen=True)
class MobileAccessState:
    enabled: bool
    pairing_code: str
    session_secret: str
    revision: str
    public_url: str


class MobileAccessManager:
    def __init__(self, path: str = MOBILE_ACCESS_PATH) -> None:
        self.path = path
        self._lock = threading.RLock()
        self._state = self._load_or_create()
        self._failures: Dict[str, Deque[float]] = defaultdict(deque)

    def _load_or_create(self) -> MobileAccessState:
        data: Dict[str, Any] = {}
        try:
            with open(self.path, "r", encoding="utf-8") as stream:
                loaded = json.load(stream)
            if isinstance(loaded, dict):
                data = loaded
        except (OSError, ValueError, TypeError):
            pass
        pairing_code = str(data.get("pairing_code") or _new_pairing_code())
        session_secret = str(data.get("session_secret") or secrets.token_urlsafe(48))
        state = MobileAccessState(
            enabled=bool(data.get("enabled", False)),
            pairing_code=pairing_code,
            session_secret=session_secret,
            revision=_revision_for(pairing_code),
            public_url=str(data.get("public_url") or ""),
        )
        self._persist(state)
        return state

    def _persist(self, state: MobileAccessState) -> None:
        _atomic_write_json(self.path, {
            "enabled": state.enabled,
            "pairing_code": state.pairing_code,
            "session_secret": state.session_secret,
            "public_url": state.public_url,
            "updated_at": int(time.time()),
        })

    def snapshot(self) -> MobileAccessState:
        with self._lock:
            return self._state

    def configure(
        self,
        enabled: Optional[bool] = None,
        rotate: bool = False,
        public_url: Optional[str] = None,
    ) -> MobileAccessState:
        with self._lock:
            current = self._state
            pairing_code = _new_pairing_code() if rotate else current.pairing_code
            self._state = MobileAccessState(
                enabled=current.enabled if enabled is None else bool(enabled),
                pairing_code=pairing_code,
                session_secret=current.session_secret,
                revision=_revision_for(pairing_code),
                public_url=current.public_url if public_url is None else public_url,
            )
            self._persist(self._state)
            if rotate:
                self._failures.clear()
            return self._state

    def verify(self, value: Any, remote_addr: str) -> Tuple[bool, int]:
        now = time.monotonic()
        with self._lock:
            failures = self._failures[remote_addr]
            while failures and now - failures[0] > _PAIRING_WINDOW_SECONDS:
                failures.popleft()
            if len(failures) >= _PAIRING_ATTEMPTS:
                retry_after = max(1, int(_PAIRING_WINDOW_SECONDS - (now - failures[0])))
                return False, retry_after
            expected = _normalize_pairing_code(self._state.pairing_code)
            supplied = _normalize_pairing_code(value)
            if hmac.compare_digest(expected, supplied):
                failures.clear()
                return True, 0
            failures.append(now)
            return False, 0


manager = MobileAccessManager()


def configure_flask_app(app: Flask) -> None:
    app.secret_key = manager.snapshot().session_secret
    app.config.update(
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        PERMANENT_SESSION_LIFETIME=timedelta(days=30),
    )


def _same_origin_write_error() -> Optional[Response]:
    if request.method not in {"POST", "PUT", "PATCH", "DELETE"}:
        return None
    if request.headers.get("Sec-Fetch-Site", "").lower() == "cross-site":
        return jsonify({"ok": False, "error": "Cross-site request blocked"}), 403
    origin = request.headers.get("Origin")
    if origin and request.path != "/pair":
        source = urlsplit(origin)
        target = urlsplit(request.host_url)
        if (source.scheme, source.netloc) != (target.scheme, target.netloc):
            return jsonify({"ok": False, "error": "Origin not allowed"}), 403
    return None


def protect_request() -> Optional[Response]:
    local_request = is_loopback_address(request.remote_addr)
    if not local_request:
        state = manager.snapshot()
        if not state.enabled:
            return jsonify({"ok": False, "error": "Local access only"}), 403
        public = request.path in _PUBLIC_PATHS or request.path.startswith("/static/")
        authenticated = session.get("mobile_access_revision") == state.revision
        if not public and not authenticated:
            if request.method == "GET" and request.accept_mimetypes.accept_html:
                return redirect("/pair")
            return jsonify({"ok": False, "error": "Pairing required"}), 401
    return _same_origin_write_error()


def require_local_request() -> Optional[Response]:
    if is_loopback_address(request.remote_addr):
        return None
    return jsonify({"ok": False, "error": "This setting can only be changed on the host computer"}), 403


def _request_port() -> int:
    try:
        return int(request.host.rsplit(":", 1)[1])
    except (IndexError, ValueError):
        return 443 if request.is_secure else 80


def _address_url(address: str) -> str:
    scheme = "https" if request.is_secure else "http"
    port = _request_port()
    suffix = "" if (scheme, port) in {("http", 80), ("https", 443)} else f":{port}"
    return f"{scheme}://{address}{suffix}"


def _normalize_public_url(value: Any) -> str:
    candidate = str(value or "").strip()
    if not candidate:
        return ""
    parsed = urlsplit(candidate)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("public_url must be an http(s) URL")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("public_url cannot contain credentials, a query, or a fragment")
    path = parsed.path.rstrip("/")
    if path:
        raise ValueError("public_url must not contain a path")
    return f"{parsed.scheme}://{parsed.netloc}"


def access_urls() -> List[str]:
    return [_address_url(address) for address in local_ipv4_addresses()]


def connection_payload() -> Dict[str, Any]:
    lan_urls = access_urls()
    detected_public_urls = [_address_url(address) for address in direct_public_ipv4_addresses()]
    configured_public_url = manager.snapshot().public_url
    public_urls = [configured_public_url] if configured_public_url else detected_public_urls
    tailscale = tailscale_details()
    tailscale_address = str(tailscale.get("address") or "")
    tailscale_url = _address_url(tailscale_address) if tailscale_address else ""
    tailscale_dns = str(tailscale.get("dns_name") or "")
    return {
        "lan": {
            "available": bool(lan_urls),
            "online": bool(lan_urls),
            "urls": lan_urls,
            "url": lan_urls[0] if lan_urls else "",
        },
        "tailscale": {
            **tailscale,
            "url": tailscale_url,
            "dns_url": _address_url(tailscale_dns) if tailscale_dns else "",
        },
        "public": {
            "available": bool(public_urls),
            "online": bool(public_urls),
            "urls": public_urls,
            "url": public_urls[0] if public_urls else "",
            "configured": bool(configured_public_url),
            "configured_url": configured_public_url,
            "detected": bool(detected_public_urls),
            "requires_https": bool(public_urls and not public_urls[0].lower().startswith("https://")),
        },
    }


def status_payload(runtime_lan: bool) -> Dict[str, Any]:
    state = manager.snapshot()
    local_request = is_loopback_address(request.remote_addr)
    connections = connection_payload() if local_request else {}
    urls = list(connections.get("lan", {}).get("urls") or [])
    return {
        "ok": True,
        "enabled": state.enabled,
        "runtime_lan": bool(runtime_lan),
        "restart_required": bool(state.enabled) != bool(runtime_lan),
        "local_request": local_request,
        "urls": urls,
        "connections": connections,
        "pairing_code": state.pairing_code if local_request else None,
        "revision": state.revision,
        "secure_context": request.is_secure,
        "qr_available": _segno_available(),
    }


def settings_endpoint(
    runtime_lan: bool,
    restart_callback: Optional[Callable[[], bool]] = None,
) -> Response:
    if request.method == "GET":
        return jsonify(status_payload(runtime_lan))
    local_error = require_local_request()
    if local_error:
        return local_error
    payload = request.get_json(silent=True) or {}
    enabled = payload.get("enabled")
    if enabled is not None and not isinstance(enabled, bool):
        return jsonify({"ok": False, "error": "enabled must be a boolean"}), 400
    public_url = None
    if "public_url" in payload:
        try:
            public_url = _normalize_public_url(payload.get("public_url"))
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
    manager.configure(
        enabled=enabled,
        rotate=bool(payload.get("rotate", False)),
        public_url=public_url,
    )
    result = status_payload(runtime_lan)
    restart_requested = bool(payload.get("restart", False)) and result["restart_required"]
    result["restart_scheduled"] = bool(restart_callback and restart_callback()) if restart_requested else False
    return jsonify(result)


def _segno_available() -> bool:
    try:
        import segno  # noqa: F401
        return True
    except ImportError:
        return False


def pairing_url(connection: str = "lan") -> Optional[str]:
    connections = connection_payload()
    selected = connections.get(connection) if connection in {"lan", "tailscale", "public"} else None
    target = str((selected or {}).get("url") or "")
    if not target:
        return None
    return f"{target}/pair#code={manager.snapshot().pairing_code}"


def qr_svg_response() -> Response:
    local_error = require_local_request()
    if local_error:
        return local_error
    connection = request.args.get("connection", "lan").strip().lower()
    target = pairing_url(connection)
    if not target:
        return jsonify({"ok": False, "error": "Connection address unavailable"}), 503
    try:
        import segno
    except ImportError:
        return jsonify({"ok": False, "error": "Install toyoko-tracker[mobile] for QR support"}), 503
    output = BytesIO()
    segno.make(target, error="m").save(output, kind="svg", scale=5, border=2, dark="#17355b")
    return Response(output.getvalue(), mimetype="image/svg+xml")


def pairing_page() -> Response:
    if request.method == "POST":
        value = (request.get_json(silent=True) or {}).get("code") if request.is_json else request.form.get("code")
        valid, retry_after = manager.verify(value, request.remote_addr or "unknown")
        if retry_after:
            response = jsonify({"ok": False, "error": "Too many attempts", "retry_after": retry_after})
            response.status_code = 429
            response.headers["Retry-After"] = str(retry_after)
            return response
        if not valid:
            if request.is_json:
                return jsonify({"ok": False, "error": "Invalid pairing code"}), 401
            return _pairing_html("配对码不正确 / Invalid pairing code"), 401
        session.clear()
        session.permanent = True
        session["mobile_access_revision"] = manager.snapshot().revision
        if request.is_json:
            return jsonify({"ok": True})
        return redirect("/")
    if is_loopback_address(request.remote_addr):
        return redirect("/")
    return _pairing_html()


def _pairing_html(error: str = "") -> Response:
    safe_error = error.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    try:
        remote_address = ipaddress.ip_address(request.remote_addr or "")
        via_tailscale = remote_address in ipaddress.ip_network("100.64.0.0/10")
    except ValueError:
        via_tailscale = False
    connection_label = "Tailscale 远程连接 / Remote" if via_tailscale else "局域网连接 / Local network"
    html = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#155ec2"><title>Toyoko Chan Pairing</title>
<style>
*{{box-sizing:border-box}}body{{min-height:100dvh;margin:0;display:grid;place-items:center;padding:max(18px,env(safe-area-inset-top)) 18px max(18px,env(safe-area-inset-bottom));background:#edf2f7;color:#172b45;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}}
main{{width:min(100%,410px);overflow:hidden;border:1px solid #d7e0eb;border-radius:16px;background:#fff;box-shadow:0 20px 54px rgba(23,53,91,.14)}}.head{{padding:22px 22px 18px;background:#f8fbff;border-bottom:1px solid #e2e8f0}}
.brand{{display:flex;align-items:center;gap:13px}}img{{width:54px;height:54px;border:1px solid #d8e2ef;border-radius:12px;background:#fff}}h1{{margin:0;font-size:22px;letter-spacing:0}}p{{margin:4px 0 0;color:#68758a;line-height:1.45}}.channel{{display:inline-flex;align-items:center;gap:7px;margin-top:14px;padding:6px 9px;border:1px solid #c9dcf4;border-radius:7px;background:#eef5ff;color:#15559c;font-size:12px;font-weight:750}}.channel:before{{content:'';width:7px;height:7px;border-radius:50%;background:#2f8a45;box-shadow:0 0 0 3px #dff1e4}}
.body{{padding:20px 22px 22px}}.intro{{margin:0 0 14px;color:#475467;font-size:14px}}label{{display:block;margin:0 0 7px;font-weight:750}}input{{width:100%;height:50px;padding:0 14px;border:1px solid #bfcddd;border-radius:9px;outline:none;font-size:21px;font-weight:750;letter-spacing:2px;text-transform:uppercase}}input:focus{{border-color:#2872d1;box-shadow:0 0 0 3px rgba(40,114,209,.14)}}button{{width:100%;height:48px;margin-top:11px;border:0;border-radius:9px;background:#155ec2;color:#fff;font-size:16px;font-weight:780;box-shadow:0 4px 12px rgba(21,94,194,.2)}}.error{{margin-top:12px;padding:9px 11px;border-radius:7px;background:#fff1f0;color:#b42318;font-weight:650}}.help{{display:grid;gap:8px;margin-top:17px;padding-top:15px;border-top:1px solid #e6ebf1;color:#667085;font-size:12px;line-height:1.5}}.help div{{display:grid;grid-template-columns:22px 1fr;gap:7px}}.help b{{display:grid;place-items:center;width:21px;height:21px;border-radius:50%;background:#edf4fd;color:#15559c;font-size:11px}}
</style></head><body><main><div class="head"><div class="brand"><img src="/static/toyoko-chan-mascot.png" alt=""><div><h1>连接东横酱</h1><p>Connect to Toyoko Chan</p></div></div><div class="channel">{connection_label}</div></div><div class="body">
<p class="intro">输入 Mac 上显示的配对码以继续。<br>Enter the pairing code shown on your Mac.</p><form method="post" id="pair-form"><label for="code">配对码 / Pairing code</label><input id="code" name="code" autocomplete="one-time-code" autocapitalize="characters" required maxlength="11"><button type="submit">安全连接 / Connect securely</button></form>
{f'<div class="error">{safe_error}</div>' if safe_error else ''}<div class="help"><div><b>1</b><span>配对码位于主机电脑的“界面设定 → 手机访问”。<br>Find the code under Interface Settings → Mobile Access on the host computer.</span></div><div><b>2</b><span>配对成功后，当前设备会保留登录状态。更换配对码可撤销旧设备访问。</span></div><div><b>3</b><span>请仅在自己的设备或可信任的网络中配对。</span></div></div></div>
<script>const value=new URLSearchParams(location.hash.slice(1)).get('code');if(value){{document.getElementById('code').value=value;location.hash='';document.getElementById('pair-form').requestSubmit();}}</script>
</main></body></html>"""
    return Response(html, mimetype="text/html")


def logout() -> Response:
    session.clear()
    return redirect("/pair")


def manifest_response() -> Response:
    manifest = {
        "id": "/",
        "name": "Toyoko Chan",
        "short_name": "Toyoko Chan",
        "description": "Private hotel vacancy monitoring dashboard",
        "start_url": "/",
        "scope": "/",
        "display": "standalone",
        "background_color": "#edf1f5",
        "theme_color": "#155ec2",
        "icons": [{
            "src": "/static/toyoko-chan-mascot.png?v=3",
            "sizes": "256x256",
            "type": "image/png",
            "purpose": "any maskable",
        }],
        "shortcuts": [
            {"name": "Vacancy Search", "short_name": "Search", "url": "/?view=search"},
            {"name": "Vacancy Monitor", "short_name": "Monitor", "url": "/?view=monitor"},
        ],
    }
    return Response(json.dumps(manifest, ensure_ascii=False), mimetype="application/manifest+json")


def service_worker_response() -> Response:
    script = """const CACHE='toyoko-chan-shell-v4';
const DATA='toyoko-chan-data-v4';
const SHELL=['/static/app.css?v=__ASSET_REVISION__','/static/app.js?v=__ASSET_REVISION__','/static/toyoko-chan-mascot.png?v=3','/manifest.webmanifest'];
const DATA_PATHS=['/status','/api/v1/runtime','/api/v1/results','/api/v1/availability-logs','/api/v1/trends','/api/v1/providers'];
self.addEventListener('install',event=>{event.waitUntil(caches.open(CACHE).then(cache=>cache.addAll(SHELL)).catch(()=>{}));self.skipWaiting();});
self.addEventListener('activate',event=>{event.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(key=>![CACHE,DATA].includes(key)).map(key=>caches.delete(key)))));self.clients.claim();});
async function networkFirst(request,cacheName,fallbackKey){try{const response=await fetch(request);if(response&&response.ok){const cache=await caches.open(cacheName);await cache.put(fallbackKey||request,response.clone());}return response;}catch(error){const cached=await caches.match(fallbackKey||request);if(cached)return cached;throw error;}}
self.addEventListener('fetch',event=>{const url=new URL(event.request.url);if(event.request.method!=='GET'||url.origin!==location.origin)return;
if(url.pathname.startsWith('/static/')||url.pathname==='/manifest.webmanifest'){event.respondWith(networkFirst(event.request,CACHE));return;}
if(event.request.mode==='navigate'){event.respondWith(networkFirst(event.request,DATA,'/__app_shell__'));return;}
if(DATA_PATHS.includes(url.pathname)){event.respondWith(networkFirst(event.request,DATA));}
});
self.addEventListener('message',event=>{if(event.data&&event.data.type==='SKIP_WAITING')self.skipWaiting();});
"""
    script = script.replace("__ASSET_REVISION__", f"{APP_VERSION}-phase5-1")
    response = Response(script, mimetype="application/javascript")
    response.headers["Service-Worker-Allowed"] = "/"
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return response
