# Phase 5 Native Desktop Lifecycle Architecture

Phase 5 gives the frozen desktop bundles a lifecycle that is independent from
the browser-only WebUI while keeping the Flask application and task scheduler
as the single source of truth.

## Components

### Lifecycle controller

`desktop_lifecycle.py` owns the cross-platform contract:

- explicit `show`, `hide`, `close-to-background` and `quit` behavior;
- persistent desktop preferences and unread-notification state;
- system launch-at-login adapters;
- the `toyoko-tracker://open` deep-link format;
- resume and network-restoration detection;
- capability reporting for the WebUI.

`desktop.py` supplies the native adapters. The standard path uses pywebview and
pystray. Windows ARM64 retains the QtWebView shell and exposes the same adapter
contract through Qt signals.

### Persistent files

All desktop state uses the existing per-user Toyoko Tracker configuration
directory:

| File | Purpose |
| --- | --- |
| `desktop_preferences.json` | close-to-background, launch-at-login, badge and recovery preferences |
| `desktop_state.json` | unread count, latest deep link and recovery diagnostics |
| `desktop_deep_links.json` | short-lived inbox used to forward links to an existing process |

Writes use temporary files plus `os.replace`, so a process interruption does
not leave partially written JSON.

### Tray and window semantics

1. **Close** hides the window only when close-to-background is enabled and a
   working tray/menu-bar icon exists.
2. **Show** restores the current window and may navigate it to a deep link.
3. **Quit** is available from the tray menu and closes the embedded server and
   every background service.
4. When the tray integration is missing, closing the window exits normally;
   the application never becomes an invisible process without a way to reopen
   it.

The tray menu exposes Show, Vacancy Monitor, start/pause current task, latest
notification, clear badge and Quit.

### Launch at login

The lifecycle core uses native per-user mechanisms:

- macOS: `~/Library/LaunchAgents/com.jellyneko.toyoko-tracker.plist`;
- Windows: `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`;
- Linux: `~/.config/autostart/toyoko-tracker.desktop`.

Autostart launches the desktop app with `--background`. No administrator
permission or machine-wide installation is required.

### Resume and network recovery

The recovery monitor detects:

- a monotonic polling gap large enough to indicate system sleep/resume;
- a transition from offline DNS resolution to an available network.

Recovery calls the existing idempotent service entry points, wakes the one task
scheduler and one alert dispatcher, and resumes durable flexible-stay jobs.
It never starts a second Flask server or a second scheduler instance.

### Notification deep links

Desktop links use this stable format:

```text
toyoko-tracker://open?view=monitor&task_id=TASK&hotel_code=HOTEL&stay_date=YYYY-MM-DD&event_id=EVENT
```

The link fields are optional, validated and converted to a local WebUI URL.
If a desktop process already exists, a second invocation writes the link to the
deep-link inbox and exits. The running controller consumes the inbox and
focuses the relevant view.

Platform registration:

- macOS declares `CFBundleURLTypes` and listens for `GURL` Apple Events;
- Windows creates a per-user URL-protocol registration;
- Linux installs an `x-scheme-handler/toyoko-tracker` desktop entry.

Local notifications carry the link through terminal-notifier on macOS,
NotifyIcon click handling on Windows and libnotify actions on supported Linux
desktops. The tray's Latest Notification action remains the deterministic
fallback.

### Badge and unread count

Each newly created event increments one persistent unread counter using the
event ID as its deduplication key. The count is projected to:

- the macOS Dock badge;
- the tray/menu-bar title on every platform;
- the desktop window title;
- the Interface Settings status card.

Opening a notification deep link or selecting Clear Badge resets the count.

## API

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/v1/desktop/lifecycle` | preferences, state, integration capabilities and autostart status |
| `PATCH` | `/api/v1/desktop/lifecycle` | update supported desktop preferences |
| `POST` | `/api/v1/desktop/notifications/read` | clear unread state and native badges |

Browser-only WebUI instances return `frontend: webui` and disable native
controls while preserving the rest of the interface.

## Packaging contract

The desktop extras include pywebview, pystray and Pillow. Linux additionally
uses PyGObject and AppIndicator/GTK when available. PyInstaller declares the
dynamic pystray backends, the macOS URL scheme, and the Linux desktop MIME
handler. The existing workflow continues to target:

- macOS arm64 and x64;
- Windows x64 and ARM64;
- Linux x86_64 and ARM64.

Phase 6 owns the final signed six-runner release regression. Phase 5 freezes
the shared implementation, packaging metadata and automated unit/API contract.
