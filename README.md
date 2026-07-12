# Toyoko Inn Room Vacancy Tracker WebUI

*A cute room availability tracker for [Toyoko Inn](https://www.toyoko-inn.com/), powered by Flask + HTTP/API + optional Playwright.*

🌏 [📖 中文说明书](./README_zh.md)

---

# 📘 Toyoko Tracker User Guide

## Ch.1 Installation & Getting Started

### 1.1 Introduction

**Toyoko Tracker** is a local WebUI tool for automatically checking **Toyoko Inn** room availability.

It supports:

- 🌐 Local WebUI for real-time vacancy tracking
- ⚡ Lightweight HTTP/API search engine by default
- 🧭 Optional Playwright browser-rendering engine for compatibility
- 🏨 Area-based hotel picker
- 🕘 Search history
- 🛏 Room type filtering: Single / Double / Twin
- 💳 Member / non-member price display
- 🔔 Local desktop notifications
- 🤖 Telegram Bot push
- 📱 Bark push for iPhone/iPad
- 💬 Server Chan push for WeChat
- 📧 SMTP email alerts
- 🚀 Smart parallel scanning for large hotel lists

---

### 1.2 Installation

#### Requirements

- Python **3.9+**
- Recommended: Python **3.10 / 3.11 / 3.12**
- Internet connection

#### Optional

- Playwright Chromium, only required when using the **Playwright** engine.

---

### 1.3 Install from PyPI

Open a terminal:

- **Windows**: Press `Win + R`, type `cmd`, then press Enter.  
  You can also use PowerShell.
- **macOS**: Open Launchpad → Terminal.
- **Linux**: Press `Ctrl + Alt + T`.

Run:

```bash
pip install --upgrade pip
pip install --upgrade toyoko-tracker
```

If your Python environment blocks global pip installation, use a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install --upgrade toyoko-tracker
```

On Windows PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install --upgrade pip
pip install --upgrade toyoko-tracker
```

---

### 1.4 Optional: Install Playwright Chromium

The default HTTP/API engine does **not** require Playwright.

Only install Playwright Chromium if you want to use the compatibility browser engine:

```bash
playwright install chromium
```

---

### 1.5 Usage

After installation, run:

```bash
toyoko-tracker
```

After launching:

- A local web server will start.
- Default URL: [http://127.0.0.1:4170](http://127.0.0.1:4170)
- If port `4170` is already occupied, the program will automatically use another free local port.
- The browser will usually open automatically.
- If it does not open, check the terminal output and open the displayed local URL manually.

---

### 1.6 Version Info

- Current version: `v0.6.0`
- App name: `东横酱 Toyoko Chan`
- Author: JellyNeko / bilibili @果冻猫猫丶
- License: MIT
- Architecture: [docs/architecture-v0.6.md](docs/architecture-v0.6.md)

---

## 🏨 Ch.2 Choosing Hotels

Toyoko Tracker supports two ways to choose hotels:

1. **Area mode**: choose a region and optional detail area
2. **Radius mode**: enter a place, address, or coordinates and choose a 1–50 km radius

---

### 2.1 Recommended: Area Hotel Picker

In the WebUI:

1. Select a **Region**
2. Optionally select a **Detail Area**
3. Click **Load Hotels**
4. Select the hotels you want to monitor
5. Click **Start**

You can also:

- Click **Select All** to select all loaded hotels
- Click **Select None** to clear selection
- Use the filter box to search by Chinese name, English name, or hotel code

The selected hotels are shown on the map and saved into the search history.

---

### 2.2 Radius Mode

In the WebUI:

1. Switch the hotel picker to **Radius**
2. Enter a place, address, or latitude/longitude pair
3. Select a radius from 1 to 50 km
4. Click **Load Nearby**
5. Review the map and select the hotels to monitor

Coordinates are parsed locally. Place names and addresses use OpenStreetMap/Nominatim for geocoding.

---

## 🔍 Ch.3 Search Settings

### 3.1 Basic Search Conditions

The WebUI supports:

- Check-in date
- Check-out date
- Number of guests: 1–5
- Number of rooms: 1–9
- Smoking preference:
  - Non-Smoking
  - Smoking
  - Any
- Room type:
  - Any
  - Single
  - Double
  - Twin
- Membership status:
  - Member
  - Non-member
  - Unknown

Quick date buttons are also available:

- Tonight
- Tomorrow
- Weekend

---

### 3.2 Search Engine

Toyoko Tracker provides two engines:

#### HTTP/API Engine

Default and recommended.

Advantages:

- Faster
- Lightweight
- Lower resource usage
- Works without browser rendering

If the HTTP/API engine fails to parse a hotel result, the program may try to fall back to Playwright when available.

#### Playwright Engine

Compatibility mode.

Advantages:

- Closer to real browser rendering
- Useful when Toyoko Inn changes website structure
- Better fallback when HTTP/API parsing fails

Requires:

```bash
playwright install chromium
```

---

### 3.3 Scan Cadence

You can configure:

- **Round Interval**  
  Time between scan rounds. Minimum: 30 seconds.

- **Per-hotel Base Delay**  
  Delay between checking hotels in one scan line.

- **Request Jitter**  
  Adds random timing variation to avoid perfectly fixed request intervals.

Recommended stable settings:

```text
Round Interval: 120 seconds or more
Per-hotel Delay: 2–5 seconds
Request Jitter: 30–50%
```

---

### 3.4 Smart Parallel

Smart Parallel is available for the HTTP/API engine.

It can split hotels into 1–3 scanning workers.

Recommended usage:

- 1 worker: small hotel list
- 2 workers: medium hotel list
- 3 workers: large hotel list

Smart Parallel uses staggered starts and expanded per-line intervals to keep requests more natural.

---

## 🕘 Ch.4 Search History

Toyoko Tracker automatically records recent search settings.

The Search History panel supports:

- Refresh
- Clear
- Reload previous search settings

The program keeps up to the latest 10 search records.

Identical search settings will not be repeatedly added.

---

## 🔔 Ch.5 Push Notifications

Toyoko Tracker can send notifications when:

- Tracking starts
- Rooms become available
- Available rooms remain available and reminder conditions are met
- Previously available rooms become unavailable

The notification message may include:

- Hotel name
- Date range
- Room type
- Non-member price
- Member price
- Remaining room count
- Booking URL

Special room types such as **heartful / accessible rooms** are automatically ignored.

---

### 5.1 Reminder Policy

You can configure:

- Reminder repeat count
- Reminder cooldown interval

The repeat count controls additional reminders after the first availability alert.

The maximum value can be used as continuous reminder mode.

Recommended cooldown:

```text
300 seconds or more
```

---

## 🤖 Ch.6 Telegram Bot Setup

### 6.1 Create a Telegram Bot

1. Open Telegram
2. Search for **BotFather**
3. Send:

```text
/newbot
```

4. Follow the instructions:
   - Bot name, for example `ToyokoBot`
   - Bot username, must end with `bot`
5. BotFather will give you a Bot Token, for example:

```text
1234567890:ABCdefGhIJklmNoPQRstuVWxyZ
```

---

### 6.2 Get Chat ID

For personal chat:

1. Search for **@userinfobot**
2. Start the bot
3. It will show your Chat ID, for example:

```text
987654321
```

For group chat:

1. Add your bot to the group
2. Make sure the bot has permission to send messages
3. Get the group Chat ID using a Telegram update/debug bot or Telegram Bot API

---

### 6.3 Configure Telegram in WebUI

In **Push Settings → Telegram Bot**:

1. Enable Telegram
2. Fill in Bot Token
3. Fill in Chat ID
4. Start tracking

---

## 📱 Ch.7 Bark Push Setup

Bark is useful for iPhone/iPad push notifications.

### 7.1 Setup

1. Install **Bark** on your iPhone/iPad
2. Open Bark
3. Copy your Device Key
4. In Toyoko Tracker WebUI, open **Push Settings → Bark**
5. Enable Bark
6. Paste your Bark Key
7. Keep Bark Server as default unless you use a self-hosted Bark server

Default Bark server:

```text
https://api.day.app
```

---

## 💬 Ch.8 Server Chan Setup

Server Chan can send notifications to WeChat.

### 8.1 Setup

1. Open Server Chan official website
2. Log in with WeChat
3. Bind the WeChat push channel
4. Copy your `SendKey`
5. In Toyoko Tracker WebUI, open **Push Settings → Server Chan**
6. Enable Server Chan
7. Paste the SendKey

The SendKey usually starts with:

```text
SCT
```

---

## 📧 Ch.9 Email Notification Setup

Toyoko Tracker supports SMTP email alerts.

### 9.1 Enable SMTP Service

Steps vary by provider.

#### Gmail

Recommended: use **App Passwords**.

1. Open Google Account settings
2. Go to Security
3. Enable 2-Step Verification
4. Create an App Password
5. Use that password in Toyoko Tracker

#### QQ Mail

1. Open QQ Mail settings
2. Enable SMTP service
3. Generate an authorization code
4. Use the authorization code as SMTP password

#### 163 / 126 Mail

1. Enable POP3/SMTP/IMAP service
2. Generate an authorization code
3. Use the authorization code as SMTP password

---

### 9.2 Fill in Email Settings

In **Push Settings → Email**:

- SMTP Host: for example `smtp.gmail.com` or `smtp.qq.com`
- SMTP Port:
  - `465` for SSL
  - `587` for STARTTLS
- SMTP Username: your email address
- SMTP Password: app password or authorization code
- From: sender email address
- To: receiver email address

Multiple recipients can be separated by commas:

```text
a@example.com, b@example.com
```

---

## 💻 Ch.10 Local Desktop Notifications

Local notifications are supported on:

- macOS
- Windows
- Linux

### macOS

Toyoko Tracker tries:

1. `terminal-notifier`, if installed
2. `osascript` fallback

Optional macOS helper:

```bash
brew install terminal-notifier
```

If notifications do not appear:

1. Open **System Settings**
2. Go to **Notifications**
3. Allow notifications for Terminal, Python, or osascript

You can test local notifications in the WebUI:

```text
Push Settings → Local → Test Notification
```

### Windows

Toyoko Tracker uses PowerShell NotifyIcon balloon notifications.

### Linux

Toyoko Tracker tries to use:

```bash
notify-send
```

---

## 🖥 Ch.11 Web Interface Guide

### 11.1 Main Sections

The WebUI contains:

- Search conditions
- Area hotel picker
- Search history
- Search settings
- Push settings
- Run control
- Search results
- Notification status
- Live logs

---

### 11.2 Control Buttons

- **Start**  
  Start monitoring with current settings. Current settings are automatically saved.

- **Stop**  
  Stop monitoring.

- **Default**  
  Reset basic search settings to default values.

- **Load Hotels**  
  Load hotels from selected region/detail area.

- **Select All**  
  Select all loaded hotels.

- **Select None**  
  Clear selected hotels.

- **Refresh History**  
  Reload search history.

- **Clear History**  
  Delete saved search history.

- **Test Notification**  
  Send a local notification test.

---

### 11.3 Status Panel

The status panel shows:

- Running / stopped state
- Scan round count
- Current progress
- Round elapsed time
- Total uptime
- Current action
- Waiting/scanning phase

---

### 11.4 Results Table

The results table shows:

- Hotel code
- Hotel name
- Status
- Minimum price
- Remaining rooms
- Room type

Status meaning:

- ✅ Available
- ❌ Unavailable
- ❓ Unknown / needs check
- ❗ Room type requirement not met

The tracker displays the cheapest matching offer for each room type and automatically ignores special rooms such as heartful / accessible rooms.

---

### 11.5 Notification Status Panel

The notification status panel shows each channel:

- Telegram
- Local notification
- Email
- Bark
- Server Chan

Each channel may show:

- Disabled
- Waiting
- Pushing
- Success
- Failed

---

## 🗂 Ch.12 Configuration Files

Toyoko Tracker saves configuration files in the user configuration directory.

### macOS

```text
~/Library/Application Support/toyoko-tracker/
```

### Windows

```text
%APPDATA%\toyoko-tracker\
```

### Linux

```text
~/.config/toyoko-tracker/
```

Main files:

```text
auto_save.json
save.json
search_history.json
```

You can override the config directory with:

```bash
TOYOKO_TRACKER_CONFIG_DIR=/path/to/config toyoko-tracker
```

---

## 🧪 Ch.13 Troubleshooting

### 13.1 Command not found

If `toyoko-tracker` is not found, try:

```bash
python -m toyoko_tracker
```

or reinstall:

```bash
pip install --upgrade toyoko-tracker
```

---

### 13.2 Playwright engine is disabled

Install Chromium:

```bash
playwright install chromium
```

Then restart Toyoko Tracker.

---

### 13.3 Email not received

Check:

- Spam / junk folder
- SMTP host and port
- App password / authorization code
- Whether SMTP service is enabled
- Whether the sender account blocks third-party clients

---

### 13.4 Telegram push failed

Check:

- Bot Token
- Chat ID
- Whether you have started the bot
- Whether the bot has group permission

---

### 13.5 Local notification not shown on macOS

Try:

```bash
brew install terminal-notifier
```

Then allow notifications in:

```text
System Settings → Notifications
```

---

## 📦 Ch.14 Upgrade

Upgrade from PyPI:

```bash
pip install --upgrade toyoko-tracker
```

Check installed version:

```bash
toyoko-tracker
```

The version is shown at the bottom of the WebUI.

---

## License

MIT License
