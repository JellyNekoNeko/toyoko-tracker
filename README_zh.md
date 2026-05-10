# 东横INN 空房追踪器 WebUI

*一个可爱的 [东横INN](https://www.toyoko-inn.com/) 酒店空房监控工具，基于 Flask + HTTP/API + 可选 Playwright 构建。*

🌏 [📖 English Guide](./README.md)

---

# 📘 Toyoko Tracker 中文使用说明

## 第1章 安装与入门

### 1.1 简介

**Toyoko Tracker（东横追踪器 / 东横酱 Toyoko Chan）** 是一个本地 WebUI 工具，用于自动检测 **东横INN** 酒店空房状态。

它支持：

- 🌐 本地网页界面，实时显示空房结果
- ⚡ 默认使用轻量 HTTP/API 查询引擎
- 🧭 可选 Playwright 浏览器渲染引擎，用于兼容模式
- 🏨 按地区加载和选择酒店
- 🕘 搜索历史记录
- 🛏 房型筛选：Single / Double / Twin
- 💳 会员价 / 非会员价显示
- 🔔 本地桌面通知
- 🤖 Telegram Bot 推送
- 📱 Bark 推送，适合 iPhone / iPad
- 💬 Server 酱推送，适合微信通知
- 📧 SMTP 邮件提醒
- 🚀 智能并行扫描，适合较大的酒店列表

---

### 1.2 安装说明

#### 必需条件

- Python **3.9+**
- 推荐 Python **3.10 / 3.11 / 3.12**
- 网络连接

#### 可选条件

- Playwright Chromium，仅在使用 **Playwright 兼容引擎** 时需要。

---

### 1.3 从 PyPI 安装

打开命令行：

- **Windows**：按 `Win + R`，输入 `cmd`，然后回车。也可以使用 PowerShell。
- **macOS**：打开 Launchpad，搜索并打开 **终端**。
- **Linux**：按 `Ctrl + Alt + T`，或在应用菜单中搜索 Terminal。

执行：

```bash
pip install --upgrade pip
pip install --upgrade toyoko-tracker
```

如果你的 Python 环境不允许全局 pip 安装，建议使用虚拟环境：

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install --upgrade toyoko-tracker
```

Windows PowerShell：

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install --upgrade pip
pip install --upgrade toyoko-tracker
```

---

### 1.4 可选：安装 Playwright Chromium

默认 HTTP/API 引擎 **不需要** Playwright。

只有当你想使用浏览器兼容引擎时，才需要安装 Chromium：

```bash
playwright install chromium
```

---

### 1.5 使用方法

安装完成后运行：

```bash
toyoko-tracker
```

启动后：

- 本地 Web 服务会自动启动。
- 默认地址：[http://127.0.0.1:4170](http://127.0.0.1:4170)
- 如果 `4170` 端口被占用，程序会自动寻找其他可用本地端口。
- 浏览器通常会自动打开。
- 如果没有自动打开，请查看终端输出，手动打开显示的本地地址。

---

### 1.6 版本信息

- 当前版本：`v0.5.0`
- App 名称：`东横酱 Toyoko Chan`
- 作者：JellyNeko / bilibili @果冻猫猫丶
- 许可证：MIT

---

## 🏨 第2章 选择酒店

Toyoko Tracker 支持两种选择酒店的方式：

1. 使用内置 **地区酒店选择器**
2. 手动输入东横INN 5位酒店代码

---

### 2.1 推荐：使用地区酒店选择器

在 WebUI 中：

1. 选择 **Region / 地区**
2. 可选选择 **Detail Area / 详细区域**
3. 点击 **Load Hotels / 加载酒店**
4. 勾选要监控的酒店
5. 点击 **Start / 开始**

你也可以：

- 点击 **Select All** 选择当前加载的全部酒店
- 点击 **Select None** 清空选择
- 使用过滤框按中文名、英文名或酒店代码搜索

选择的酒店会保存到搜索历史中。

---

### 2.2 通过 Google 搜索酒店代码

你也可以手动查找 5 位酒店代码。

例如搜索：

```text
Toyoko Inn Shin-yokohama Ekimae Shinkan
```

你可能会找到东横INN官方页面：

```text
https://www.toyoko-inn.com/eng/search/detail/00061/
```

其中 `00061` 就是酒店代码。

---

### 2.3 从预订链接获取酒店代码

在东横INN官网搜索时，结果页面链接可能类似：

```text
https://www.toyoko-inn.com/eng/search/result/room_plan/?hotel=00061&start=2025-10-13&end=2025-10-14&room=1&people=1
```

其中：

```text
hotel=00061
```

表示酒店代码为：

```text
00061
```

---

## 🔍 第3章 搜索设置

### 3.1 基本搜索条件

WebUI 支持设置：

- 入住日期
- 退房日期
- 入住人数：1–5
- 房间数量：1–9
- 吸烟偏好：
  - Non-Smoking / 禁烟
  - Smoking / 吸烟
  - Any / 不限
- 房型：
  - Any / 不限
  - Single / 单人房
  - Double / 双人大床房
  - Twin / 双床房
- 会员状态：
  - Member / 会员
  - Non-member / 非会员
  - Unknown / 未知

同时提供快捷日期按钮：

- Tonight / 今晚
- Tomorrow / 明晚
- Weekend / 周末

---

### 3.2 搜索引擎

Toyoko Tracker 提供两种搜索引擎。

#### HTTP/API 引擎

默认推荐使用。

优点：

- 更快
- 更轻量
- 资源占用更低
- 不需要浏览器渲染

如果 HTTP/API 引擎无法解析某个酒店结果，且 Playwright 可用，程序可能会尝试回退到 Playwright 兼容方式。

#### Playwright 引擎

兼容模式。

优点：

- 更接近真实浏览器渲染
- 适合东横INN网站结构变化时使用
- 当 HTTP/API 解析失败时可作为备用方案

需要先安装：

```bash
playwright install chromium
```

---

### 3.3 扫描节奏

可以配置：

- **Round Interval / 轮询间隔**  
  每一轮扫描之间的等待时间。最小 30 秒。

- **Per-hotel Base Delay / 单酒店基础延迟**  
  同一扫描线中，每个酒店之间的等待时间。

- **Request Jitter / 请求随机抖动**  
  在固定延迟基础上加入随机变化，避免请求节奏过于机械。

推荐稳定设置：

```text
Round Interval: 120 秒或更高
Per-hotel Delay: 2–5 秒
Request Jitter: 30–50%
```

---

### 3.4 Smart Parallel / 智能并行

智能并行适用于 HTTP/API 引擎。

它可以把酒店列表分成 1–3 条扫描线。

推荐用法：

- 1 worker：少量酒店
- 2 workers：中等酒店列表
- 3 workers：大量酒店列表

智能并行会使用错峰启动和扩展后的单线间隔，让请求节奏更自然。

---

## 🕘 第4章 搜索历史

Toyoko Tracker 会自动记录最近的搜索设置。

搜索历史面板支持：

- 刷新
- 清空
- 重新加载之前的搜索设置

程序最多保留最近 10 条搜索记录。

完全相同的搜索设置不会重复加入历史。

---

## 🔔 第5章 推送通知

Toyoko Tracker 可以在以下情况发送通知：

- 开始监控
- 发现有空房
- 空房持续存在且满足重复提醒条件
- 原本有房的酒店变为无房

通知内容可能包含：

- 酒店名称
- 日期范围
- 房型
- 非会员价格
- 会员价格
- 剩余房间数量
- 预订链接

特殊房型，例如 **heartful / accessible / 无障碍房**，会自动忽略。

---

### 5.1 重复提醒规则

可以配置：

- 重复提醒次数
- 重复提醒冷却时间

重复次数表示首次有房提醒之后，还可以额外提醒几次。

最大值可作为持续提醒模式。

推荐冷却时间：

```text
300 秒或更高
```

---

## 🤖 第6章 Telegram Bot 设置

### 6.1 创建 Telegram Bot

1. 打开 Telegram
2. 搜索 **BotFather**
3. 发送：

```text
/newbot
```

4. 按提示设置：
   - 机器人名称，例如 `ToyokoBot`
   - 机器人用户名，必须以 `bot` 结尾
5. BotFather 会提供 Bot Token，例如：

```text
1234567890:ABCdefGhIJklmNoPQRstuVWxyZ
```

---

### 6.2 获取 Chat ID

个人聊天：

1. 搜索 **@userinfobot**
2. 启动这个 bot
3. 它会显示你的 Chat ID，例如：

```text
987654321
```

群组聊天：

1. 把你的 bot 加入群组
2. 确认 bot 有发送消息权限
3. 使用 Telegram 更新调试 bot 或 Bot API 获取群组 Chat ID

---

### 6.3 在 WebUI 中配置 Telegram

在 **Push Settings → Telegram Bot** 中：

1. 启用 Telegram
2. 填入 Bot Token
3. 填入 Chat ID
4. 开始监控

---

## 📱 第7章 Bark 推送设置

Bark 适合 iPhone / iPad 推送通知。

### 7.1 设置步骤

1. 在 iPhone / iPad 上安装 **Bark**
2. 打开 Bark
3. 复制你的 Device Key
4. 在 Toyoko Tracker WebUI 中打开 **Push Settings → Bark**
5. 启用 Bark
6. 粘贴 Bark Key
7. Bark Server 默认即可，除非你使用自建 Bark 服务

默认 Bark 服务：

```text
https://api.day.app
```

---

## 💬 第8章 Server 酱设置

Server 酱可以把通知推送到微信。

### 8.1 设置步骤

1. 打开 Server 酱官网
2. 使用微信登录
3. 绑定微信推送通道
4. 复制你的 `SendKey`
5. 在 Toyoko Tracker WebUI 中打开 **Push Settings → Server Chan**
6. 启用 Server Chan
7. 粘贴 SendKey

SendKey 通常以以下字符开头：

```text
SCT
```

---

## 📧 第9章 邮件通知设置

Toyoko Tracker 支持 SMTP 邮件提醒。

### 9.1 开启 SMTP 服务

不同邮箱设置方式不同。

#### Gmail

推荐使用 **App Passwords / 应用专用密码**。

1. 打开 Google 账号设置
2. 进入 Security / 安全
3. 启用 2-Step Verification / 两步验证
4. 创建 App Password
5. 在 Toyoko Tracker 中使用该密码

#### QQ 邮箱

1. 打开 QQ 邮箱设置
2. 启用 SMTP 服务
3. 生成授权码
4. 使用授权码作为 SMTP 密码

#### 163 / 126 邮箱

1. 启用 POP3/SMTP/IMAP 服务
2. 生成授权码
3. 使用授权码作为 SMTP 密码

---

### 9.2 填写邮件设置

在 **Push Settings → Email** 中填写：

- SMTP Host：例如 `smtp.gmail.com` 或 `smtp.qq.com`
- SMTP Port：
  - `465` 用于 SSL
  - `587` 用于 STARTTLS
- SMTP Username：你的邮箱地址
- SMTP Password：应用专用密码或授权码
- From：发件邮箱
- To：收件邮箱

多个收件人可以用英文逗号分隔：

```text
a@example.com, b@example.com
```

---

## 💻 第10章 本地桌面通知

本地通知支持：

- macOS
- Windows
- Linux

### macOS

Toyoko Tracker 会尝试：

1. 使用 `terminal-notifier`，如果已安装
2. 使用 `osascript` 作为备用方案

可选安装 macOS 通知工具：

```bash
brew install terminal-notifier
```

如果没有通知弹窗：

1. 打开 **系统设置**
2. 进入 **通知**
3. 允许 Terminal、Python 或 osascript 发送通知

你可以在 WebUI 中测试本地通知：

```text
Push Settings → Local → Test Notification
```

### Windows

Toyoko Tracker 会使用 PowerShell NotifyIcon 气泡通知。

### Linux

Toyoko Tracker 会尝试使用：

```bash
notify-send
```

---

## 🖥 第11章 Web 界面说明

### 11.1 主要区域

WebUI 包含：

- 搜索条件
- 地区酒店选择器
- 搜索历史
- 搜索设置
- 推送设置
- 运行控制
- 搜索结果
- 通知状态
- 实时日志

---

### 11.2 操作按钮

- **Start / 开始**  
  使用当前设置开始监控，并自动保存当前设置。

- **Stop / 停止**  
  停止监控。

- **Default / 默认**  
  重置基础搜索设置。

- **Load Hotels / 加载酒店**  
  根据选择的地区和详细区域加载酒店。

- **Select All / 全选**  
  选择当前加载的全部酒店。

- **Select None / 全不选**  
  清空当前选择。

- **Refresh History / 刷新历史**  
  重新读取搜索历史。

- **Clear History / 清空历史**  
  删除保存的搜索历史。

- **Test Notification / 测试通知**  
  发送一条本地通知测试。

---

### 11.3 状态面板

状态面板显示：

- 运行 / 停止状态
- 扫描轮次
- 当前进度
- 本轮耗时
- 总运行时间
- 当前动作
- 等待 / 扫描阶段

---

### 11.4 结果表格

结果表格显示：

- 酒店代码
- 酒店名称
- 状态
- 最低价格
- 剩余房间数
- 房型

状态含义：

- ✅ 有房
- ❌ 无房
- ❓ 未知 / 需要检查
- ❗ 不满足房型要求

追踪器会显示符合条件的最低价项目，并自动忽略 heartful / accessible / 无障碍等特殊房型。

---

### 11.5 通知状态面板

通知状态面板显示各通道状态：

- Telegram
- 本地通知
- Email
- Bark
- Server Chan

每个通道可能显示：

- Disabled / 未启用
- Waiting / 等待中
- Pushing / 推送中
- Success / 成功
- Failed / 失败

---

## 🗂 第12章 配置文件

Toyoko Tracker 会把配置文件保存在用户配置目录。

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

主要文件：

```text
auto_save.json
save.json
search_history.json
```

可以通过环境变量覆盖配置目录：

```bash
TOYOKO_TRACKER_CONFIG_DIR=/path/to/config toyoko-tracker
```

---

## 🧪 第13章 故障排查

### 13.1 找不到 toyoko-tracker 命令

如果提示 `toyoko-tracker: command not found`，可以尝试：

```bash
python -m toyoko_tracker
```

或重新安装：

```bash
pip install --upgrade toyoko-tracker
```

---

### 13.2 Playwright 引擎不可用

安装 Chromium：

```bash
playwright install chromium
```

然后重新启动 Toyoko Tracker。

---

### 13.3 邮件收不到

检查：

- 垃圾邮件 / Spam 文件夹
- SMTP Host 和端口
- 应用专用密码 / 授权码
- 是否启用了 SMTP 服务
- 发件邮箱是否限制第三方客户端登录

---

### 13.4 Telegram 推送失败

检查：

- Bot Token 是否正确
- Chat ID 是否正确
- 是否已经启动 bot
- 群组中 bot 是否有发送消息权限

---

### 13.5 macOS 本地通知没有弹窗

可以尝试安装：

```bash
brew install terminal-notifier
```

然后在以下位置允许通知：

```text
系统设置 → 通知
```

---

## 📦 第14章 升级

从 PyPI 升级：

```bash
pip install --upgrade toyoko-tracker
```

查看版本：

```bash
toyoko-tracker
```

版本号会显示在 WebUI 底部。

---

## 📜 许可证与链接

- 许可证：**MIT**
- 作者：JellyNeko / bilibili @果冻猫猫丶
- 项目主页：[GitHub](https://github.com/JellyNekoNeko/toyoko-tracker)
