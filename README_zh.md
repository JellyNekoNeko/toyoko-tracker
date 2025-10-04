# 📘 Toyoko Tracker 使用说明书

## Ch.1 安装与启动

### 1.1 简介

**Toyoko Tracker** 是一个基于 **Flask + Selenium** 的桌面与 Web 工具，用来自动检测 **东横 INN** 酒店房间空余情况，并支持：

- 🌐 Web 界面实时查看房源状况  
- 🔔 本地通知（⚠️ MacOS 本地通知暂不可用）  
- 🤖 Telegram 机器人推送  
- 📧 SMTP 邮件提醒  

---

### 1.2 安装

#### 系统要求
- Python **3.9+**（推荐 3.10 / 3.11）  
- 已安装 **Google Chrome 浏览器**（程序依赖 ChromeDriver 自动化）  

#### 从 PyPI 安装
```bash
pip install toyoko-tracker
```

---

### 1.3 使用方法

安装完成后，在命令行输入：

```bash
toyoko-tracker
```

启动后：

- 默认会运行一个本地 Web 服务： [http://127.0.0.1:4170](http://127.0.0.1:4170)  
- 程序会尝试自动打开浏览器访问此界面  
- 如果没有自动打开，可以手动在浏览器输入 `127.0.0.1:4170`  

---

### 1.4 版本信息

- 当前版本：`v0.4.17`  
- 作者：果冻猫猫 (bilibili @果冻猫猫丶)  
- 开源协议：MIT  

---

## Ch.2 Telegram Bot 配置

为了通过 Telegram 接收房源提醒，你需要先配置一个机器人。

---

### 2.1 创建 Telegram Bot

1. 在 Telegram 搜索并打开 **BotFather**  
2. 发送命令：  
   ```
   /newbot
   ```
3. 按提示输入：  
   - 机器人名称（例如：`ToyokoBot`）  
   - 用户名（必须以 `bot` 结尾，例如：`toyokotracker_bot`）  
4. 创建完成后，BotFather 会返回一个 **Bot Token**：  
   ```
   1234567890:ABCdefGhIJklmNoPQRstuVWxyZ
   ```

---

### 2.2 获取 Chat ID

Chat ID 是 Telegram 中标识用户或群的唯一 ID，用来指定推送的目标。

方法：

1. 在 Telegram 搜索并启动 **@userinfobot**  
2. 它会直接告诉你当前账号的 **Chat ID**，格式类似：  
   ```
   987654321
   ```

---

### 2.3 配置到 Toyoko Tracker

1. 打开 Toyoko Tracker 的 Web 界面  
2. 在设置面板中找到 **Telegram Bot** 部分  
3. 勾选启用 ✅  
4. 填入 BotFather 给的 **Bot Token**  
5. 填入你通过 @userinfobot 获取的 **Chat ID**  

这样，当有房间可订时，系统就会自动通过 Telegram 向你推送消息。  

---

## Ch.3 邮件推送配置

为了通过 **邮箱** 接收房源提醒，你需要配置一个 SMTP 邮件发送账号。  

---

### 3.1 开启邮箱 SMTP 服务

不同邮箱服务商的配置方式略有不同：  

- **QQ 邮箱**  
  1. 登录 QQ 邮箱网页版 → 设置 → 账户  
  2. 找到「SMTP 服务」并开启  
  3. 系统会生成一个 **授权码**（不是你的邮箱密码！）  

- **Gmail**  
  1. 登录 Gmail → 管理账户 → 安全性  
  2. 开启「允许低安全性应用访问」或使用 **应用专用密码**  
  3. 获取一个 16 位的 **应用专用密码**  

- **163/126 邮箱**  
  1. 登录邮箱 → 设置 → POP3/SMTP/IMAP  
  2. 开启「SMTP 服务」  
  3. 获取 **授权码**  

---

### 3.2 填写 Toyoko Tracker 邮件配置

在 Web 界面的 **Email Settings** 中填写以下内容：  

- **SMTP Server**：例如 `smtp.qq.com` / `smtp.gmail.com`  
- **SMTP Port**：通常为 `465`（SSL）或 `587`（TLS）  
- **Username**：你的邮箱地址，例如 `example@qq.com`  
- **Password**：邮箱生成的 **授权码**（不是邮箱登录密码）  
- **To Address**：你希望接收提醒的邮箱地址  

---

### 3.3 启用邮件提醒

1. 在 Web 界面勾选 **Enable Email** ✅  
2. 填写完配置后点击 **Save** 保存  
3. 点击 **Start** 启动监控  
4. 当检测到房间空余时，系统会自动发送邮件通知  

---

### 3.4 提示

- 推荐使用 **QQ 邮箱** 或 **Gmail** 测试  
- 如果邮件没有收到，请检查 **垃圾邮箱**  
- 若提示认证失败，请确认是否填写了 **授权码** 而不是邮箱密码  
