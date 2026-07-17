# V2EX 每日自动签到

自动领取 V2EX 每日登录奖励（铜币/银币/金币），支持多账号、2FA、Telegram 通知，通过 GitHub Actions 定时执行，**无需服务器**。

## 功能

- 每日自动签到领取奖励
- 多账号支持
- 2FA 账号支持（需完整 Cookie 串）
- 签到结果 Telegram 推送通知
- 今日领取的铜币/银币/金币数量统计
- GitHub Actions 定时执行，21:00~00:00 随机签到，免服务器

## 快速开始

### 1. Fork 或克隆本仓库

```bash
git clone https://github.com/BYGD/v2ex-checkin.git
```

### 2. 获取 Cookie

V2EX 的签到需要登录态 Cookie。根据你的账号类型，获取方式略有不同：

#### 未开启 2FA 的账号（只需 A2）

1. 浏览器登录 [v2ex.com](https://www.v2ex.com/)
2. 按 `F12` 打开开发者工具
3. 切换到 `Application`（应用）标签
4. 左侧 `Cookies` → `https://www.v2ex.com`
5. 找到名为 `A2` 的那一行，复制它的值
6. 拼成：`A2=你复制的值`

#### 开启了 2FA 的账号（需完整 Cookie 串）

> 如果只复制 `A2`，签到时会跳到 2FA 验证页，无法通过。

1. 浏览器登录 v2ex.com（完成 2FA 验证）
2. 按 `F12` → `Network`（网络）标签
3. 刷新一下首页
4. 点列表里第一个 `www.v2ex.com` 请求
5. 在 `Headers` 里找到 `Request Headers` → `Cookie:` 那一行
6. 复制冒号后面的**整串内容**（类似 `PB3_SESSION=...; V2EX_LANG=zhcn; A2=...; A2O=...; V2EX_TAB=...`）

> 其中 `A2O` 就是 2FA 通过标记，带它才能跳过 2FA 验证。

### 3. 配置 GitHub Actions

#### 添加 Secrets

进入你 Fork 的仓库 → `Settings` → `Secrets and variables` → `Actions` → `New repository secret`

**单账号配置：**

| Name | Value |
|------|-------|
| `V2EX_COOKIE` | `A2=你的A2值` 或完整 Cookie 串 |

**多账号配置（推荐）：**

| Name | Value |
|------|-------|
| `V2EX_ACCOUNTS` | 见下方 JSON 格式 |

```json
[
  {"name": "主号", "cookie": "A2=...; A2O=..."},
  {"name": "小号", "cookie": "A2=...; A2O=..."}
]
```

> 单账号用 `V2EX_COOKIE`，多账号用 `V2EX_ACCOUNTS`，两者可同时配置，脚本会合并执行。

#### 自定义签到时间

默认每天北京时间 **21:00~00:00 之间随机**执行（cron 触发后随机延迟 0~3 小时）。

编辑 `.github/workflows/v2ex-checkin.yml`：

```yaml
schedule:
  # cron 触发时间（UTC），北京 21:00 = UTC 13:00
  - cron: '0 13 * * *'

# 随机延迟 0~10800 秒（0~3 小时），实际签到落在 21:00~00:00 之间
DELAY=$((RANDOM % 10800))
```

想改成固定时间：删掉「随机延迟」步骤，把 cron 改成目标时间即可。改完 push 到 GitHub 生效。

#### 手动测试

进入仓库 `Actions` 页 → 左侧选「V2EX 每日签到」→ 点 `Run workflow` → 等待执行完成，绿勾说明成功。

### 4. （可选）配置 Telegram 通知

签到完成后自动推送结果到 Telegram。

#### 创建 Bot 获取 Token

1. Telegram 搜索 `@BotFather`
2. 发送 `/newbot`
3. 设置 Bot 名称和用户名
4. 获取 token（格式类似 `123456789:ABCdefGHIjklMNOpqrsTUVwxyz`）

#### 获取你的 Chat ID

1. Telegram 搜索 `@userinfobot`
2. 发送任意消息
3. 获取回复中的 `Id`（一串数字）

#### 添加到 Secrets

| Name | Value |
|------|-------|
| `TG_BOT_TOKEN` | 你的 Bot Token |
| `TG_CHAT_ID` | 你的 Chat ID |

配置完成后，签到结果会推送到你的 Telegram，效果如下：

```
✅ V2EX 签到报告
时间：2026-07-18 22:17
结果：1/1 成功

✅ 主号 — 获得 50 铜币

💰 今日收获：50 铜币
```

## 本地运行

### 安装依赖

```bash
pip install requests
```

### 方式一：环境变量

```bash
# 单账号
export V2EX_COOKIE="A2=你的A2值"
python v2ex_checkin.py

# 多账号
export V2EX_ACCOUNTS='[{"name":"主号","cookie":"A2=...; A2O=..."},{"name":"小号","cookie":"A2=...; A2O=..."}]'
python v2ex_checkin.py

# Telegram 通知（可选）
export TG_BOT_TOKEN="你的Bot Token"
export TG_CHAT_ID="你的Chat ID"
```

### 方式二：配置文件

复制 `config.example.json` 为 `config.json`，填入 Cookie：

```json
{
  "accounts": [
    {"name": "主号", "cookie": "A2=...; A2O=..."},
    {"name": "小号", "cookie": "A2=...; A2O=..."}
  ]
}
```

然后运行：

```bash
python v2ex_checkin.py
```

### 方式三：定时任务

```bash
# Linux/Mac crontab（每天 9:05 执行）
5 9 * * * /path/to/python /path/to/v2ex_checkin.py >> v2ex.log 2>&1
```

Windows 用任务计划程序，设置每天定时运行 `python v2ex_checkin.py`。

## 配置参考

所有可用环境变量和配置项：

| 配置项 | 类型 | 说明 |
|--------|------|------|
| `V2EX_ACCOUNTS` | 环境变量 | 多账号 JSON 数组（优先级最高） |
| `V2EX_COOKIE` | 环境变量 | 单账号 Cookie |
| `config.json` | 配置文件 | 本地运行用，格式同 V2EX_ACCOUNTS |
| `TG_BOT_TOKEN` | 环境变量 | Telegram Bot Token（可选） |
| `TG_CHAT_ID` | 环境变量 | Telegram Chat ID（可选） |

> 三种签到配置方式可叠加，脚本会合并所有账号一起执行。

## 注意事项

- **Cookie 会过期**：`A2` / `A2O` 含时间戳，过一段时间会失效。签到报「未登录」时，重新获取 Cookie 更新 Secret 即可。
- **GitHub 仓库活跃度**：仓库超过 60 天无 commit/activity，scheduled workflow 会被自动暂停，偶尔提交点代码保持活跃即可。
- **安全提醒**：Cookie = 账号登录凭证，切勿提交到代码仓库或分享给他人。`config.json` 已被 `.gitignore` 忽略，GitHub Actions 用户请通过 Secrets 配置。
- **2FA 账号**：必须使用完整 Cookie 串（含 `A2O`），单 `A2` 无法通过 2FA 验证。

## 工作原理

```
带 Cookie 访问 /mission/daily
        │
        ├── 重定向到 /signin → Cookie 失效
        ├── 页面显示"已领取"  → 今日已签到
        └── 提取 once token
                │
                └── GET /mission/daily/redeem?once=xxx → 签到成功，提取奖励
```

## License

MIT
