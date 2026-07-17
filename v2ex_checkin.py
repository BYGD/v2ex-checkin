#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
V2EX 每日自动签到脚本
=====================

原理：带 Cookie 访问 /mission/daily → 解析 once token → 请求 /mission/daily/redeem?once=xxx 完成签到。

【获取 Cookie】
  未开 2FA 的账号只需 A2 一个 Cookie；开了 2FA 的账号需完整 Cookie 串（含 A2O 等）
  1. 浏览器登录 https://www.v2ex.com/
  2. F12 → Application(应用) → Cookies → https://www.v2ex.com
  3. 复制所需 cookie，拼成 "A2=值" 或完整串 "A2=...; A2O=...; ..."

【配置方式】(可叠加，优先级从高到低)
  A. 环境变量多账号（推荐 GitHub Actions 用）：
       V2EX_ACCOUNTS='[{"name":"主号","cookie":"A2=...; A2O=..."},
                       {"name":"小号","cookie":"A2=...; A2O=..."}]'
  B. 环境变量单账号：
       V2EX_COOKIE="A2=你的A2值"
  C. config.json（格式同 V2EX_ACCOUNTS，文件方式）：
       {"accounts": [{"name":"主号","cookie":"A2=主号值"},
                     {"name":"小号","cookie":"A2=小号值"}]}

【运行】
  python v2ex_checkin.py

【定时】
  A. GitHub Actions（推荐，免服务器）：
     - 把脚本和 .github/workflows/v2ex-checkin.yml 提交到 GitHub 仓库
     - 仓库 Settings → Secrets → Actions → New secret
       单账号：名称填 V2EX_COOKIE，值填 cookie 串
       多账号：名称填 V2EX_ACCOUNTS，值填 JSON 数组
     - 自定义签到时间：修改 yml 中 cron 表达式（UTC 时间，北京 = UTC + 8）
     - 也可在 Actions 页手动 Run workflow 测试
  B. Windows 任务计划程序 / Linux crontab：
     5 9 * * * /path/to/python /path/to/v2ex_checkin.py >> v2ex.log 2>&1

【Telegram 通知】（可选）
  签到完成后将结果推送到 Telegram，需配置两个环境变量：
    TG_BOT_TOKEN — 通过 @BotFather 创建 Bot 获取
    TG_CHAT_ID   — 你的 Chat ID（通过 @userinfobot 获取）
  未配置则自动跳过，不影响签到。
  GitHub Actions 用户：把这两个值加到仓库 Secrets 里即可。
"""

import os
import re
import sys
import json
import time
from datetime import datetime, timezone, timedelta

try:
    import requests
except ImportError:
    sys.exit("缺少依赖 requests，请先安装：pip install requests")

BASE_URL = "https://www.v2ex.com"
TIMEOUT = 20
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")


def log(name, msg):
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] [{name}] {msg}", flush=True)


def send_telegram(text):
    """通过 Telegram Bot 推送通知，需配置 TG_BOT_TOKEN 和 TG_CHAT_ID 环境变量"""
    token = os.getenv("TG_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TG_CHAT_ID", "").strip()
    if not token or not chat_id:
        return  # 未配置则跳过，不影响签到
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "HTML",
                  "disable_web_page_preview": True},
            timeout=15,
        )
        if resp.status_code != 200:
            log("TG", f"通知发送失败 HTTP {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        log("TG", f"通知发送异常: {e}")


def load_config():
    """加载账号配置，返回 [(name, cookie), ...]

    优先级（高→低，可叠加）：
      1. V2EX_ACCOUNTS 环境变量（JSON 数组，多账号）
      2. V2EX_COOKIE 环境变量（单账号）
      3. config.json 文件
    """
    accounts = []

    # 1. V2EX_ACCOUNTS：JSON 数组，支持多账号
    env_accounts = os.getenv("V2EX_ACCOUNTS", "").strip()
    if env_accounts:
        try:
            for a in json.loads(env_accounts):
                accounts.append((a.get("name", "account"), a["cookie"]))
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            sys.exit(f"V2EX_ACCOUNTS 格式错误（应为 JSON 数组）: {e}")

    # 2. V2EX_COOKIE：单账号
    env_cookie = os.getenv("V2EX_COOKIE", "").strip()
    if env_cookie:
        accounts.append(("env", env_cookie))

    # 3. config.json
    cfg_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
    if os.path.exists(cfg_path):
        with open(cfg_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        if "accounts" in cfg:
            for a in cfg["accounts"]:
                accounts.append((a.get("name", "account"), a["cookie"]))
        elif "cookie" in cfg:
            accounts.append((cfg.get("name", "account"), cfg["cookie"]))
    return accounts


def checkin(name, cookie):
    s = requests.Session()
    s.headers.update({
        "User-Agent": UA,
        "Cookie": cookie,
        "Referer": f"{BASE_URL}/mission/daily",
        "Accept-Language": "zh-CN,zh;q=0.9",
    })

    # 1. 访问签到页
    r = s.get(f"{BASE_URL}/mission/daily", timeout=TIMEOUT, allow_redirects=True)

    # 未登录会重定向到 /signin，或页面提示需登录
    if "/signin" in r.url or "You need to sign in" in r.text or "请先登录" in r.text:
        log(name, "X 未登录或 Cookie 已失效")
        return False
    if "每日登录奖励已领取" in r.text:
        log(name, "OK 今日已签到（之前领过了）")
        return True

    # 2. 提取 once token
    m = re.search(r'/mission/daily/redeem\?once=(\d+)', r.text)
    if not m:
        m = re.search(r'once=(\d+)', r.text)
    if not m:
        log(name, "X 未找到签到 token，页面结构可能已变化")
        return False
    once = m.group(1)

    # 3. 领取奖励
    r2 = s.get(f"{BASE_URL}/mission/daily/redeem?once={once}",
               timeout=TIMEOUT, allow_redirects=True)
    bonus = re.search(r'(\d+)\s*(?:个)?\s*(铜币|银币|金币)', r2.text)
    bonus_str = f"（获得 {bonus.group(1)} {bonus.group(2)}）" if bonus else ""
    if r2.status_code == 200:
        log(name, f"OK 签到成功 {bonus_str}".rstrip())
        return True
    log(name, f"X 签到失败 HTTP {r2.status_code}")
    return False


def main():
    accounts = load_config()
    if not accounts:
        sys.exit("未找到配置！请设置环境变量 V2EX_ACCOUNTS / V2EX_COOKIE 或创建 config.json（参考脚本头部说明）")

    log("系统", f"开始签到，共 {len(accounts)} 个账号")
    ok = 0
    results = []
    for name, cookie in accounts:
        try:
            if checkin(name, cookie):
                ok += 1
                results.append(f"✅ {name}")
            else:
                results.append(f"❌ {name}")
        except requests.RequestException as e:
            log(name, f"X 网络错误: {e}")
            results.append(f"❌ {name}（网络错误）")
        time.sleep(2)  # 多账号间隔，避免请求过快

    log("系统", f"完成：{ok}/{len(accounts)} 成功")

    # Telegram 通知
    now_bj = datetime.now(timezone(timedelta(hours=8)))
    icon = "✅" if ok == len(accounts) else "⚠️"
    msg = (f"<b>{icon} V2EX 签到报告</b>\n"
           f"时间：{now_bj:%Y-%m-%d %H:%M}\n"
           f"结果：{ok}/{len(accounts)} 成功\n\n")
    msg += "\n".join(results)
    send_telegram(msg)

    sys.exit(0 if ok == len(accounts) else 1)


if __name__ == "__main__":
    main()
