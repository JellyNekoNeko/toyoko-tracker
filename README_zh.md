# 📘 Toyoko Tracker 使用说明书  

---

## 🏁 Ch.1 安装与启动  

### 📖 1.1 简介  

**Toyoko Tracker** 是一个基于 **Flask + Selenium** 的桌面与 Web 工具，用来自动检测 **东横 INN** 酒店房间空余情况，并支持：  

- 🌐 **Web 界面**：实时查看房源状况  
- 🔔 **本地通知**（⚠️ MacOS 本地通知暂不可用）  
- 🤖 **Telegram 机器人推送**  
- 📧 **SMTP 邮件提醒**  

---

### 🔧 1.2 安装  

#### 系统要求  
- Python **3.9+**（推荐 3.10 / 3.11）  
- 已安装 **Google Chrome 浏览器**（依赖 ChromeDriver 自动化）  

#### 从 PyPI 安装  
```bash
pip install toyoko-tracker
```

---

### 🚀 1.3 使用方法  

安装完成后，在命令行输入：  
```bash
toyoko-tracker
```  

启动后：  
- 默认会运行一个本地 Web 服务： 👉 [http://127.0.0.1:4170](http://127.0.0.1:4170)  
- 程序会尝试自动打开浏览器访问此界面  
- 如果没有自动打开，可以手动在浏览器输入 `127.0.0.1:4170`  

---

### 📝 1.4 版本信息  

- 当前版本：`v0.4.17`  
- 作者：果冻猫猫 (bilibili @果冻猫猫丶)  
- 开源协议：MIT  

---

## 🤖 Ch.2 Telegram Bot 配置  

为了通过 Telegram 接收房源提醒，你需要先配置一个机器人。  

---

### 🔹 2.1 创建 Telegram Bot  

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

### 🔹 2.2 获取 Chat ID  

Chat ID 是 Telegram 中标识用户或群的唯一 ID，用来指定推送的目标。  

1. 在 Telegram 搜索并启动 **@userinfobot**  
2. 它会直接告诉你当前账号的 **Chat ID**，格式类似：  
   ```
   987654321
   ```

---

### 🔹 2.3 配置到 Toyoko Tracker  

1. 打开 Toyoko Tracker 的 Web 界面  
2. 在设置面板中找到 **Telegram Bot** 部分  
3. 勾选启用 ✅  
4. 填入 **BotFather 提供的 Bot Token**  
5. 填入 **@userinfobot 提供的 Chat ID**  

完成后，当有房间可订时，系统会自动推送提醒消息。  

---

## 📧 Ch.3 邮件推送配置  

通过 **邮箱** 接收房源提醒，需要配置一个 SMTP 邮件发送账号。  

---

### 🔹 3.1 开启邮箱 SMTP 服务  

不同邮箱服务商配置方式：  

- **QQ 邮箱**  
  1. 登录 QQ 邮箱网页版 → 设置 → 账户  
  2. 找到「SMTP 服务」并开启  
  3. 系统会生成一个 **授权码**（⚠️ 不是邮箱密码！）  

- **Gmail**  
  1. 登录 Gmail → 管理账户 → 安全性  
  2. 开启「允许低安全性应用访问」或使用 **应用专用密码**  
  3. 获取一个 16 位的 **应用专用密码**  

- **163/126 邮箱**  
  1. 登录邮箱 → 设置 → POP3/SMTP/IMAP  
  2. 开启「SMTP 服务」  
  3. 获取 **授权码**  

---

### 🔹 3.2 填写邮件配置  

在 Web 界面的 **Email Settings** 中填写：  

- **SMTP Server**：如 `smtp.qq.com` / `smtp.gmail.com`  
- **SMTP Port**：`465`（SSL）或 `587`（TLS）  
- **Username**：邮箱地址（如 `example@qq.com`）  
- **Password**：邮箱生成的 **授权码**  
- **To Address**：接收提醒的邮箱  

---

### 🔹 3.3 启用邮件提醒  

1. 在 Web 界面勾选 **Enable Email** ✅  
2. 填写配置后点击 **Save**  
3. 点击 **Start** 启动监控  
4. 有房间可订时会自动发送邮件  

---

### 🔹 3.4 提示  

- 推荐使用 **QQ 邮箱** 或 **Gmail** 测试  
- 如果没收到邮件，请检查 **垃圾邮箱**  
- 若提示认证失败，请确认填写的是 **授权码** 而非邮箱密码  

---

## 💻 Ch.4 界面操作  

介绍 Toyoko Tracker 启动后的 **Web 界面操作**。  

---

### 🔹 4.1 主界面  

- 启动后打开 `http://127.0.0.1:4170`  
- 页面包含：  
  - **运行配置 (Run Settings)**  
  - **状态显示 (Status)**  
  - **结果表格 (Results Table)**  
  - **操作按钮 (Controls)**  

---

### 🔹 4.2 操作按钮  

- **启动 Start**：开始检测，并保存配置到 `auto_save.json`  
- **停止 Stop**：停止检测并关闭浏览器驱动  
- **默认 Default**：恢复默认配置（日期 = 今天 + 明天，人数 = 1，房间 = 1）  
- **保存 Save**：保存当前配置到 `save.json`  
- **读取 Load**：从 `save.json` 读取配置并应用  

---

### 🔹 4.3 配置面板  

1. **入住/退房日期**：选择日期  
2. **人数 / 房间数**：输入范围（1–5 人，1–9 间）  
3. **吸烟选项**：`noSmoking` / `Smoking` / `all`  
4. **酒店编号**：支持多个 5 位编号，用逗号或空格分隔  
5. **代理设置**：可启用代理（如 `http://127.0.0.1:7890`）  
6. **Telegram 配置**：输入 Bot Token 与 Chat ID  
7. **本地通知**：可启用（⚠️ MacOS 暂不可用）  
8. **邮件通知**：填写 SMTP 配置  

---

### 🔹 4.4 状态显示  

- **Round**：检测轮次  
- **进度条**：进度展示  
- **Elapsed / Uptime**：本轮用时 & 总运行时间  
- **Current Action**：当前执行任务（如「正在检查 00061 酒店」）  

---

### 🔹 4.5 结果表格  

- **编号 Code**：酒店代码  
- **酒店名 HotelName**：酒店名称  
- **结果 Result**：✅ 有房 / ❌ 无房 / ❓ 未知  
- **最低价 MinPrice**：最低非会员价  
- **剩余 Left**：剩余房间数（`Reserve` = ≥10）  
- **房型 Type**：对应房型  

> ⚠️ 特殊房型（如 *heartful* / *accessible*）会自动忽略。  
