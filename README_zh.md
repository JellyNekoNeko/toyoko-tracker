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
pip install --upgrade pip
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

## 🏨 Ch.2 获取酒店 5 位编码  

在使用 Toyoko Tracker 之前，你需要准备 **酒店的 5 位数编码**。这个编码是东横 INN 官网用于区分不同酒店的唯一标识。  

---

### 🔹 2.1 通过 Google 搜索酒店名称  

1. 在 Google 搜索完整的酒店名字，例如：  
   ```
   Toyoko Inn Shin-yokohama Ekimae Shinkan
   ```  
2. 通常会在搜索结果中出现东横 INN 的官方网站链接，例如：  
   ```
   https://www.toyoko-inn.com/eng/search/detail/00061/
   ```  
3. 在这个链接中，**00061** 就是该酒店的编码。  

---

### 🔹 2.2 从搜索结果 URL 中获取  

当你在官网输入入住日期和条件后，跳转到搜索结果页面：  
```
https://www.toyoko-inn.com/eng/search/result/room_plan/?hotel=00061&start=2025-10-13&end=2025-10-14&room=1&people=1
```  

此处的 `hotel=00061` 就是酒店编码。  

---

## 🤖 Ch.3 Telegram Bot 配置

为了通过 Telegram 接收房源提醒，你需要先配置一个机器人。  

### 3.1 创建 Telegram Bot

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

### 3.2 获取 Chat ID

Chat ID 是 Telegram 中标识用户或群的唯一 ID，用来指定推送的目标。  

方法：

1. 在 Telegram 搜索并启动 **@userinfobot**  
2. 它会直接告诉你当前账号的 **Chat ID**，格式类似：  
   ```
   987654321
   ```  

### 3.3 配置到 Toyoko Tracker

1. 打开 Toyoko Tracker 的 Web 界面  
2. 在设置面板中找到 **Telegram Bot** 部分  
3. 勾选启用 ✅  
4. 填入 BotFather 给的 **Bot Token**  
5. 填入你通过 @userinfobot 获取的 **Chat ID**  

这样，当有房间可订时，系统就会自动通过 Telegram 向你推送消息。  

---

## 📧 Ch.4 邮件推送配置

为了通过 **邮箱** 接收房源提醒，你需要配置一个 SMTP 邮件发送账号。  

### 4.1 开启邮箱 SMTP 服务

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

### 4.2 填写 Toyoko Tracker 邮件配置

在 Web 界面的 **Email Settings** 中填写以下内容：  

- **SMTP Server**：例如 `smtp.qq.com` / `smtp.gmail.com`  
- **SMTP Port**：通常为 `465`（SSL）或 `587`（TLS）  
- **Username**：你的邮箱地址，例如 `example@qq.com`  
- **Password**：邮箱生成的 **授权码**（不是邮箱登录密码）  
- **To Address**：你希望接收提醒的邮箱地址  

### 4.3 启用邮件提醒

1. 在 Web 界面勾选 **Enable Email** ✅  
2. 填写完配置后点击 **Save** 保存  
3. 点击 **Start** 启动监控  
4. 当检测到房间空余时，系统会自动发送邮件通知  

### 4.4 提示

- 推荐使用 **QQ 邮箱** 或 **Gmail** 测试  
- 如果邮件没有收到，请检查 **垃圾邮箱**  
- 若提示认证失败，请确认是否填写了 **授权码** 而不是邮箱密码  

---

## 💻 Ch.5 界面操作

本章介绍 Toyoko Tracker 启动后的 **Web 界面操作**。  

### 5.1 主界面

- 启动后，默认打开 `http://127.0.0.1:4170`。  
- 页面包含：  
  - **运行配置 (Run Settings)**  
  - **状态显示 (Status)**  
  - **结果表格 (Results Table)**  
  - **操作按钮 (Controls)**  

### 5.2 操作按钮

- **启动 Start**：开始后台房源检测，并保存当前配置到 `auto_save.json`。  
- **停止 Stop**：停止检测并关闭浏览器驱动。  
- **默认 Default**：恢复为默认配置（日期为今天 + 明天，人数 = 1，房间 = 1）。  
- **保存 Save**：保存当前配置到 `save.json`（手动保存）。  
- **读取 Load**：从 `save.json` 读取配置并应用到界面。  

### 5.3 配置面板

1. **入住/退房日期**：选择开始和结束日期。  
2. **人数 / 房间数**：输入 1–5 人，1–9 间。  
3. **吸烟选项**：可选择  
   - `noSmoking` 无烟房  
   - `Smoking` 吸烟房  
   - `all` 不限  
4. **酒店编号**：支持多个 5 位编号，用逗号或空格分隔。  
5. **代理设置**：可启用代理（如 `http://127.0.0.1:7890`）。  
6. **Telegram 配置**：输入 Bot Token 与 Chat ID。  
7. **本地通知**：勾选启用（⚠️ MacOS 当前可能不可用）。  
8. **邮件通知**：输入 SMTP 服务器、端口、邮箱、授权码等信息。  

### 5.4 状态显示

界面中部提供实时状态显示：  

- **Round**：检测轮次  
- **进度条**：当前进度与总数  
- **Elapsed / Uptime**：本轮用时 & 总运行时间  
- **Current Action**：正在执行的任务

### 5.5 结果表格

表格实时展示最新的检测结果：  

- **编号 Code**：酒店代码  
- **酒店名 HotelName**：酒店名称  
- **结果 Result**：✅ 有房 / ❌ 无房 / ❓ 未知  
- **最低价 MinPrice**：最低非会员价  
- **剩余 Left**：剩余房间数 
- **房型 Type**：对应房间类型  

> ⚠️ 特殊房型（如 *heartful* / *accessible*）会自动忽略。  
