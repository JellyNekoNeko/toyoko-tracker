# Toyoko Inn Room Vacancy Tracker

*A lovely room availability tracker for [Toyoko Inn](https://www.toyoko-inn.com/), powered by Flask + Selenium.*

🌏 [📖 中文说明书](./README_zh.md)


---

# 📘 Toyoko Tracker User Guide  

---

## 🏁 Ch.1 Installation & Startup  

### 📖 1.1 Introduction  

**Toyoko Tracker** is a **Flask + Selenium** based desktop & web tool for automatically checking **Toyoko Inn** hotel room availability, with support for:  

- 🌐 **Web Interface**: Real-time room availability display  
- 🔔 **Local Notifications** (⚠️ MacOS currently unsupported)  
- 🤖 **Telegram Bot Push**  
- 📧 **SMTP Email Alerts**  

---

### 🔧 1.2 Installation  

#### Requirements  
- Python **3.9+** (recommended: 3.10 / 3.11)  
- **Google Chrome Browser** installed (requires ChromeDriver automation)  

#### Install from PyPI  
```bash
pip install toyoko-tracker
```

---

### 🚀 1.3 Usage  

After installation, run in terminal:  
```bash
toyoko-tracker
```  

Once launched:  
- A local web service will start at 👉 [http://127.0.0.1:4170](http://127.0.0.1:4170)  
- The program will attempt to automatically open the browser  
- If it doesn’t, manually visit `127.0.0.1:4170` in your browser  

---

### 📝 1.4 Version Info  

- Current version: `v0.4.17`  
- Author: 果冻猫猫 (bilibili @果冻猫猫丶)  
- License: MIT  

---

## 🤖 Ch.2 Telegram Bot Setup  

To receive room alerts via **Telegram**, you need to configure a bot.  

---

### 🔹 2.1 Create a Telegram Bot  

1. In Telegram, search and open **BotFather**  
2. Send command:  
   ```
   /newbot
   ```
3. Follow instructions to set:  
   - Bot name (e.g., `ToyokoBot`)  
   - Username (must end with `bot`, e.g., `toyokotracker_bot`)  
4. BotFather will return a **Bot Token**:  
   ```
   1234567890:ABCdefGhIJklmNoPQRstuVWxyZ
   ```

---

### 🔹 2.2 Get Chat ID  

Chat ID identifies your Telegram account or group.  

1. In Telegram, search and start **@userinfobot**  
2. It will return your **Chat ID**, e.g.:  
   ```
   987654321
   ```

---

### 🔹 2.3 Configure in Toyoko Tracker  

1. Open Toyoko Tracker web interface  
2. Go to **Telegram Bot Settings**  
3. Enable ✅  
4. Enter **Bot Token** from BotFather  
5. Enter **Chat ID** from @userinfobot  

Now, when rooms are available, Toyoko Tracker will notify you via Telegram.  

---

## 📧 Ch.3 Email Alerts Setup  

To receive **email alerts**, configure an SMTP account.  

---

### 🔹 3.1 Enable SMTP in Your Email  

Examples:  

- **QQ Mail**  
  1. Log into QQ Mail → Settings → Account  
  2. Enable **SMTP service**  
  3. System generates an **authorization code** (⚠️ not your password!)  

- **Gmail**  
  1. Log into Gmail → Manage account → Security  
  2. Enable **Less Secure Apps** or create an **App Password**  
  3. Get a 16-digit App Password  

- **163/126 Mail**  
  1. Log into webmail → Settings → POP3/SMTP/IMAP  
  2. Enable **SMTP service**  
  3. Get an **authorization code**  

---

### 🔹 3.2 Fill in Toyoko Tracker Email Settings  

- **SMTP Server**: e.g. `smtp.qq.com` / `smtp.gmail.com`  
- **SMTP Port**: usually `465` (SSL) or `587` (TLS)  
- **Username**: your email (e.g., `example@gmail.com`)  
- **Password**: the **authorization code**  
- **To Address**: target email to receive alerts  

---

### 🔹 3.3 Enable Email Alerts  

1. Check ✅ **Enable Email**  
2. Fill config and click **Save**  
3. Click **Start** to launch monitoring  
4. When rooms are found, system sends an email  

---

### 🔹 3.4 Tips  

- Recommended: **QQ Mail** or **Gmail** for testing  
- If no mail, check **Spam folder**  
- If auth fails, ensure you used **authorization code** instead of login password  

---

## 💻 Ch.4 Web Interface Operations  

---

### 🔹 4.1 Main Interface  

- Default address: `http://127.0.0.1:4170`  
- Sections:  
  - **Run Settings**  
  - **Status Display**  
  - **Results Table**  
  - **Control Buttons**  

---

### 🔹 4.2 Control Buttons  

- **Start**: Start monitoring & save config to `auto_save.json`  
- **Stop**: Stop monitoring & close driver  
- **Default**: Reset config (today + tomorrow, people = 1, room = 1)  
- **Save**: Save current config to `save.json`  
- **Load**: Load config from `save.json`  

---

### 🔹 4.3 Settings Panel  

1. **Start/End Date**: Check-in/out dates  
2. **People / Rooms**: Input 1–5 people, 1–9 rooms  
3. **Smoking Option**: `noSmoking` / `Smoking` / `all`  
4. **Hotel Code**: multiple 5-digit codes allowed (comma or space separated)  
5. **Proxy Settings**: e.g. `http://127.0.0.1:7890`  
6. **Telegram**: Bot Token & Chat ID  
7. **Local Notifications**: enable (⚠️ MacOS unsupported)  
8. **Email Notifications**: SMTP config  

---

### 🔹 4.4 Status Display  

- **Round**: Current round  
- **Progress Bar**: Completed vs total  
- **Elapsed / Uptime**: Time for this round & total uptime  
- **Current Action**: Current task (e.g. "Checking hotel 00061")  

---

### 🔹 4.5 Results Table  

- **Code**: Hotel code  
- **HotelName**: Hotel name  
- **Result**: ✅ Available / ❌ Not Available / ❓ Unknown  
- **MinPrice**: Lowest non-member price  
- **Left**: Remaining rooms (`Reserve` = ≥10)  
- **Type**: Room type  

> Special room types (such as *heartful* / *accessible*) are automatically ignored due to hotel reservation policies.




