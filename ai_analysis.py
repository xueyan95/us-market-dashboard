#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ai_analysis.py — 调用 SiliconFlow（硅基流动，OpenAI 兼容 API）做 AI 研判，输出 analysis.json。

设计要点：
  - OpenAI 兼容 /chat/completions 端点，Bearer token 鉴权
  - response_format: json_object 强制 JSON 输出，无需手动 parse
  - 不支持原生联网（无 googleSearch 等价物）→ 改用 yfinance 拉最近新闻塞进 prompt 当上下文
  - 多模型降级链：72B → 32B → 14B，每档重试 3 次
  - API Key 从环境变量 SILICONFLOW_API_KEY 读取

环境变量：
  SILICONFLOW_API_KEY  — 必填
  SF_MODEL             — 可选，默认 Qwen/Qwen2.5-72B-Instruct
"""
import json
import os
import time
import urllib.request
import urllib.error
import datetime

import yfinance as yf

API_KEY = os.environ.get("SILICONFLOW_API_KEY", "")
MODEL = os.environ.get("SF_MODEL", "Qwen/Qwen2.5-72B-Instruct")
BASE = "https://api.siliconflow.cn/v1"

HOLDINGS = ["LAZR", "INTC", "APP", "BE", "COHR", "WOLF", "NBIS", "NOW"]
NEWS_TICKERS = ["^GSPC", "^IXIC", "NVDA", "AAPL", "MSFT", "TSLA", "GOOGL", "AMZN", "META"]


def load_market():
    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, "market_data.json"), encoding="utf-8") as f:
        return json.load(f)


def fetch_yf_news():
    """拉主流指数/股票最近新闻，去重后取前 12 条。无网络或失败时返回 []. """
    items, seen = [], set()
    for sym in NEWS_TICKERS:
        try:
            t = yf.Ticker(sym)
            for n in (t.news or [])[:2]:
                title = n.get("title", "")
                if title and title not in seen:
                    seen.add(title)
                    items.append({
                        "title": title,
                        "publisher": n.get("publisher", ""),
                        "link": n.get("link", ""),
                    })
        except Exception:
            continue
    return items[:12]


def build_prompt(m, news):
    q = m.get("quotes", {})

    def g(sym):
        x = q.get(sym, {})
        return x.get("last"), x.get("chg_pct")

    def fmt(sym, name):
        p, c = g(sym)
        if p is None:
            return f"{name}: 无数据"
        sign = "+" if (c or 0) > 0 else ""
        return f"{name}: ${p} ({sign}{c}%)"

    idx_lines = [
        fmt("usSPY", "标普500"), fmt("usQQQ", "纳斯达克"),
        fmt("usDIA", "道琼斯"), fmt("usIWM", "罗素2000"),
    ]
    hold_lines = [fmt(f"us{h}", h) for h in HOLDINGS]

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

    yf_data = m.get("yf", {})
    macro_lines = []
    for k, label in [("tnx", "10Y美债"), ("fvx", "5Y美债"), ("tyx", "30Y美债"),
                     ("vix", "VIX"), ("dxy", "美元指数DXY"),
                     ("gold", "黄金"), ("wti", "WTI原油"), ("btc", "BTC")]:
        v = yf_data.get(k, {})
        if v.get("last") is not None:
            c = v.get("chg_pct") or 0
            sign = "+" if c > 0 else ""
            macro_lines.append(f"{label}: {v['last']} ({sign}{c}%)")

    news_text = "\n".join(f"- {n['title']} ({n['publisher']})" for n in news) or "（暂无 yfinance 新闻）"

    return f"""你是专业美股投研分析师。基于以下【实时行情】+【近期新闻上下文】（yfinance 拉取，不保证完全实时）输出纯 JSON。

【交易日】{m.get('d_latest')}（前一交易日 {m.get('d_prev')}）

【核心指数】
{chr(10).join(idx_lines)}

【用户持仓 8 只】
{chr(10).join(hold_lines)}

【AI 五层蛋糕关键股】
{chr(10).join(cake)}

【宏观/债市】
{chr(10).join(macro_lines) if macro_lines else '（暂无）'}

【近期新闻上下文（yfinance，可能非最新）】
{news_text}

请输出 JSON（response_format=json_object 强制 JSON，不要任何 markdown 包裹或额外文字），字段：

{{
  "conclusion": "一句话结论（中文，核心驱动 + 资金流向 + 明日关注）",
  "q4_why_buy": "交易前4问·第1问：为什么买",
  "q4_when_sell": "交易前4问·第2问：什么情况认错卖（具体触发条件）",
  "q4_emotion": "交易前4问·第3问：情绪 0-10 分 + 一句话（≥7 分建议等24小时）",
  "q4_worst": "交易前4问·第4问：最差会怎样（结合风控：单只≤20%/现金≥10%/连亏3笔暂停/财报前不重仓）",
  "fedwatch": {{
    "hike": "9月FOMC加息概率（如≈50%，仅作模型估计）",
    "hold": "维持不变概率",
    "cut": "降息概率",
    "meeting": "下次FOMC日期",
    "note": "FedWatch 来源说明（强调是模型估计非实时数据）"
  }},
  "news": [
    {{"title": "新闻标题", "detail": "一句话要点", "source": "来源媒体或 yfinance"}}
  ],
  "holdings_alert": "持仓预警：今日 8 只持仓里谁最强/谁最弱/是否有风险信号",
  "tomorrow_focus": "明日/近期关注事件（非农/CPI/PPI/FOMC/重要财报）"
}}

要求：news 给 6-10 条；数字尽量来自提供的行情数据，新闻尽量来自上面的 yfinance 上下文；中文输出。
"""


def _call(model, prompt):
    """调用 SiliconFlow chat/completions，返回文本。"""
    url = f"{BASE}/chat/completions"
    body = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "response_format": {"type": "json_object"},
        "temperature": 0.4,
        "max_tokens": 4096,
    }
    req = urllib.request.Request(
        url, data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data["choices"][0]["message"]["content"]


def call_siliconflow(prompt):
    """多模型降级链 + 重试。"""
    models = [
        MODEL,
        "Qwen/Qwen2.5-32B-Instruct",
        "Qwen/Qwen2.5-14B-Instruct",
    ]
    last_err = None
    for m in models:
        for attempt in range(3):
            try:
                text = _call(m, prompt)
                return json.loads(text)
            except (urllib.error.HTTPError, urllib.error.URLError, json.JSONDecodeError, KeyError) as e:
                last_err = e
                print(f"  [{m}] 第{attempt + 1}次失败: {e}")
                time.sleep(2 * (attempt + 1))
            except Exception as e:  # noqa: BLE001
                last_err = e
                print(f"  [{m}] 第{attempt + 1}次异常: {e}")
                time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"SiliconFlow 全部尝试失败，最后错误: {last_err}")


def main():
    if not API_KEY:
        print("缺少环境变量 SILICONFLOW_API_KEY，跳过 AI 研判")
        # 写一个空 analysis，让 pipeline 不挂
        empty = {
            "conclusion": "（未配置 SILICONFLOW_API_KEY，跳过）",
            "q4_why_buy": "", "q4_when_sell": "", "q4_emotion": "5/10", "q4_worst": "",
            "fedwatch": {"hike": "—", "hold": "—", "cut": "—", "meeting": "—", "note": "未配置"},
            "news": [], "holdings_alert": "", "tomorrow_focus": "",
        }
        here = os.path.dirname(os.path.abspath(__file__))
        with open(os.path.join(here, "analysis.json"), "w", encoding="utf-8") as f:
            json.dump(empty, f, ensure_ascii=False, indent=2)
        return

    m = load_market()
    print("拉取近期新闻上下文（yfinance）...")
    news = fetch_yf_news()
    print(f"  拿到 {len(news)} 条新闻")

    prompt = build_prompt(m, news)
    print(f"调用 SiliconFlow（{MODEL}）做 AI 研判...")
    try:
        analysis = call_siliconflow(prompt)
    except Exception as e:  # noqa: BLE001
        print(f"SiliconFlow 调用失败: {e}")
        analysis = {
            "conclusion": "（SiliconFlow 调用失败，见日志）",
            "q4_why_buy": "", "q4_when_sell": "", "q4_emotion": "5/10", "q4_worst": "",
            "fedwatch": {"hike": "—", "hold": "—", "cut": "—", "meeting": "—", "note": ""},
            "news": [], "holdings_alert": "", "tomorrow_focus": "",
            "error": str(e),
        }

    analysis["generated_at"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    analysis["model"] = MODEL
    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, "analysis.json"), "w", encoding="utf-8") as f:
        json.dump(analysis, f, ensure_ascii=False, indent=2)
    print(f"已写入 analysis.json，结论：{analysis.get('conclusion', '')[:60]}...")


if __name__ == "__main__":
    main()