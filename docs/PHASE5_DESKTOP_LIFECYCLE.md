# Phase 5 Desktop Lifecycle Guide

## Tray and background mode

The desktop app displays a Toyoko Chan tray/menu-bar icon. Closing the main
window keeps monitoring in the background by default. Use **Show** to restore
the window and **Quit** to stop the local server and all monitoring services.

If the operating system tray integration is not present, closing the window
exits the app instead of leaving a hidden background process.

Start directly in the background:

```bash
toyoko-tracker-desktop --background
```

## Desktop settings

Open **Interface Settings → Desktop Background** to configure:

- keep running when the window closes;
- start at operating-system login;
- show the unread notification badge;
- recover monitoring after sleep or network restoration.

The card reports WebUI fallback when the current process is not the packaged
desktop app.

## Tray task controls

The tray menu provides:

- Show;
- Vacancy Monitor;
- Start current task;
- Pause current task;
- Open latest notification;
- Mark notifications read;
- Quit.

Start/Pause uses the same task APIs as the WebUI and therefore retains global
Provider pacing and task state.

## Notification links and badges

Availability and alert events store a link to the relevant task, hotel and
stay date. Selecting a supported native notification opens the desktop window,
switches to Vacancy Monitor and filters the result list to that hotel.

The unread count remains after restart. It is cleared when a notification link
is opened, from the tray's Mark Read command, or with **Clear Badge** in
Interface Settings.

## Sleep and network recovery

After the computer wakes from sleep or its network becomes available again,
the desktop app wakes the existing scheduler and alert dispatcher and resumes
durable flexible-date jobs. Current task state, pacing and notification queues
remain unchanged.

## Platform notes

### macOS

- Uses the menu bar and Dock badge.
- Login startup uses a user LaunchAgent.
- Notification links require notification permission for the sending
  application; terminal-notifier provides direct click-through when installed.

### Windows

- Uses a notification-area tray icon and per-user Run registration.
- Notification balloons open the registered `toyoko-tracker://` protocol.
- Windows ARM64 uses the QtWebView window with the same lifecycle controller.

### Linux

- Prefers AppIndicator and falls back through GTK/Xorg backends.
- Login startup uses the XDG autostart directory.
- Notification click-through uses libnotify actions when supported; the tray's
  Latest Notification command remains available on other desktops.
- A graphical X11/Wayland, DBus, GTK/WebKitGTK and notification session is
  required for native desktop behavior.
