#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
notify_feishu.py — 推送看板核心摘要到飞书群自定义机器人。
环境变量：FEISHU_WEBHOOK（飞书群机器人 webhook URL）。
未配置 webhook 时静默跳过（不中断流水线）。
"""
import json
import os
import urllib.request

HOLDINGS = ["LAZR", "INTC", "APP", "BE", "COHR", "WOLF", "NBIS", "NOW"]


def load_json(name):
    here = os.path.dirname(os.path.abspath(__file__))
    p = os.path.join(here, name)
    if not os.path.exists(p):
        return {}
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def build_summary():
    m = load_json("market_data.json")
    a = load_json("analysis.json")
    q = m.get("quotes", {})
    yf = m.get("yf", {})
    d = m.get("d_latest", "—")

    def idx(key, etf):
        v = yf.get(key, {})
        if v.get("last") is not None:
            c = v.get("chg_pct")
            return f"{v['last']:,.0f} ({'+' if (c or 0) > 0 else ''}{c}%)"
        x = q.get(etf, {})
        c = x.get("chg_pct")
        return f"{x.get('last', '—')} ({'+' if (c or 0) > 0 else ''}{c}%)"

    lines = [
        f"📊 美股 {d} 收盘复盘（自动化）",
        "",
        "【一句话结论】",
        a.get("conclusion", "（暂无）"),
        "",
        "【三大指数】",
        f"标普 {idx('spx','usSPY')} · 纳指 {idx('ndx','usQQQ')} · 道指 {idx('dji','usDIA')}",
        "",
    ]
    # 持仓
    hold_lines = []
    for h in HOLDINGS:
        x = q.get(f"us{h}", {})
        c = x.get("chg_pct")
        if x.get("last") is not None:
            hold_lines.append(f"{h} {x['last']} ({'+' if (c or 0) > 0 else ''}{c}%)")
    lines.append("【持仓 8 只】")
    lines.append(" · ".join(hold_lines))
    lines.append("")
    # FedWatch
    fw = a.get("fedwatch", {})
    lines.append(f"【FedWatch】加息 {fw.get('hike','—')} / 维持 {fw.get('hold','—')} / 降息 {fw.get('cut','—')}")
    if a.get("tomorrow_focus"):
        lines.append("")
        lines.append(f"【近期关注】{a['tomorrow_focus']}")
    lines.append("")
    lines.append("完整看板见 GitHub Actions 产物 index.html")
    lines.append("以上内容基于公开数据，仅供参考，不构成投资建议。")
    return "\n".join(lines)


def send(text):
    webhook = os.environ.get("FEISHU_WEBHOOK", "")
    if not webhook:
        print("未配置 FEISHU_WEBHOOK，跳过飞书推送")
        return False
    body = json.dumps({"msg_type": "text", "content": {"text": text}}).encode("utf-8")
    req = urllib.request.Request(webhook, data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read().decode("utf-8"))
        code = result.get("code", result.get("StatusCode", -1))
        print(f"飞书推送返回: {result}")
        return code == 0
    except Exception as e:  # noqa: BLE001
        print(f"飞书推送失败: {e}")
        return False


if __name__ == "__main__":
    text = build_summary()
    print("=== 摘要预览 ===")
    print(text)
    ok = send(text)
    print("推送成功" if ok else "推送未完成（未配置或失败）")
