#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ai_analysis.py — 调用 Gemini 做 AI 研判（含 Google Search 联网），输出 analysis.json。
完全脱离 WorkBuddy。API Key 从环境变量 GEMINI_API_KEY 读取。
"""
import json
import os
import urllib.request
import datetime

API_KEY = os.environ.get("GEMINI_API_KEY", "")
MODEL = "gemini-2.5-flash"
BASE = "https://generativelanguage.googleapis.com/v1beta"

HOLDINGS = ["LAZR", "INTC", "APP", "BE", "COHR", "WOLF", "NBIS", "NOW"]


def load_market():
    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, "market_data.json"), encoding="utf-8") as f:
        return json.load(f)


def build_prompt(m):
    q = m.get("quotes", {})
    def g(sym):
        x = q.get(sym, {})
        return (x.get("last"), x.get("chg_pct"))
    def fmt(sym, name):
        p, c = g(sym)
        return f"{name}: ${p} ({'+' if (c or 0) > 0 else ''}{c}%)" if p else f"{name}: 无数据"

    idx_lines = [
        fmt("usSPY", "标普500"), fmt("usQQQ", "纳斯达克"), fmt("usDIA", "道琼斯"), fmt("usIWM", "罗素2000"),
        fmt("usSMH", "半导体SMH"), fmt("usXLK", "科技XLK"), fmt("usIGV", "软件IGV"),
        fmt("usXLF", "金融XLF"), fmt("usXLE", "能源XLE"), fmt("usGLD", "黄金GLD"),
    ]
    hold_lines = [fmt(f"us{h}", h) for h in HOLDINGS]

    # 五层蛋糕关键股
    cake = [
        "⑤应用: " + ", ".join(fmt(s, n) for s, n in
               [("usAAPL", "AAPL"), ("usTSLA", "TSLA"), ("usSNOW", "SNOW"), ("usNOW", "NOW"),
                ("usAPP", "APP"), ("usCRM", "CRM"), ("usPLTR", "PLTR"), ("usCRWD", "CRWD")]),
        "④模型(云厂代理): " + ", ".join(fmt(s, n) for s, n in
               [("usMSFT", "MSFT"), ("usGOOGL", "GOOGL"), ("usMETA", "META"), ("usAMZN", "AMZN")]),
        "③基础设施: " + ", ".join(fmt(s, n) for s, n in
               [("usORCL", "ORCL"), ("usCRWV", "CRWV"), ("usNBIS", "NBIS"), ("usCOHR", "COHR"),
                ("usCRDO", "CRDO"), ("usANET", "ANET"), ("usVRT", "VRT"), ("usEQIX", "EQIX")]),
        "②芯片: " + ", ".join(fmt(s, n) for s, n in
               [("usNVDA", "NVDA"), ("usAMD", "AMD"), ("usTSM", "TSM"), ("usAVGO", "AVGO"),
                ("usMU", "MU"), ("usARM", "ARM"), ("usASML", "ASML"), ("usAMAT", "AMAT"),
                ("usMRVL", "MRVL"), ("usINTC", "INTC"), ("usWOLF", "WOLF")]),
        "①能源: " + ", ".join(fmt(s, n) for s, n in
               [("usVST", "VST"), ("usCEG", "CEG"), ("usGEV", "GEV"), ("usBE", "BE"), ("usOKLO", "OKLO")]),
    ]

    yf = m.get("yf", {})
    macro_lines = []
    for k, label in [("tnx", "10Y美债"), ("fvx", "5Y美债"), ("tyx", "30Y美债"),
                     ("vix", "VIX"), ("gold", "黄金"), ("wti", "WTI原油"), ("btc", "BTC")]:
        v = yf.get(k, {})
        if v.get("last") is not None:
            macro_lines.append(f"{label}: {v['last']} ({'+' if (v.get('chg_pct') or 0) > 0 else ''}{v.get('chg_pct')}%)")

    prompt = f"""你是美股投研助手。请基于以下【实时行情数据】（已拉到本地）+【联网搜索最新新闻】做收盘复盘研判。

【最新交易日】{m.get('d_latest')}（前一交易日 {m.get('d_prev')}）

【核心指数】
{chr(10).join(idx_lines)}

【用户持仓 8 只（今日涨跌）】
{chr(10).join(hold_lines)}

【AI 五层蛋糕关键股】
{chr(10).join(cake)}

【宏观/债市（yfinance）】
{chr(10).join(macro_lines) if macro_lines else '（暂无）'}

请联网搜索今日（{m.get('d_latest')} 前后）的美股/半导体/AI/美联储最新消息（英伟达、台积电、博通、OpenAI、美联储官员讲话、CME FedWatch 最新概率等），然后输出一个 JSON（不要 markdown 代码块，直接纯 JSON），字段如下：

{{
  "conclusion": "一句话结论（中文，点出今日核心驱动 + 资金流向 + 明日关注）",
  "q4_why_buy": "交易前4问·第1问：为什么买（结合当前 AI 资本开支叙事与软件/半导体业绩）",
  "q4_when_sell": "交易前4问·第2问：什么情况认错卖（给出具体触发条件，如长债破位/CPI超预期）",
  "q4_emotion": "交易前4问·第3问：情绪自评 0-10 分，一句话（≥7 分建议等24小时）",
  "q4_worst": "交易前4问·第4问：最差会怎样（结合风控：单只≤20%/现金≥10%/连亏3笔暂停/财报前不重仓）",
  "fedwatch": {{
    "hike": "9月FOMC加息概率（如≈50%）",
    "hold": "维持不变概率",
    "cut": "降息概率",
    "meeting": "下次FOMC日期",
    "note": "FedWatch 来源与变化说明"
  }},
  "news": [
    {{"title": "新闻标题（含标的/事件）", "detail": "一句话要点", "source": "来源媒体"}}
  ],
  "holdings_alert": "持仓预警：今日 8 只持仓里谁最强/谁最弱/是否有风险信号，一段话",
  "tomorrow_focus": "明日/近期关注事件（非农/CPI/PPI/FOMC/重要财报）"
}}

要求：news 给 6-10 条；所有数字必须来自联网搜索或上面行情数据，禁止编造；中文输出。
"""
    return prompt


def _call(model, prompt, use_search):
    """单次调用，返回 (text, ok)。"""
    url = f"{BASE}/models/{model}:generateContent?key={API_KEY}"
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.4},
    }
    if use_search:
        body["tools"] = [{"googleSearch": {}}]
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    text = data["candidates"][0]["content"]["parts"][0]["text"]
    return text, True


def call_gemini(prompt):
    """多模型 + 重试 + 联网降级链，尽量保证拿到研判。"""
    import time
    # 优先级：联网优先，模型从快→强
    attempts = [
        (MODEL, True),            # gemini-2.5-flash + 联网
        ("gemini-2.5-pro", True), # gemini-2.5-pro + 联网
        (MODEL, False),           # gemini-2.5-flash 纯文本（无联网）
        ("gemini-2.0-flash", True),
        ("gemini-2.0-flash", False),
    ]
    last_err = None
    for model, use_search in attempts:
        for attempt in range(3):
            try:
                text, _ = _call(model, prompt, use_search)
                return parse_json_loose(text)
            except Exception as e:  # noqa: BLE001
                last_err = e
                print(f"  [{model} search={use_search}] 第{attempt+1}次失败: {e}")
                time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"Gemini 全部尝试失败，最后错误: {last_err}")


def parse_json_loose(text):
    """从 Gemini 返回文本中稳健提取 JSON（去掉 markdown 代码块、前后杂质）。"""
    text = text.strip()
    # 去掉 ```json ... ``` 或 ``` ... ``` 包裹
    if text.startswith("```"):
        text = text.strip("`")
        # 去掉首行可能的 json 标记
        first_nl = text.find("\n")
        if first_nl != -1 and text[:first_nl].strip().lower() in ("json", "javascript"):
            text = text[first_nl + 1:]
    # 定位第一个 { 和最后一个 }
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        text = text[start:end + 1]
    return json.loads(text)


def main():
    if not API_KEY:
        print("缺少环境变量 GEMINI_API_KEY，退出")
        return
    m = load_market()
    prompt = build_prompt(m)
    print("调用 Gemini（联网搜索 + 研判）...")
    try:
        analysis = call_gemini(prompt)
    except Exception as e:  # noqa: BLE001
        print(f"Gemini 调用失败: {e}")
        analysis = {
            "conclusion": "（Gemini 调用失败，见日志）",
            "q4_why_buy": "", "q4_when_sell": "", "q4_emotion": "5/10", "q4_worst": "",
            "fedwatch": {"hike": "—", "hold": "—", "cut": "—", "meeting": "—", "note": ""},
            "news": [], "holdings_alert": "", "tomorrow_focus": "",
            "error": str(e),
        }
    analysis["generated_at"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, "analysis.json"), "w", encoding="utf-8") as f:
        json.dump(analysis, f, ensure_ascii=False, indent=2)
    print(f"已写入 analysis.json，结论：{analysis.get('conclusion', '')[:60]}...")


if __name__ == "__main__":
    main()
