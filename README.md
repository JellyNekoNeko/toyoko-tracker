# Toyoko Inn Room Vacancy Tracker

*A lovely room availability tracker for [Toyoko Inn](https://www.toyoko-inn.com/), powered by Flask + Selenium.*

🌏 [📖 中文说明书](./README.md)

---

# 📘 Toyoko Tracker User Guide

## Ch.1 Installation & Startup

### 1.1 Introduction

**Toyoko Tracker** is a desktop and web tool based on **Flask + Selenium** that automatically monitors room availability for **Toyoko Inn** hotels, with support for:

- 🌐 Real-time room status via a web interface  
- 🔔 Local notifications (⚠️ macOS notifications temporarily unavailable)  
- 🤖 Telegram bot push notifications  
- 📧 SMTP email alerts  

---

### 1.2 Installation

#### Requirements
- Python **3.9+** (recommended: 3.10 / 3.11)  
- Installed **Google Chrome Browser** (program depends on ChromeDriver automation)  

#### Install from PyPI
```bash
pip install toyoko-tracker
```

---

### 1.3 Usage

After installation, run in terminal:

```bash
toyoko-tracker
```

Once started:

- A local web service will run at: [http://127.0.0.1:4170](http://127.0.0.1:4170)  
- The program will attempt to open this URL in your browser automatically  
- If it doesn’t, you can manually visit `127.0.0.1:4170`  

---

### 1.4 Version Info

- Current version: `v0.4.17`  
- Author: 果冻猫猫 (bilibili @果冻猫猫丶)  
- License: MIT  

---

## Ch.2 Telegram Bot Setup

To receive room availability alerts via Telegram, you’ll need to configure a bot.

---

### 2.1 Create a Telegram Bot

1. In Telegram, search and open **BotFather**  
2. Send the command:  
   ```
   /newbot
   ```
3. Follow the prompts:  
   - Bot name (e.g., `ToyokoBot`)  
   - Username (must end with `bot`, e.g., `toyokotracker_bot`)  
4. Once created, BotFather will give you a **Bot Token**:  
   ```
   1234567890:ABCdefGhIJklmNoPQRstuVWxyZ
   ```

---

### 2.2 Get Your Chat ID

The Chat ID uniquely identifies a user or group in Telegram. You’ll need it to specify where alerts should be sent.

Steps:

1. In Telegram, search and start **@userinfobot**  
2. It will reply with your **Chat ID**, e.g.:  
   ```
   987654321
   ```

---

### 2.3 Configure in Toyoko Tracker

1. Open the Toyoko Tracker web interface  
2. In the settings panel, find **Telegram Bot**  
3. Enable it ✅  
4. Enter the **Bot Token** from BotFather  
5. Enter your **Chat ID** from @userinfobot  

Once configured, the system will automatically send Telegram messages when rooms become available.  
If previously available rooms become unavailable, the system will also notify you.  

---

## Ch.3 Email Alerts Setup

You can also receive room availability alerts by email via SMTP.

---

### 3.1 Enable SMTP for Your Email

Setup depends on your email provider:  

- **Gmail**  
  1. Log in to Gmail → Manage Account → Security  
  2. Enable “Allow less secure apps” (or use an **App Password**)  
  3. Generate a 16-digit **App Password**  

---

### 3.2 Configure Email Settings in Toyoko Tracker

In the web interface under **Email Settings**, fill in:  

- **SMTP Server**: e.g., `smtp.gmail.com`  
- **SMTP Port**: typically `465` (SSL) or `587` (TLS)  
- **Username**: your email address, e.g., `example@gmail.com`  
- **Password**: your **App Password** (not your email login password)  
- **To Address**: the email address where you want to receive alerts  

---

### 3.3 Enable Email Alerts

1. In the web interface, check **Enable Email** ✅  
2. Fill in the settings and click **Save**  
3. Click **Start** to begin monitoring  
4. The system will send an email when rooms are available  

---

### 3.4 Notes

- Recommended to test with **Gmail**  
- Check your **spam folder** if no emails arrive  
- If authentication fails, make sure you entered the **App Password**, not your login password  
