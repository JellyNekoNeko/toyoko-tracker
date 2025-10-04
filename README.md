# Toyoko Inn Room Vacancy Tracker

*A lovely room availability tracker for [Toyoko Inn](https://www.toyoko-inn.com/), powered by Flask + Selenium.*

🌏 [📖 中文说明书](./README_zh.md)


---

# 📘 Toyoko Tracker User Guide

## Ch.1 Installation & Getting Started

### 1.1 Introduction

**Toyoko Tracker** is a **Flask + Selenium** based desktop and web tool designed to automatically check **Toyoko Inn** hotel room availability, with support for:

- 🌐 Web interface for real-time room availability  
- 🔔 Local notifications (⚠️ MacOS notifications currently not supported)  
- 🤖 Telegram Bot push  
- 📧 SMTP Email alerts  

---

### 1.2 Installation

#### Requirements
- Python **3.9+** (Recommended 3.10 / 3.11)  
- Installed **Google Chrome Browser** (the tool relies on ChromeDriver for automation)  

#### Install from PyPI

- Windows: Press Win + R, type cmd, then press Enter. This will open the Command Prompt window where you can enter commands. Alternatively, click the Start menu → search for PowerShell → open Windows PowerShell.
- MacOS: Open Launchpad, search for and click Terminal, then you can enter commands.
- Linux: Press Ctrl + Alt + T to automatically open the terminal. You can also search for Terminal in the applications menu.

Run the following commands to complete the installation:

```bash
pip install --upgrade pip
pip install toyoko-tracker
```

---

### 1.3 Usage

After installation, run the following in your terminal:

```bash
toyoko-tracker
```

After launching:

- A local web server will run at: [http://127.0.0.1:4170](http://127.0.0.1:4170)  
- The program will try to automatically open the browser  
- If it doesn’t, open the browser manually and enter `127.0.0.1:4170`  

---

### 1.4 Version Info

- Current version: `v0.4.17`  
- Author: JellyNeko (bilibili @果冻猫猫丶)  
- License: MIT  

---

## 🏨 Ch.2 Getting Hotel 5-Digit Codes

Before using Toyoko Tracker, you need the **5-digit hotel code**.  
This code is used on the Toyoko Inn official website to uniquely identify each hotel.  

### 🔹 2.1 Search by Hotel Name on Google

1. Search the full hotel name on Google, for example:  
   ```
   Toyoko Inn Shin-yokohama Ekimae Shinkan
   ```  
2. You will usually see the official Toyoko Inn booking page, such as:  
   ```
   https://www.toyoko-inn.com/eng/search/detail/00061/
   ```  
3. In this link, **00061** is the hotel code.  

---

### 🔹 2.2 From the Booking URL

When you search on the official Toyoko Inn website with check-in and check-out dates, you will see a booking results page like this:  
```
https://www.toyoko-inn.com/eng/search/result/room_plan/?hotel=00061&start=2025-10-13&end=2025-10-14&room=1&people=1
```  

Here, the parameter `hotel=00061` indicates the hotel code.  

---

## 🤖 Ch.3 Telegram Bot Setup

To receive availability alerts via Telegram, you need to configure a bot.  

### 3.1 Create a Telegram Bot

1. Search and open **BotFather** in Telegram  
2. Send the command:  
   ```
   /newbot
   ```  
3. Follow the prompts:  
   - Bot name (e.g. `ToyokoBot`)  
   - Username (must end with `bot`, e.g. `toyokotracker_bot`)  
4. BotFather will provide a **Bot Token**:  
   ```
   1234567890:ABCdefGhIJklmNoPQRstuVWxyZ
   ```  

### 3.2 Get Chat ID

Chat ID is the unique identifier for your Telegram account or group.  

Method:  

1. Search and start **@userinfobot** in Telegram  
2. It will show your current account’s **Chat ID**, for example:  
   ```
   987654321
   ```  

### 3.3 Configure in Toyoko Tracker

1. Open the Toyoko Tracker web interface  
2. Locate the **Telegram Bot** section in the settings panel  
3. Enable it ✅  
4. Enter the **Bot Token** from BotFather  
5. Enter your **Chat ID** from @userinfobot  

Once configured, Toyoko Tracker will automatically send messages via Telegram when rooms are available.  

---

## 📧 Ch.4 Email Notification Setup

To receive alerts via **email**, you need to configure an SMTP account.  

### 4.1 Enable SMTP Service

Steps vary by provider:  

- **Gmail**  
  1. Log in → Manage account → Security  
  2. Enable “Allow less secure apps” or use **App Passwords**  
  3. Get a 16-digit **App Password**  

- **QQ Mail**  
  1. Log in → Settings → Account  
  2. Enable “SMTP Service”  
  3. Get an **authorization code** (not your login password)  

- **163/126 Mail**  
  1. Log in → Settings → POP3/SMTP/IMAP  
  2. Enable “SMTP Service”  
  3. Get an **authorization code**  

### 4.2 Fill in Email Settings in Toyoko Tracker

In the **Email Settings** section:  

- **SMTP Server**: e.g. `smtp.gmail.com` / `smtp.qq.com`  
- **SMTP Port**: usually `465` (SSL) or `587` (TLS)  
- **Username**: your email address, e.g. `example@gmail.com`  
- **Password**: the **authorization code** or **app password**  
- **To Address**: the recipient email address  

### 4.3 Enable Email Alerts

1. Check **Enable Email** ✅ in the web interface  
2. Save your configuration  
3. Click **Start** to begin monitoring  
4. When rooms are found, emails will be automatically sent  

### 4.4 Tips

- Recommended: Gmail or QQ Mail for testing  
- Check your **spam/junk folder** if emails don’t arrive  
- Ensure you used the **authorization code** or **app password**, not your login password  

---

## 💻 Ch.5 Web Interface Guide

This chapter explains the **web interface** after launching Toyoko Tracker.  

### 5.1 Main Interface

- Default: opens at `http://127.0.0.1:4170`  
- Sections include:  
  - **Run Settings**  
  - **Status**  
  - **Results Table**  
  - **Controls**  

### 5.2 Control Buttons

- **Start**: begin monitoring and save config to `auto_save.json`  
- **Stop**: stop monitoring and close browser driver  
- **Default**: reset to default config (today+tomorrow, 1 person, 1 room)  
- **Save**: save config to `save.json` (manual save)  
- **Load**: load config from `save.json`  

### 5.3 Settings Panel

1. **Check-in/Check-out Dates**  
2. **Guests / Rooms** (1–5 people, 1–9 rooms)  
3. **Smoking Options**:  
   - `noSmoking` (non-smoking)  
   - `Smoking` (smoking)  
   - `all` (any)  
4. **Hotel Code(s)**: multiple 5-digit codes separated by comma or space  
5. **Proxy Settings**: e.g. `http://127.0.0.1:7890`  
6. **Telegram Settings**: Bot Token & Chat ID  
7. **Local Notifications**: enable (⚠️ MacOS may not work)  
8. **Email Notifications**: SMTP server, port, account, password  

### 5.4 Status Panel

Shows real-time status:  

- **Round**: iteration count  
- **Progress Bar**: current vs total  
- **Elapsed / Uptime**: round time & total runtime  
- **Current Action**: e.g. “Checking hotel 00061”  

### 5.5 Results Table

Displays the latest scan results:  

- **Code**: hotel code  
- **HotelName**: hotel name  
- **Result**: ✅ available / ❌ unavailable / ❓ unknown  
- **MinPrice**: lowest non-member price  
- **Left**: remaining rooms 
- **Type**: room type  

> Special room types (such as *heartful* / *accessible*) are automatically ignored due to hotel reservation policies.




