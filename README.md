# Toyoko Inn Room Vacancy Tracker WebUI

*A lovely room availability tracker for [Toyoko Inn](https://www.toyoko-inn.com/), powered by Flask + Selenium + Playwright.*

🌏 [📖 中文说明书 (Chinese Guide)](./README_zh.md)

---

## ✨ Features Overview

- 🏨 Real-time tracking of Toyoko Inn hotel availability  
- 🌐 Web-based interface with live results  
- 🔔 Multi-channel notifications: Telegram, Email, and Local  
- 🧠 Filters: room requirement, budget, per-hotel delay, repeat rules  
- 🧾 Input hotel codes or names (auto-map to 5-digit codes)  
- ⚙️ Proxy & interval customization  
- 💾 Auto-save and load configuration  
- 🧩 Built-in Playwright renderer for better compatibility  

---

# 📘 User Guide

## Ch.1 Installation & Getting Started

### 1.1 Introduction

**Toyoko Tracker** is a desktop + web tool based on **Flask** and **Playwright**, designed to automatically check **Toyoko Inn** hotel room availability.

Supported features:
- 🌐 Real-time web interface  
- 🤖 Telegram Bot push  
- 📧 SMTP email notification  
- 🧭 Customizable room filters and interval rules  

---

### 1.2 Installation

#### Requirements
- Python **3.9+** (Recommended 3.10 / 3.11)
- Internet connection  
- Chromium (installed automatically by Playwright)

#### Optional
- Google Chrome browser (for Selenium compatibility)

#### Terminal / Command Line Access
- **Windows:** Press `Win + R` → type `cmd` → Enter  
  (or open *PowerShell* from Start Menu)
- **MacOS:** Open *Launchpad* → search **Terminal**
- **Linux:** Press `Ctrl + Alt + T` or search **Terminal**

#### Installation Command
```bash
pip install --upgrade pip
```
```bash
pip install toyoko-tracker
```
```bash
playwright install chromium
```

---

### 1.3 Usage

Run the tracker in your terminal:
```bash
toyoko-tracker
```

Once started:
- Access via [http://127.0.0.1:4170](http://127.0.0.1:4170)
- The browser opens automatically (if not, open manually)

---

### 1.4 Version Info

- **Current version:** `v0.4.18`  
- **Author:** JellyNeko (bilibili @果冻猫猫丶)  
- **License:** MIT  

---

## 🏨 Ch.2 Getting Hotel 5-Digit Codes

Before monitoring, you need the hotel’s **5-digit code**.

### 2.1 Search by Hotel Name on Google
1. Search the full hotel name, e.g.  
   `Toyoko Inn Shin-yokohama Ekimae Shinkan`
2. Open the official Toyoko Inn link:  
   `https://www.toyoko-inn.com/eng/search/detail/00061/`
3. The `00061` part is the **hotel code**.

### 2.2 From Booking URL
When you search on Toyoko Inn’s booking page, you’ll see URLs like:  
```
https://www.toyoko-inn.com/eng/search/result/room_plan/?hotel=00061&start=2025-10-13&end=2025-10-14
```
Here, `hotel=00061` indicates the hotel code.

---

## 🤖 Ch.3 Telegram Bot Setup

To receive Telegram alerts, configure your bot:

### 3.1 Create a Bot
1. Open **BotFather** in Telegram  
2. Send `/newbot`  
3. Follow prompts:
   - Bot name (e.g. `ToyokoBot`)
   - Username (must end with `bot`)
4. Get your **Bot Token**:
   ```
   1234567890:ABCdefGhIJklmNoPQRstuVWxyZ
   ```

### 3.2 Get Chat ID
1. Open **@userinfobot**  
2. It returns your **Chat ID**, e.g. `987654321`

### 3.3 Configure in Toyoko Tracker
1. In WebUI, open **Settings → Telegram Bot**
2. Enable ✅  
3. Enter your **Bot Token** and **Chat ID**

---

## 📧 Ch.4 Email Notification Setup

Configure your email for SMTP alerts.

### 4.1 Enable SMTP
Examples:
- **Gmail:** Enable “App Passwords” (16-digit)  
- **QQ Mail:** Enable “SMTP Service” → get authorization code  
- **163 Mail:** Enable “SMTP” in settings  

### 4.2 Email Configuration
- SMTP Server: `smtp.gmail.com` / `smtp.qq.com`  
- SMTP Port: `465` or `587`  
- Username: `example@gmail.com`  
- Password: *authorization code*  
- Recipient: your target email  

### 4.3 Enable
1. Enable **Email Notification** ✅  
2. Save and start tracking  
3. When rooms are available, emails will be sent automatically  

---

## 💻 Ch.5 Web Interface Overview

### 5.1 Main Sections
- **Run Settings**
- **Status**
- **Results Table**
- **Controls**

### 5.2 Buttons
- 🟢 **Start:** begin scanning  
- 🔴 **Stop:** stop scanning  
- ⚙️ **Default:** reset configuration  
- 💾 **Save / Load:** manage local configs  
- 🏨 **HotelNameLibUpdate:** open `hotel_scan.py` in new terminal  

### 5.3 Settings Panel
Includes:
- Check-in/out dates  
- Guests & rooms  
- Smoking options  
- Room requirement  
- Budget limit slider  
- Proxy  
- Telegram / Email / Notification rules  

---

## ⏱️ Ch.6 Notification & Delay Rules

**Notification Rules** allow for fine-tuned alerts:

- **Repeat Reminder:** enable re-sending  
- **Max Repeat Count:** 0–99  
- **Repeat Interval:** 30–3600 seconds  
- **Loop Interval:** 5–3600 seconds (⚠️ too short may cause blocking)  
- **Per-Hotel Delay:** 1–30 seconds  

All settings available in *Notification Rules* panel.  

---

## 💰 Ch.7 Room Filtering & Budget

### 7.1 Room Requirement
Select preferred room type:
- No Limit  
- Single  
- Double  
- Twin  

If hotel only has *heartful* or *accessible* rooms → treated as unavailable.

### 7.2 Budget Control
- Toggle “Budget Limit” on/off  
- Adjust price range: ¥0 – ¥30,000  
- Step: ¥1,000  
- Based on **non-member price**

If all room types exceed budget → ❗ mark  
If some rooms fit → ✅ only valid rooms shown  

---

## 📊 Ch.8 Results Table

Displays per-room-type results dynamically:

| Code | Hotel | Result | Price | Left | Type |
|------|--------|---------|--------|-------|------|
| 00061 | Toyoko Inn Shin-Yokohama | ✅ | ¥8,700 (¥8,200) | 3 | Single |
| 00061 | 〃 | ✅ | ¥9,400 (¥9,000) | 2 | Double |

Notes:
- Duplicate room names show only the **lowest price**  
- Hotel name links directly to the official site  
- If only *heartful/accessible* rooms → ❗ mark  

---

## 🔔 Ch.9 Notification Content

When rooms become available:
- **Telegram Message Example:**
  ```
  ✅ Room available at Toyoko Inn Tokyo Station
  - Type: Double
  - Price: ¥8,700
  - URL: https://www.toyoko-inn.com/eng/search/detail/00061/
  ```
- **Email:** contains same formatted summary
- **Local Notification:** displays “Room Available!” popup

---

## 🧩 Ch.10 Troubleshooting

| Issue | Possible Cause | Solution |
|--------|----------------|-----------|
| Browser fails to start | Missing Playwright Chromium | Run `playwright install chromium` |
| Telegram not working | Invalid Chat ID / Token | Recheck BotFather setup |
| Email failed | Wrong SMTP password | Use app password instead |
| Local notification stuck | OS blocked popup | Disable “Focus Assist” / Notification Filter |
| Slow on Windows | Old Python or ChromeDriver | Update Python + remove `chromedriver` |

---

## 📜 License & Links

- License: **MIT**  
- Author: JellyNeko (bilibili @果冻猫猫丶)  
- Homepage: [GitHub Project](https://github.com/JellyNekoNeko/toyoko-tracker)  
