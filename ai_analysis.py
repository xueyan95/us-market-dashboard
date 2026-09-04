#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ai_analysis.py — 调用 SiliconFlow（硅基流动，OpenAI 兼容 API）做 AI 研判，输出 analysis.json。

设计要点：
  - OpenAI 兼容 /chat/completions 端点，Bearer token 鉴权
  - response_format: json_object 强制 JSON 输出，无需手动 parse
  - 不支持原生联网（无 googleSearch 等价物）→ 改用 fetch_news.py 抓的 RSS 多源新闻做上下文
  - 主题聚类：让模型把 20-30 条原始新闻聚成 4-6 大主题 + AI 摘要
  - 多模型降级链：72B → 32B → 14B，每档重试 3 次
  - API Key 从环境变量 SILICONFLOW_API_KEY 读取

环境变量：
  SILICONFLOW_API_KEY  — 必填
  SF_MODEL             — 可选，默认 Qwen/Qwen2.5-72B-Instruct
"""
import datetime
import json
import os
import time
import urllib.error
import urllib.request

import yfinance as yf

API_KEY = os.environ.get("SILICONFLOW_API_KEY", "")
MODEL = os.environ.get("SF_MODEL", "Qwen/Qwen2.5-72B-Instruct")
BASE = "https://api.siliconflow.cn/v1"

HOLDINGS = ["LAZR", "INTC", "APP", "BE", "COHR", "WOLF", "NBIS", "NOW"]
NEWS_TICKERS = ["^GSPC", "^IXIC", "NVDA", "AAPL", "MSFT", "TSLA", "GOOGL", "AMZN"]


def load_market():
    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, "market_data.json"), encoding="utf-8") as f:
        return json.load(f)


def load_news():
    """读 fetch_news.py 抓的 RSS 多源新闻。优先 news.json，没有再退到 yfinance。

    返回 (items, source_label)，items 是 [{title, source, summary, themes?}, ...]。
    """
    here = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(here, "news.json")
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            items = data.get("items", [])
            if items:
                return items[:30], "rss"
        except Exception as e:  # noqa: BLE001
            print(f"  [news.json] 读取失败: {e}")
    return fetch_yf_news(), "yfinance"


def fetch_yf_news():
    """yfinance 兜底：拉主流指数/股票最近新闻，去重后取前 12 条。"""
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
                        "source": f"yfinance:{sym}",
                        "publisher": n.get("publisher", ""),
                        "link": n.get("link", ""),
                    })
        except Exception:
            continue
    return items[:12]


def build_prompt(m, news, news_source):
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

    # 新闻上下文：RSS 多源已经分类过 themes，让模型用这个粗分类做参考
    news_lines = []
    for n in news:
        themes = "/".join(n.get("themes", [])) or "general"
        src = n.get("source", "?")
        news_lines.append(f"- [{src}|{themes}] {n['title']}")
    news_text = "\n".join(news_lines) or "（暂无新闻）"

    # 利率预期面板（实时数据驱动 + AI 定性）
    fedwatch = m.get("fedwatch", {})

    # 未来 7 天重要宏观事件（精简展示）
    econ_calendar = m.get("econ_calendar", {})
    econ_lines = []
    today_iso = datetime.date.today().isoformat()
    for d_str in sorted(econ_calendar.keys()):
        if d_str < today_iso:
            continue  # 已发布的略过
        for e in econ_calendar[d_str]:
            ev = e.get("event", "")
            if e.get("weight", 0) >= 3:  # 只列高重要性
                actual = e.get("actual", "")
                actual_str = f" 实际={actual}" if actual else ""
                forecast = e.get("forecast", "")
                forecast_str = f" 预期={forecast}" if forecast else ""
                econ_lines.append(f"- {d_str} {e.get('time', '—')} {ev}（权重{e['weight']}）{forecast_str}{actual_str}")
    econ_text = "\n".join(econ_lines[:15]) or "（近 7 日无高重要性宏观数据）"

    return f"""你是专业美股投研分析师。基于【实时行情】+【多源新闻上下文】（已用本地粗分类标记主题）输出纯 JSON。

【交易日】{m.get('d_latest')}（前一交易日 {m.get('d_prev')}）

【核心指数】
{chr(10).join(idx_lines)}

【用户持仓 8 只】
{chr(10).join(hold_lines)}

【AI 五层蛋糕关键股】
{chr(10).join(cake)}

【宏观/债市/商品】
{chr(10).join(macro_lines) if macro_lines else '（暂无）'}

【利率预期面板（实时数据）】
- 当前联邦基金目标区间：{fedwatch.get('current_range', '—')}
- 下次 FOMC 决议：{fedwatch.get('next_meeting', '—')} {fedwatch.get('next_meeting_time', '')}
- 收益率曲线 2s10s：{fedwatch.get('curve_2s10s', '—')} bp（正值=陡峭/扩张，负值=倒挂）
- 10Y 当日变动：{fedwatch.get('tnx_chg_pct', '—')}%
- DXY 当日变动：{fedwatch.get('dxy_chg_pct', '—')}%
- 已发布 CPI（最近一次）：{fedwatch.get('latest_cpi', {}).get('value', '—') if fedwatch.get('latest_cpi') else '—'}（{fedwatch.get('latest_cpi', {}).get('date', '—') if fedwatch.get('latest_cpi') else '暂无'}）
- 已发布 非农（最近一次）：{fedwatch.get('latest_nfp', {}).get('value', '—') if fedwatch.get('latest_nfp') else '—'}（{fedwatch.get('latest_nfp', {}).get('date', '—') if fedwatch.get('latest_nfp') else '暂无'}）

【未来 7 天重要宏观数据（来自 westock 经济日历，仅高重要性）】
{econ_text}

【近期多源新闻上下文（{news_source}，已分类主题）】
{news_text}

请输出 JSON（response_format=json_object 强制 JSON，不要任何 markdown 包裹或额外文字），字段：

{{
  "conclusion": "一句话结论（中文，核心驱动 + 资金流向 + 明日关注）",
  "q4_why_buy": "交易前4问·第1问：为什么买",
  "q4_when_sell": "交易前4问·第2问：什么情况认错卖（具体触发条件）",
  "q4_emotion": "交易前4问·第3问：情绪 0-10 分 + 一句话（≥7 分建议等24小时）",
  "q4_worst": "交易前4问·第4问：最差会怎样（结合风控：单只≤20%/现金≥10%/连亏3笔暂停/财报前不重仓）",
  "fedwatch": {{
    "stance": "鸽派 / 中性 / 鹰派（基于收益率曲线 + 最新 CPI/非农/PMI + 联储票委表态综合判断）",
    "stance_reason": "定性判断理由（≤50 字）",
    "next_meeting": "{fedwatch.get('next_meeting', '—')} {fedwatch.get('next_meeting_time', '')}".strip(),
    "current_range": "{fedwatch.get('current_range', '—')}",
    "curve_2s10s_bp": "{fedwatch.get('curve_2s10s', '—')}",
    "latest_cpi": "{fedwatch.get('latest_cpi', {}).get('value', '—') if fedwatch.get('latest_cpi') else '—'}（{fedwatch.get('latest_cpi', {}).get('date', '—') if fedwatch.get('latest_cpi') else '—'}）",
    "latest_nfp": "{fedwatch.get('latest_nfp', {}).get('value', '—') if fedwatch.get('latest_nfp') else '—'}（{fedwatch.get('latest_nfp', {}).get('date', '—') if fedwatch.get('latest_nfp') else '—'}）",
    "note": "本面板为定性判断（基于实时数据 + AI 综合），非 CME FedWatch 精确概率"
  }},
  "news_themes": [
    {{"theme": "主题名（如 央行政策 / AI芯片 / 地缘 / 公司财报 / 大宗商品）", "headline": "主题一句话概括", "items": [{{"title": "该主题下新闻标题", "source": "媒体源"}}], "takeaway": "对市场含义一句话"}}
  ],
  "news_cards": [
    {{"category": "宏观·美联储", "title": "一句话标题", "key_data": "关键数字（含单位）", "impact": "因果或市场影响", "source": "Bloomberg/WSJ/CNBC"}}
  ],
  "news": [
    {{"title": "原始新闻标题（挑最重要 5-8 条）", "detail": "一句话要点", "source": "媒体源或 ticker"}}
  ],
  "holdings_alert": "持仓预警：今日 8 只持仓里谁最强/谁最弱/是否有风险信号",
  "tomorrow_focus": "明日/近期关注事件（基于宏观经济日历，含日期+时间+预期）"
}}

要求：
- news_themes 给 4-6 个主题聚类，每个主题 items 限 2-4 条新闻标题，不要包含详细正文
- news_cards 给 12-15 条结构化信息卡，覆盖以下类别：
  ·【宏观·美联储/欧央行/利率】（鸽鹰表态、CPI/非农/PPI 解读、点阵图预期）
  ·【AI·并购/资本运作】（重大收购、定增、IPO）
  ·【AI·模型/产品发布】（GPT-6、Gemini、Claude、Sora 等新版本）
  ·【AI·业绩/指引】（超预期/不及预期 + 具体数字）
  ·【能源·电力】（AI 电力、核电、油价、天然气）
  ·【半导体】（芯片股回调、AI capex、出口管制）
  ·【加密/避险】（BTC 涨跌、稳定币、黄金）
  ·【地缘/政治】（中东、俄乌、中美芯片战）
  ·【国内/中概】（A 股、H 股、中概回港）
  每条卡片必须有【具体数字】（涨跌幅、价格、概率、估值、营收等可量化信息），并标注来源
- news 给 5-8 条精选（跨主题）
- 数字尽量来自提供的行情数据；新闻尽量来自上面多源上下文
- 中文输出
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
        empty = {
            "conclusion": "（未配置 SILICONFLOW_API_KEY，跳过）",
            "q4_why_buy": "", "q4_when_sell": "", "q4_emotion": "5/10", "q4_worst": "",
            "fedwatch": {"stance": "—", "stance_reason": "", "next_meeting": "—",
                         "current_range": "—", "curve_2s10s_bp": "—",
                         "latest_cpi": "—", "latest_nfp": "—", "note": "未配置"},
            "news_themes": [], "news_cards": [], "news": [],
            "holdings_alert": "", "tomorrow_focus": "",
        }
        here = os.path.dirname(os.path.abspath(__file__))
        with open(os.path.join(here, "analysis.json"), "w", encoding="utf-8") as f:
            json.dump(empty, f, ensure_ascii=False, indent=2)
        return

    m = load_market()
    news, news_source = load_news()
    print(f"加载新闻上下文: 来源={news_source}, {len(news)} 条")

    prompt = build_prompt(m, news, news_source)
    print(f"调用 SiliconFlow（{MODEL}）做 AI 研判...")
    try:
        analysis = call_siliconflow(prompt)
    except Exception as e:  # noqa: BLE001
        print(f"SiliconFlow 调用失败: {e}")
        analysis = {
            "conclusion": "（SiliconFlow 调用失败，见日志）",
            "q4_why_buy": "", "q4_when_sell": "", "q4_emotion": "5/10", "q4_worst": "",
            "fedwatch": {"stance": "—", "stance_reason": "", "next_meeting": "—",
                         "current_range": "—", "curve_2s10s_bp": "—",
                         "latest_cpi": "—", "latest_nfp": "—", "note": ""},
            "news_themes": [], "news_cards": [], "news": [],
            "holdings_alert": "", "tomorrow_focus": "",
            "error": str(e),
        }

    analysis["generated_at"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    analysis["model"] = MODEL
    analysis["news_source"] = news_source
    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, "analysis.json"), "w", encoding="utf-8") as f:
        json.dump(analysis, f, ensure_ascii=False, indent=2)
    print(f"已写入 analysis.json，结论：{analysis.get('conclusion', '')[:60]}...")


if __name__ == "__main__":
    main()
