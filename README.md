# Toyoko Inn Room Vacancy Tracker

[![PyPI version](https://badge.fury.io/py/toyoko-tracker.svg)](https://pypi.org/project/toyoko-tracker/)

A lovely room availability tracker for [Toyoko Inn](https://www.toyoko-inn.com/), powered by Flask + Selenium.

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

- 默认会运行一个本地 Web 服务： (http://127.0.0.1:4170)  
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
