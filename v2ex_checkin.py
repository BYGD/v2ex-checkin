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


def _extract_reward(html):
    """从签到页 HTML 提取奖励信息，返回 '获得 X 铜币' 或 ''"""
    patterns = [
        r'已成功领取每日登录奖励\s*(\d+)\s*(铜币|银币|金币)',
        r'每日登录奖励\s*(\d+)\s*(铜币|银币|金币)',
        r'领取[^<]*?(\d+)\s*(铜币|银币|金币)',
        r'(\d+)\s*个?\s*(铜币|银币|金币)',
    ]
    for p in patterns:
        m = re.search(p, html)
        if m:
            return f"获得 {m.group(1)} {m.group(2)}"
    return ""


def checkin(name, cookie):
    """签到，返回 (success: bool, reward: str)"""
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
        return False, "未登录或 Cookie 已失效"
    if "每日登录奖励已领取" in r.text:
        reward = _extract_reward(r.text)
        msg = f"今日已签过（{reward}）" if reward else "今日已签过"
        log(name, f"OK {msg}")
        return True, msg

    # 2. 提取 once token
    m = re.search(r'/mission/daily/redeem\?once=(\d+)', r.text)
    if not m:
        m = re.search(r'once=(\d+)', r.text)
    if not m:
        log(name, "X 未找到签到 token，页面结构可能已变化")
        return False, "未找到签到 token"
    once = m.group(1)

    # 3. 领取奖励
    r2 = s.get(f"{BASE_URL}/mission/daily/redeem?once={once}",
               timeout=TIMEOUT, allow_redirects=True)
    if r2.status_code != 200:
        log(name, f"X 签到失败 HTTP {r2.status_code}")
        return False, f"签到失败 HTTP {r2.status_code}"

    # 4. 领取后从"再次请求的签到页"和 redeem 响应里提取奖励
    #    （V2EX 的"已成功领取 X 铜币"提示框只在领取瞬间显示，刷新即消失）
    time.sleep(1)
    r3 = s.get(f"{BASE_URL}/mission/daily", timeout=TIMEOUT, allow_redirects=True)
    pages = [r3.text if r3.status_code == 200 else "", r2.text]

    # 5. 多重正则提取奖励（两个页面都试）
    for page in pages:
        reward = _extract_reward(page)
        if reward:
            log(name, f"OK 签到成功（{reward}）")
            return True, reward

    # 诊断：打印疑似片段，方便下次精确定位
    for page in pages:
        for kw in ["铜币", "银币", "金币", "领取", "奖励"]:
            idx = page.find(kw)
            if idx >= 0:
                snippet = page[max(0, idx - 40):idx + 60].strip()
                log(name, f"诊断 [{kw}] 片段: ...{snippet}...")
                break
        else:
            continue
        break

    log(name, "OK 签到成功")
    return True, "签到成功（奖励信息未识别）"


def main():
    accounts = load_config()
    if not accounts:
        sys.exit("未找到配置！请设置环境变量 V2EX_ACCOUNTS / V2EX_COOKIE 或创建 config.json（参考脚本头部说明）")

    log("系统", f"开始签到，共 {len(accounts)} 个账号")
    ok = 0
    results = []
    coins = {}  # {币种: 数量} 汇总今天新领取的
    for name, cookie in accounts:
        try:
            success, reward = checkin(name, cookie)
            if success:
                ok += 1
                results.append(f"✅ <b>{name}</b>\n   └ {reward}")
                # 提取奖励数量汇总
                for amt, unit in re.findall(r'(\d+)\s*(铜币|银币|金币)', reward):
                    coins[unit] = coins.get(unit, 0) + int(amt)
            else:
                results.append(f"❌ <b>{name}</b>\n   └ {reward}")
        except requests.RequestException as e:
            log(name, f"X 网络错误: {e}")
            results.append(f"❌ <b>{name}</b>\n   └ 网络错误")
        time.sleep(2)  # 多账号间隔，避免请求过快

    log("系统", f"完成：{ok}/{len(accounts)} 成功")

    # Telegram 通知（卡片式排版）
    now_bj = datetime.now(timezone(timedelta(hours=8)))
    sep = "━━━━━━━━━━━━━━━━━━"
    icon = "🎯" if ok == len(accounts) else "⚠️"

    msg = f"<b>{icon} V2EX 每日签到</b>\n"
    msg += f"{sep}\n"
    msg += f"⏰ {now_bj:%Y-%m-%d %H:%M}\n"
    msg += f"📊 成功 <b>{ok}</b>/<b>{len(accounts)}</b>\n"
    msg += f"{sep}\n"
    msg += "\n".join(results)
    msg += f"\n{sep}\n"
    if coins:
        coin_str = "，".join(f"{v} {k}" for k, v in coins.items())
        msg += f"💎 今日收获 · <b>{coin_str}</b>"
    else:
        msg += "💎 今日收获 · 无"
    send_telegram(msg)

    sys.exit(0 if ok == len(accounts) else 1)


if __name__ == "__main__":
    main()
