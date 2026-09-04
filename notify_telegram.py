#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
notify_telegram.py — 推送看板核心摘要到 Telegram 机器人。
环境变量：
  TELEGRAM_BOT_TOKEN  — @BotFather 创建机器人后拿到的 token
  TELEGRAM_CHAT_ID    — 与机器人的会话 chat_id（个人 / 群 / 频道均可）
未配置时静默跳过（不中断流水线）。
"""
import json
import os
import urllib.parse
import urllib.request

HOLDINGS = ["LAZR", "INTC", "APP", "BE", "COHR", "WOLF", "NBIS", "NOW"]


def load_json(name):
    here = os.path.dirname(os.path.abspath(__file__))
    p = os.path.join(here, name)
    if not os.path.exists(p):
        return {}
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def esc(s):
    """Telegram HTML parse_mode 需要转义 <, >, &"""
    if s is None:
        return ""
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def idx_html(yf, q, key, etf, etf_name):
    """渲染「三大指数」单格文字。三层防御，确保永不输出 nan：
        1. yfinance 数据有效 → 用真实指数点位 + 涨跌%
        2. yfinance 无效 → fallback 到 westockdata ETF（涨跌幅一致，点位用 ETF 名）
        3. ETF 也无 → 显示 "—"
    """
    import math

    def _is_finite(x):
        return x is not None and isinstance(x, (int, float)) and math.isfinite(x)

    v = yf.get(key, {})
    last, chg = v.get("last"), v.get("chg_pct")
    if _is_finite(last) and _is_finite(chg):
        sign = "+" if chg > 0 else ""
        return f"{last:,.0f} ({sign}{chg}%)"
    x = q.get(etf, {})
    etf_chg = x.get("chg_pct")
    if _is_finite(etf_chg):
        sign = "+" if etf_chg > 0 else ""
        return f"{etf_name} {sign}{etf_chg}%"
    return f"{etf_name} —"


def build_message():
    m = load_json("market_data.json")
    a = load_json("analysis.json")
    q = m.get("quotes", {})
    yf = m.get("yf", {})
    d = m.get("d_latest", "—")

    parts = [
        f"📊 <b>美股 {esc(d)} 收盘复盘</b>（自动化）",
        "",
        "【一句话结论】",
        esc(a.get("conclusion", "（暂无）")),
        "",
        "【三大指数】",
        f"{esc(idx_html(yf, q, 'spx', 'usSPY', '标普 ETF'))} · "
        f"{esc(idx_html(yf, q, 'ndx', 'usQQQ', '纳指 ETF'))} · "
        f"{esc(idx_html(yf, q, 'dji', 'usDIA', '道指 ETF'))}",
        "",
    ]

    # 持仓
    hold_lines = []
    for h in HOLDINGS:
        x = q.get(f"us{h}", {})
        if x.get("last") is not None:
            c = x.get("chg_pct") or 0
            sign = "+" if c > 0 else ""
            last = x["last"]
            if isinstance(last, (int, float)):
                last_s = f"{last:,.2f}" if last < 1000 else f"{last:,.0f}"
            else:
                last_s = str(last)
            hold_lines.append(f"{h} {last_s} ({sign}{c}%)")
    parts.append("【持仓 8 只】")
    parts.append(" · ".join(hold_lines))
    parts.append("")

    # FedWatch
    fw = a.get("fedwatch", {})
    parts.append(
        f"【FedWatch】加息 {esc(fw.get('hike', '—'))} / "
        f"维持 {esc(fw.get('hold', '—'))} / "
        f"降息 {esc(fw.get('cut', '—'))}"
    )

    if a.get("tomorrow_focus"):
        parts.append("")
        parts.append(f"【近期关注】{esc(a['tomorrow_focus'])}")

    parts.extend([
        "",
        "完整看板见 GitHub Actions 产物 <code>index.html</code>",
        "<i>基于公开数据，仅供参考，不构成投资建议。</i>",
    ])
    # Telegram 单条 4096 字符上限，留余量
    msg = "\n".join(parts)
    return msg[:4000]


def send(text):
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        print("未配置 TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID，跳过 Telegram 推送")
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read().decode("utf-8"))
        ok = result.get("ok", False)
        print(f"Telegram 推送返回: ok={ok} 描述={'成功' if ok else result.get('description', '?')}")
        return ok
    except Exception as e:  # noqa: BLE001
        print(f"Telegram 推送失败: {e}")
        return False


def send_typing():
    """可选：先发一个 'typing' 动作，模拟打字效果（让用户感知到 bot 在工作）"""
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not (token and chat_id):
        return
    url = f"https://api.telegram.org/bot{token}/sendChatAction"
    req = urllib.request.Request(
        url, data=json.dumps({"chat_id": chat_id, "action": "typing"}).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    try:
        urllib.request.urlopen(req, timeout=5)
    except Exception:
        pass


if __name__ == "__main__":
    text = build_message()
    print("=== Telegram 摘要预览 ===")
    print(text)
    print(f"\n（字符数 {len(text)} / 4000）\n")
    send_typing()
    ok = send(text)
    print("推送成功" if ok else "推送未完成（未配置或失败）")
