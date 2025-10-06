# 东横INN 空房追踪器 WebUI

*一个可爱的 [东横INN](https://www.toyoko-inn.com/) 酒店空房监控工具，基于 Flask + Selenium + Playwright 构建。*

🌏 [📖 English Guide (英文说明书)](./README.md)

---

## ✨ 功能概览

- 🏨 实时追踪东横INN酒店空房情况  
- 🌐 网页界面实时显示结果  
- 🔔 多渠道通知：Telegram、邮箱、本地通知  
- 🧠 支持筛选：房型、预算、单酒店延迟、重复提醒规则  
- 🧾 支持输入酒店代码或名称（自动映射为5位数代码）  
- ⚙️ 支持代理与间隔自定义  
- 💾 自动保存与加载配置  
- 🧩 内置 Playwright 渲染器，兼容性更好  

---

# 📘 使用说明

## 第1章 安装与入门

### 1.1 简介

**Toyoko Tracker（东横追踪器）** 是一个基于 **Flask** 与 **Playwright** 的桌面与网页应用，能够自动检测 **东横INN** 酒店的空房状态。

主要功能：
- 🌐 实时网页界面  
- 🤖 Telegram 推送  
- 📧 邮件提醒  
- 🧭 支持房型与预算筛选、自定义循环间隔  

---

### 1.2 安装说明

#### 必需条件
- Python **3.9+**（推荐 3.10 / 3.11）
- 网络连接  
- Chromium（由 Playwright 自动安装）

#### 可选
- Google Chrome 浏览器（用于 Selenium 兼容）

#### 打开命令行
- **Windows：** 按下 `Win + R` → 输入 `cmd` → 回车  
- **MacOS：** 打开 *Launchpad* → 搜索 **终端**  
- **Linux：** 按 `Ctrl + Alt + T` 或搜索 *Terminal*

#### 安装命令
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

### 1.3 使用方法

运行追踪器：
```bash
toyoko-tracker
```

启动后：
- 打开 [http://127.0.0.1:4170](http://127.0.0.1:4170)  
- 浏览器会自动启动（如未启动，请手动打开）

---

### 1.4 版本信息

- **当前版本：** `v0.4.18`  
- **作者：** JellyNeko (bilibili @果冻猫猫丶)  
- **许可证：** MIT  

---

## 🏨 第2章 获取酒店5位代码

监控前需先获得酒店的 **5位数字代码**。

### 2.1 通过Google搜索
1. 搜索酒店英文名，如：  
   `Toyoko Inn Shin-yokohama Ekimae Shinkan`
2. 打开东横INN官网链接：  
   `https://www.toyoko-inn.com/eng/search/detail/00061/`
3. 其中 `00061` 即为酒店代码。

### 2.2 从预订链接获取
在官网预订页面中：  
```
https://www.toyoko-inn.com/eng/search/result/room_plan/?hotel=00061&start=2025-10-13&end=2025-10-14
```
其中 `hotel=00061` 即代表酒店代码。

---

## 🤖 第3章 Telegram 机器人推送

### 3.1 创建机器人
1. 打开 **BotFather**  
2. 输入 `/newbot`  
3. 按提示设置：
   - 机器人名称（如 `ToyokoBot`）
   - 用户名（需以 `bot` 结尾）  
4. 获取 **Bot Token**：
   ```
   1234567890:ABCdefGhIJklmNoPQRstuVWxyZ
   ```

### 3.2 获取 Chat ID
1. 打开 **@userinfobot**  
2. 返回你的 **Chat ID**（如 `987654321`）

### 3.3 在程序中配置
1. 打开 **设置 → Telegram Bot**  
2. 启用 ✅  
3. 输入 **Bot Token** 与 **Chat ID**  

---

## 📧 第4章 邮件提醒

### 4.1 开启SMTP
示例：  
- **Gmail：** 启用 “App Passwords”（16位代码）  
- **QQ邮箱：** 启用 “SMTP服务” → 获取授权码  
- **163邮箱：** 启用 “SMTP”  

### 4.2 配置示例
- SMTP服务器：`smtp.gmail.com` / `smtp.qq.com`  
- 端口：`465` 或 `587`  
- 用户名：`example@gmail.com`  
- 密码：授权码  
- 收件人：你的邮箱地址  

### 4.3 启用
1. 启用邮件通知 ✅  
2. 保存配置并开始监控  
3. 一旦有空房，将自动发送邮件  

---

## 💻 第5章 网页界面

### 5.1 主界面部分
- **运行设置**
- **状态**
- **结果表格**
- **操作按钮**

### 5.2 按钮说明
- 🟢 **Start：** 开始扫描  
- 🔴 **Stop：** 停止扫描  
- ⚙️ **Default：** 恢复默认设置  
- 💾 **Save / Load：** 保存或加载配置  
- 🏨 **HotelNameLibUpdate：** 打开 `hotel_scan.py`  

### 5.3 设置面板
包含：  
- 入住/退房日期  
- 人数与房间数  
- 吸烟选项  
- 房型与预算限制  
- 代理设置  
- Telegram / 邮件通知规则  

---

## ⏱️ 第6章 通知与延迟规则

- **重复提醒：** 是否重复发送  
- **最大重复次数：** 0–99  
- **重复间隔：** 30–3600秒  
- **循环间隔：** 5–3600秒  
- **单酒店延迟：** 1–30秒  

---

## 💰 第7章 房型与预算

### 7.1 房型要求
可选：不限 / 单人房 / 双人房 / 双床房  
若仅剩 *无障碍房* → 视为无房。

### 7.2 预算控制
- 开启预算限制  
- 调节价格范围 ¥0–¥30,000（步进¥1,000）  
- 按非会员价格计算  
若所有房型超出预算 → ❗  
若部分符合 → ✅ 显示可用项  

---

## 📊 第8章 结果表格

| 代码 | 酒店名 | 状态 | 价格 | 剩余 | 类型 |
|------|--------|------|------|------|------|
| 00061 | Toyoko Inn 新横滨站前 | ✅ | ¥8,700 (¥8,200) | 3 | 单人房 |
| 00061 | 同上 | ✅ | ¥9,400 (¥9,000) | 2 | 双人房 |

备注：  
- 重复房型仅显示最低价  
- 酒店名链接至官网  
- 若仅剩无障碍房 → ❗  

---

## 🔔 第9章 通知内容

示例：
```
✅ 东横INN东京站有空房！
- 类型：双人房
- 价格：¥8,700
- 链接：https://www.toyoko-inn.com/eng/search/detail/00061/
```

---

## 🧩 第10章 故障排查

| 问题 | 可能原因 | 解决方案 |
|------|------------|-----------|
| 浏览器启动失败 | 未安装Chromium | 运行 `playwright install chromium` |
| Telegram 无法推送 | Token 或 Chat ID 错误 | 重新检查 BotFather 设置 |
| 邮件失败 | SMTP 密码错误 | 使用授权码 |
| 本地通知无弹窗 | 系统屏蔽通知 | 关闭“专注模式” |
| Windows运行慢 | Python过旧 | 更新Python与环境 |

---

## 📜 许可证与链接

- 许可证：**MIT**  
- 作者：JellyNeko (bilibili @果冻猫猫丶)  
- 项目主页：[GitHub](https://github.com/JellyNekoNeko/toyoko-tracker)  
