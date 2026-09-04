#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gen_dashboard.py — 数据驱动生成每日美股行情看板 index.html。
读取 market_data.json（行情/财报/宏观）+ analysis.json（SiliconFlow 研判），
生成单文件、零外链、涨红跌绿、三态主题的 HTML。
完全脱离 WorkBuddy。
"""
import json
import os
import datetime
import html as _html

HERE = os.path.dirname(os.path.abspath(__file__))


def esc(s):
    """HTML escape."""
    if s is None:
        return ""
    return _html.escape(str(s), quote=True)

# ---------------- 持仓与五层蛋糕分组（黄仁勋框架） ----------------
HOLDINGS = ["usLAZR", "usINTC", "usAPP", "usBE", "usCOHR", "usWOLF", "usNBIS", "usNOW"]
HOLD_NAME = {"usLAZR": "LAZR", "usINTC": "INTC", "usAPP": "APP", "usBE": "BE",
             "usCOHR": "COHR", "usWOLF": "WOLF", "usNBIS": "NBIS", "usNOW": "NOW"}
HOLD_SET = set(HOLDINGS)

LAYERS = [
    ("⑤ 应用", "应用软件 / 终端 / 消费 AI",
     [("终端/硬件", ["usAAPL", "usTSLA"]),
      ("应用软件/SaaS", ["usNOW", "usSNOW", "usNET", "usAPP", "usCRM", "usPLTR", "usADBE", "usCRWD"])]),
    ("④ 模型", "云厂代理模型：MSFT→OpenAI · GOOGL→Gemini · META→Llama · AMZN→Claude（纯模型公司未上市）",
     [("云厂代理", ["usMSFT", "usGOOGL", "usMETA", "usAMZN"])]),
    ("③ 基础设施", "云 / NeoCloud / 光模块网络设备",
     [("云/Hyperscaler", ["usMSFT", "usAMZN", "usGOOGL", "usMETA", "usORCL"]),
      ("NeoCloud", ["usCRWV", "usNBIS"]),
      ("光模块/网络设备", ["usLAZR", "usFOTO", "usEUV", "usCOHR", "usCRDO", "usANET", "usVRT", "usEQIX"])]),
    ("② 芯片", "GPU / 代工 / 存储 / 设备",
     [("AI芯片/GPU", ["usNVDA", "usAMD", "usAVGO", "usMRVL"]),
      ("代工/IDM", ["usTSM", "usINTC", "usWOLF"]),
      ("存储", ["usMU"]),
      ("设备/材料/IP", ["usASML", "usAMAT", "usARM"])]),
    ("① 能源", "电力 / 核电（AI 供电链）",
     [("电力/IPP", ["usVST", "usCEG", "usGEV"]),
      ("氢能/燃料电池", ["usBE"]),
      ("核能", ["usOKLO"])]),
]

MATRIX_LAYERS = [
    ("⑤ 应用", ["usAAPL", "usTSLA", "usNOW", "usSNOW", "usNET", "usAPP", "usCRM", "usPLTR", "usADBE", "usCRWD"]),
    ("④ 模型 · 云厂代理", ["usMSFT", "usGOOGL", "usMETA", "usAMZN"]),
    ("③ 基础设施 · 云/NeoCloud/光模块网络", ["usORCL", "usCRWV", "usNBIS", "usLAZR", "usFOTO", "usEUV", "usCOHR", "usCRDO", "usANET", "usVRT", "usEQIX"]),
    ("② 芯片", ["usNVDA", "usAMD", "usTSM", "usAVGO", "usMU", "usARM", "usASML", "usAMAT", "usMRVL", "usINTC", "usWOLF"]),
    ("① 能源", ["usVST", "usCEG", "usGEV", "usBE", "usOKLO"]),
]

TREND_LABELS = [("1日", "chg_pct"), ("1周", "p1w"), ("1月", "p1m"), ("3月", "p3m")]

FOCUS = {"NVDA", "AMD", "TSM", "AVGO", "MU", "ARM", "ASML", "AMAT", "MRVL", "CRDO",
         "INTC", "WOLF", "COHR", "LAZR", "FOTO", "EUV", "CRWV", "APP", "NOW", "BE",
         "NBIS", "ORCL", "ANET", "VRT", "EQIX", "AAPL", "TSLA", "SNOW", "NET", "CRM",
         "PLTR", "ADBE", "CRWD", "VST", "CEG", "GEV", "OKLO", "AEHR", "NOK", "CIEN",
         "ZS", "IOT", "GWRE", "DOCU", "PATH", "LULU", "TTC", "AMBA", "MSFT", "AMZN",
         "GOOGL", "META"}

DISCLAIMER = "以上内容基于公开数据，仅供参考，不构成投资建议。市场有风险，投资需谨慎。"


def load_json(name):
    p = os.path.join(HERE, name)
    if not os.path.exists(p):
        return {}
    with open(p, encoding="utf-8") as f:
        return json.load(f)


M = load_json("market_data.json")
A = load_json("analysis.json")

QUOTES = M.get("quotes", {})
SENT = M.get("sentiment", {})
YF = M.get("yf", {})
D_LATEST = M.get("d_latest", "—")
D_PREV = M.get("d_prev", "—")
# 显式指定 UTC+8（北京时间 CST）—— GitHub Actions ubuntu 默认时区是 UTC，
# 用 naive datetime.now() 会把 UTC 时间错标为"北京时间"，提前 8 小时
CST = datetime.timezone(datetime.timedelta(hours=8))
GEN_TIME = datetime.datetime.now(CST).strftime("%Y-%m-%d %H:%M") + "（北京时间）"


def get(sym):
    q = QUOTES.get(sym, {})
    return q.get("last"), q.get("chg_pct")


def fmt_price(sym, digits=2):
    p, _ = get(sym)
    return f"{p:.{digits}f}" if p is not None else "—"


def color(v):
    if v is None:
        return "#8a8f98"
    return "#d23a3a" if v > 0 else ("#0a9e6e" if v < 0 else "#8a8f98")


def arrow(v):
    if v is None:
        return "—"
    return "▲" if v > 0 else ("▼" if v < 0 else "—")


def chg_str(v):
    if v is None:
        return "—"
    return f"{'+' if v > 0 else ''}{v:.2f}%"


def heat_bg(c):
    if c is None:
        return "background:rgba(138,143,152,.10)"
    a = abs(c)
    alpha = min(0.10 + a * 0.045, 0.48)
    rgb = "210,58,58" if c > 0 else "10,158,110"
    return f"background:rgba({rgb},{alpha:.2f})"


def butterfly():
    rows = []
    maxabs = max((abs(get(s)[1] or 0) for s in HOLDINGS), default=0)
    scale = max(maxabs, 0.5)
    for s in HOLDINGS:
        p, c = get(s)
        w = min(abs(c or 0) / scale * 50.0, 50.0)
        col = color(c)
        dirn = "right" if (c or 0) >= 0 else "left"
        style = f"width:{w:.2f}%;background:{col};{'left:50%' if dirn=='right' else 'right:50%'}"
        rows.append(
            f'<div class="row"><b>{HOLD_NAME[s]}</b>'
            f'<div class="barwrap"><div class="zero"></div><div class="bar" style="{style}"></div></div>'
            f'<span style="text-align:right;color:{col}">{fmt_price(s)} {chg_str(c)}</span></div>')
    return ("<div class='butter'>" + "".join(rows) + "</div>"
            f"<div class='note'>蝴蝶图：向右=涨(红)、向左=跌(绿)，中线 0%；横轴满刻度 = 当日持仓最大 |涨跌幅| = ±{maxabs:.2f}%（自适应）。基准 {D_LATEST} vs {D_PREV}。</div>")


def cat_block(cat, items):
    chips = []
    for s in items:
        p, c = get(s)
        ish = s in HOLD_SET
        hc = '<span class="tag-hold">仓</span>' if ish else ""
        chips.append(
            f'<span class="tick{" hold" if ish else ""}" style="{heat_bg(c)}"><b>{s.replace("us","")}</b>{hc} '
            f'<span class="num">{fmt_price(s)}</span> <span class="chg" style="color:{color(c)}">'
            f'{arrow(c)} {chg_str(c)}</span></span>')
    label = f'<div class="catlbl">{cat}</div>' if cat else ""
    return f'<div class="cat">{label}<div>{"".join(chips)}</div></div>'


def layer(title, sub, cats):
    parts = "".join(cat_block(cat, items) for cat, items in cats)
    return (f'<div class="layer"><div class="lh">{title} <span class="lt">{sub}</span></div>'
            f'{parts}</div>')


def heat_cell(v):
    if v is None:
        return '<td style="color:var(--sub)">—</td>'
    a = abs(v)
    alpha = min(0.08 + a * 0.035, 0.55)
    rgb = "210,58,58" if v > 0 else "10,158,110"
    txt = "var(--red)" if v > 0 else "var(--green)"
    return (f'<td style="background:rgba({rgb},{alpha:.2f})">'
            f'<span class="num" style="color:{txt}">{v:+.1f}%</span></td>')


def heat_matrix():
    rows = []
    for lname, syms in MATRIX_LAYERS:
        rows.append(f'<tr class="layer-row"><td colspan="5">{lname}</td></tr>')
        for s in syms:
            name = s.replace("us", "")
            ish = s in HOLD_SET
            hc = '<span class="tag-hold">仓</span>' if ish else ""
            q = QUOTES.get(s, {})
            cells = "".join(heat_cell(q.get(key)) for _, key in TREND_LABELS)
            rows.append(f'<tr><td class="name">{name}{hc}</td>{cells}</tr>')
    return (f'<div class="heat-matrix"><table>'
            f'<tr><th>个股</th><th>1日</th><th>1周</th><th>1月</th><th>3月</th></tr>'
            f'{"".join(rows)}</table></div>')


# ---------------- 各模块内容 ----------------
# 核心指标速览：标普/纳指/道指/罗素 + 美元指数 DXY
# 纳指优先取 QQQ ETF 价格（贴近交易视角），失败 fallback ^IXIC，再 fallback ETF
IDX_MAP = [("标普500 S&P 500", "spx", "usSPY"), ("纳指 QQQ ETF", "qqq", "usQQQ"),
           ("道琼斯工业", "dji", "usDIA"), ("罗素2000", "rut", "usIWM")]
idx_html = ""
for n, yk, etf in IDX_MAP:
    v = YF.get(yk, {})
    last = v.get("last")
    if last is not None:
        c = v.get("chg_pct")
        idx_html += (f'<div class="idx"><div class="l">{n}</div><div class="n">{last:,.2f}</div>'
                     f'<div class="c {"up" if (c or 0) > 0 else "down"}">{arrow(c)} {chg_str(c)}</div></div>')
    else:
        p, c = get(etf)
        if p is None:
            continue
        idx_html += (f'<div class="idx"><div class="l">{n}（ETF近似）</div><div class="n">{p:,.2f}</div>'
                     f'<div class="c {"up" if (c or 0) > 0 else "down"}">{arrow(c)} {chg_str(c)}</div></div>')

# DXY 美元指数（独立块，强调）
v = YF.get("dxy", {})
if v.get("last") is not None:
    c = v.get("chg_pct")
    idx_html += (f'<div class="idx dxy"><div class="l">美元指数 DXY</div><div class="n">{v["last"]:.2f}</div>'
                 f'<div class="c {"up" if (c or 0) > 0 else "down"}">{arrow(c)} {chg_str(c)}</div></div>')
else:
    # yfinance 拿不到时显示空壳，避免布局塌陷
    idx_html += '<div class="idx dxy off"><div class="l">美元指数 DXY</div><div class="n">—</div><div class="c">—</div></div>'

# 涨跌家数（NYSE / NASDAQ）—— A/D ratio > 1 看涨、< 1 看跌
adv_dec = M.get("adv_dec", {})
ad_html = ""
for exch_label, k in [("NYSE", "nyse"), ("NASDAQ", "nasdaq")]:
    ad = adv_dec.get(k) or {}
    if ad and ad.get("total", 0) > 0:
        ratio = ad.get("ad_ratio")
        cls = ""
        if ratio is not None:
            cls = "bull" if ratio > 1 else ("bear" if ratio < 1 else "")
        adv_n, dec_n, unc_n = ad.get("adv", 0), ad.get("dec", 0), ad.get("unc", 0)
        ad_html += (f'<div class="ad-cell"><div class="ex">{exch_label} 涨跌家数</div>'
                    f'<div class="ratio {cls}">{ratio if ratio is not None else "—"}</div>'
                    f'<div class="num">↑ {adv_n} / ↓ {dec_n} / = {unc_n}</div></div>')
    else:
        ad_html += (f'<div class="ad-cell"><div class="ex">{exch_label}</div>'
                    f'<div class="ratio">—</div><div class="num">暂无数据</div></div>')

# 持仓期权 IV / P-C ratio（核心 8 只）
opt_data = M.get("options", {})
opt_html = ""
for s in HOLDINGS:
    sym = HOLD_NAME[s]
    d = opt_data.get(sym) or {}
    iv = d.get("iv_pct")
    pc_oi = d.get("pc_oi")
    call_vol = d.get("call_vol", 0)
    put_vol = d.get("put_vol", 0)
    exp = d.get("expiry", "")
    # IV 解读：高 (>50%) / 中 (30-50%) / 低 (<30%)
    iv_text = "—"
    iv_cls = ""
    if iv is not None:
        if iv > 50:
            iv_text, iv_cls = f"{iv}% 高", "iv-high"
        elif iv < 30:
            iv_text, iv_cls = f"{iv}% 低", "iv-low"
        else:
            iv_text = f"{iv}% 中"
    # P/C 解读（用 OI）：< 0.7 偏看涨、> 1.0 偏看跌
    pc_text, pc_cls = "—", ""
    if pc_oi is not None:
        if pc_oi < 0.7:
            pc_text, pc_cls = f"{pc_oi} 偏看涨", "pc-bull"
        elif pc_oi > 1.0:
            pc_text, pc_cls = f"{pc_oi} 偏看跌", "pc-bear"
        else:
            pc_text = f"{pc_oi} 中性"
    exp_label = exp[5:].replace("-", "/") if exp else "—"
    opt_html += (f'<div class="opt-row"><b>{sym}</b>'
                 f'<span class="iv {iv_cls}">{iv_text}</span>'
                 f'<span class="pc {pc_cls}">{pc_text}</span>'
                 f'<span class="vol">C {call_vol:,} / P {put_vol:,}</span>'
                 f'<span class="exp">到期 {exp_label}</span></div>')

COMBINED = [("半导体 SMH", "usSMH"), ("科技 XLK", "usXLK"), ("软件 IGV", "usIGV"),
            ("金融 XLF", "usXLF"), ("能源 XLE", "usXLE"), ("黄金 GLD", "usGLD"),
            ("小盘 IWM", "usIWM"), ("标普 SPY", "usSPY"), ("纳指 QQQ", "usQQQ"), ("道指 DIA", "usDIA")]


def rsi_label(r):
    """7 档 RSI 信号标签。"""
    if r is None:
        return ""
    if r >= 80: return "极强超买"
    if r >= 70: return "超买"
    if r >= 60: return "偏强"
    if r >= 40: return "中性"
    if r >= 30: return "偏弱"
    if r >= 20: return "超卖"
    return "极弱超卖"


comb_rows = ""
for n, s in COMBINED:
    p, c = get(s)
    d = SENT.get(s, {})
    r = d.get("rsi14"); b20 = d.get("bias20")
    chg_cls = "up" if (c or 0) > 0 else ("down" if (c or 0) < 0 else "flat")
    rc = "up" if (r is not None and r <= 30) else ("down" if (r is not None and r >= 70) else "flat")
    bc = "up" if (b20 is not None and b20 > 0) else ("down" if (b20 is not None and b20 < 0) else "flat")
    label_txt = rsi_label(r)
    # 数字 + 标签：标签放在数字下方（小字），分两行
    r_html = f'{r}<small class="rsi-lbl {rc}">{label_txt}</small>' if r is not None else "—"
    comb_rows += (f'<tr><td>{n}</td><td>{fmt_price(s)}</td>'
                  f'<td class="{chg_cls}">{arrow(c)} {chg_str(c)}</td>'
                  f'<td class="{rc}">{r_html}</td>'
                  f'<td class="{bc}">{"+" if (b20 or 0) > 0 else ""}{b20 if b20 is not None else "—"}%</td></tr>')

# 宏观 kv
def yf_item(label, key, digits=2, prefix="", suffix=""):
    v = YF.get(key, {})
    last = v.get("last")
    if last is None:
        return ""
    c = v.get("chg_pct")
    cls = "up" if (c or 0) > 0 else ("down" if (c or 0) < 0 else "")
    return (f'<div class="it"><div class="k">{label}</div>'
            f'<div class="v {cls}">{prefix}{last:.{digits}f}{suffix}</div>'
            f'<div class="src">{arrow(c)} {chg_str(c)}</div></div>')

macro_items = [
    yf_item("10年期美债收益率", "tnx", 4, suffix="%"),
    yf_item("30年期美债收益率", "tyx", 4, suffix="%"),
    yf_item("VIX 恐慌指数", "vix", 2),
    yf_item("现货黄金", "gold", 1, prefix="$"),
    yf_item("WTI 原油", "wti", 2, prefix="$"),
    yf_item("BTC 比特币", "btc", 0, prefix="$"),
]
macro_kv = "".join(x for x in macro_items if x)

# 财报日历（未来几天 FOCUS 相关）
earnings = M.get("earnings", {})
ear_fwd_rows = ""
today = datetime.date.today().isoformat()
seen = set()


def countdown_label(d_iso):
    """距离今天 N 天：今天 / 明天 / T+3 / 已发布。"""
    delta = (datetime.date.fromisoformat(d_iso) - datetime.date.fromisoformat(today)).days
    if delta < 0:
        return "已发布"
    if delta == 0:
        return "今天"
    if delta == 1:
        return "明天"
    return f"T+{delta}"


for offset in range(6):
    d = (datetime.date.today() + datetime.timedelta(days=offset)).isoformat()
    for r in earnings.get(d, []):
        sym = r.get("symbol", "")
        if sym in FOCUS and sym not in seen:
            seen.add(sym)
            t = r.get("time", "未定")
            dlabel = "今天" if d == today else d[5:].replace("-", "/")
            cd = countdown_label(d)
            ear_fwd_rows += (f'<tr><td><b>{sym}</b></td><td>{r.get("name","")}</td>'
                             f'<td>{dlabel} {t}</td><td class="cd-{cd.replace("+","-").replace("天","day")}"><b>{cd}</b></td>'
                             f'<td>{r.get("epsForecast","")}</td>'
                             f'<td>{r.get("epsLastYear","")}</td></tr>')
if not ear_fwd_rows:
    ear_fwd_rows = '<tr><td colspan="6" style="text-align:center;color:var(--sub);padding:12px">近 6 日无持仓/关注池财报</td></tr>'

# AI 研判
concl = A.get("conclusion", "（暂无研判）")
q4 = A.get("q4_why_buy", ""), A.get("q4_when_sell", ""), A.get("q4_emotion", "5/10"), A.get("q4_worst", "")
news_items = A.get("news", [])
news_source = A.get("news_source", "rss")

# === 主题聚类视图 ===
themes = A.get("news_themes", []) or []
news_by_theme_html = ""
if themes:
    # 主题卡片
    theme_pills = ""
    for i, th in enumerate(themes[:6]):
        theme_pills += (
            f'<div class="theme-card">'
            f'<div class="theme-hd"><span class="theme-no">{i+1}</span>'
            f'<b>{esc(str(th.get("theme","")))}</b></div>'
            f'<div class="theme-hl">{esc(str(th.get("headline","")))}</div>'
            f'<ul class="theme-list">'
        )
        for it in th.get("items", [])[:3]:
            src = esc(str(it.get("source", "")))
            theme_pills += (
                f'<li><span class="src">[{src}]</span> '
                f'{esc(str(it.get("title", "")))}</li>'
            )
        theme_pills += '</ul>'
        tk = esc(str(th.get("takeaway", "")))
        if tk:
            theme_pills += f'<div class="theme-tk">→ {tk}</div>'
        theme_pills += '</div>'
    news_by_theme_html = (
        '<div class="theme-grid">'
        + theme_pills +
        '</div>'
    )

# 原始新闻列表（来自 RSS 多源 news.json；不是 AI 输出的 news）
raw_news = M.get("news", {}).get("items", []) or []
raw_news_count = M.get("news", {}).get("count", 0)
sources_dist = M.get("news", {}).get("sources", {})
sources_label = " · ".join(f"{esc(k)} {v}" for k, v in sources_dist.items()) if sources_dist else ""

raw_news_html = ""
for it in raw_news[:12]:
    title = esc(str(it.get("title", "")))
    summary = esc(str(it.get("summary", "")[:120]))
    src = esc(str(it.get("source", "")))
    pub = it.get("published", "")
    if pub:
        pub = esc(str(pub[5:16].replace("T", " ")))  # MM-DD HH:MM
    raw_news_html += (
        f'<div class="news-card">'
        f'<div class="news-title">{title}</div>'
        f'<div class="news-meta"><span class="src">[{src}]</span> {pub}</div>'
        + (f'<div class="news-sum">{summary}…</div>' if summary else '')
        + '</div>'
    )

# === AI 提炼的结构化信息卡（用户偏好的形式：【类别·子类别】+ 关键数字 + 因果 + 来源） ===
news_cards = A.get("news_cards", []) or []
news_cards_html = ""
for i, c in enumerate(news_cards[:15]):
    cat = esc(str(c.get("category", "")))
    title = esc(str(c.get("title", "")))
    key_data = esc(str(c.get("key_data", "")))
    impact = esc(str(c.get("impact", "")))
    src = esc(str(c.get("source", "")))
    news_cards_html += (
        f'<div class="info-card">'
        f'<div class="info-hd"><span class="info-cat">{cat}</span>'
        f'<span class="info-no">#{i+1}</span></div>'
        f'<div class="info-title">{title}</div>'
        + (f'<div class="info-data">📊 {key_data}</div>' if key_data else '')
        + (f'<div class="info-imp">💡 {impact}</div>' if impact else '')
        + (f'<div class="info-src">[{src}]</div>' if src else '')
        + '</div>'
    )

# === 宏观经济日历（未来 7 天，高重要性） ===
econ_calendar = M.get("econ_calendar", {})
econ_rows = ""
econ_count = 0
today_iso = datetime.date.today().isoformat()
for d_str in sorted(econ_calendar.keys()):
    for e in econ_calendar[d_str]:
        if e.get("weight", 0) < 3:  # 只列高重要性
            continue
        if e.get("is_speech"):  # 跳过讲话 / 休市
            continue
        econ_count += 1
        time_str = e.get("time", "—")
        ev = esc(str(e.get("event", "")))
        prev = esc(str(e.get("previous", "") or "—"))
        fcst = esc(str(e.get("forecast", "") or "—"))
        actual = esc(str(e.get("actual", "") or "—"))
        cd = countdown_label(d_str)
        # 已发布的标"已发布"
        if e.get("actual"):
            actual_cell = f'<td class="cd-done">{actual}</td>'
        else:
            actual_cell = '<td class="muted">—</td>'
        cd_class = "cd-done" if d_str < today_iso else (
            "cd-today" if d_str == today_iso else "cd-future")
        econ_rows += (
            f'<tr>'
            f'<td class="{cd_class}"><b>{cd}</b><br><span class="date-sm">{d_str[5:].replace("-","/")} {time_str}</span></td>'
            f'<td>{ev}</td>'
            f'<td class="muted">{prev}</td>'
            f'<td>{fcst}</td>'
            f'{actual_cell}'
            f'</tr>'
        )
if not econ_rows:
    econ_rows = '<tr><td colspan="5" style="text-align:center;color:var(--sub);padding:12px">近 7 日无高重要性宏观事件</td></tr>'

news_html = "".join(
    f'<li><b>{esc(str(x.get("title","")))}</b>：{esc(str(x.get("detail","")))} <span class="src">[{esc(str(x.get("source","")))}]</span></li>'
    for x in news_items) if news_items else '<li>（暂无新闻）</li>'

fw = A.get("fedwatch", {})
fede_tnx_str = f"{fw.get('tnx_chg_pct', '—')}%" if fw.get('tnx_chg_pct') not in (None, "—") else "—"
hold_alert = A.get("holdings_alert", "")
tomorrow = A.get("tomorrow_focus", "")

# 持仓汇总
hold_summary = ""
strong = []
weak = []
for s in HOLDINGS:
    p, c = get(s)
    if c is not None:
        (strong if c > 0 else weak).append(f"{HOLD_NAME[s]} {chg_str(c)}")
hold_summary = f'<div class="note" style="color:var(--gold)">⭐ 今日持仓：{" / ".join(strong) if strong else "—"}（上涨）；{" / ".join(weak) if weak else "—"}（下跌）。</div>'


# ================= CSS =================
CSS = """
:root{--red:#d23a3a;--green:#0a9e6e;--bg:#0f1115;--card:#181b21;--card2:#20242c;
--txt:#e8eaf0;--sub:#9aa3b2;--line:#2a2f3a;--accent:#4c8dff;--gold:#f6c34d;}
:root[data-theme="light"]{--bg:#f5f6f8;--card:#ffffff;--card2:#eef1f5;
--txt:#1b1e24;--sub:#687080;--line:#e3e6ec;--accent:#2b6de8;--gold:#a87800;}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif;
background:var(--bg);color:var(--txt);line-height:1.55;padding-bottom:40px;transition:background .2s ease,color .2s ease}
.wrap{max-width:1080px;margin:0 auto;padding:0 14px}
header{padding:22px 0 8px}
.hdr-row{display:flex;align-items:flex-start;justify-content:space-between;gap:12px;flex-wrap:wrap}
h1{font-size:21px;font-weight:700;letter-spacing:.5px}
.meta{color:var(--sub);font-size:12.5px;margin-top:6px}
.badge{display:inline-block;background:rgba(168,85,247,.15);color:#a855f7;font-size:11px;padding:2px 8px;border-radius:10px;margin-left:8px;font-weight:600}
.theme-toggle{display:inline-flex;align-items:center;gap:4px;background:var(--card2);border:1px solid var(--line);border-radius:10px;padding:3px;flex-shrink:0}
.tt-label{font-size:11px;color:var(--sub);padding:0 5px 0 8px}
.tt-btn{font-size:11px;padding:4px 9px;border:none;background:transparent;color:var(--sub);border-radius:7px;cursor:pointer;font-weight:500;transition:background .15s ease,color .15s ease}
.tt-btn.active{background:var(--accent);color:#fff}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:16px;margin-top:14px;transition:background .2s ease,border-color .2s ease}
.card h2{font-size:15px;font-weight:700;margin-bottom:12px;display:flex;align-items:center;gap:8px}
.card h2 .tag{font-size:11px;color:var(--accent);font-weight:600}
.sec-desc{color:var(--sub);font-size:12px;margin-bottom:10px}
table{width:100%;border-collapse:collapse;font-size:12.5px}
th,td{padding:7px 8px;text-align:right;border-bottom:1px solid var(--line);white-space:nowrap}
th{color:var(--sub);font-weight:600;font-size:11.5px}
th:first-child,td:first-child{text-align:left}
tr:last-child td{border-bottom:none}
.up{color:var(--red)}.down{color:var(--green)}.flat{color:var(--sub)}
.grid4{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}
.idx{background:var(--card2);border-radius:12px;padding:14px;text-align:center}
.idx .n{font-size:20px;font-weight:700}
.idx .l{font-size:12px;color:var(--sub);margin-bottom:4px}
.idx .c{font-size:13px;font-weight:600}
.idx.dxy{border:1px solid var(--gold);background:linear-gradient(135deg,rgba(246,195,77,.08),var(--card2))}
.idx.dxy .l{color:var(--gold);font-weight:600}
.idx.dxy.off{opacity:.4}
.kv{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}
.kv .it{background:var(--card2);border-radius:12px;padding:12px}
.kv .k{font-size:11.5px;color:var(--sub)}
.kv .v{font-size:17px;font-weight:700;margin-top:3px}
.news{list-style:none;padding:0;margin:0}
.news li{margin:8px 0;font-size:12.5px;color:var(--txt);padding:10px 14px;background:var(--card2);border-radius:8px;border-left:3px solid var(--accent);line-height:1.5}
.news li b{color:var(--txt);display:block;margin-bottom:2px;font-size:13px;font-weight:700}
.news li .src{display:inline-block;color:var(--sub);font-size:11px;margin-top:4px;padding:1px 6px;background:var(--card);border-radius:6px}
.theme-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:10px;margin:6px 0 14px}
.theme-card{background:var(--card2);border-radius:12px;padding:14px;border-left:3px solid var(--accent);transition:transform .15s}
.theme-card:hover{transform:translateY(-2px)}
.theme-hd{display:flex;align-items:center;gap:8px;margin-bottom:6px}
.theme-no{display:inline-flex;width:22px;height:22px;background:var(--accent);color:#fff;border-radius:6px;align-items:center;justify-content:center;font-size:12px;font-weight:700}
.theme-hd b{font-size:14px;color:var(--txt)}
.theme-hl{font-size:12.5px;color:var(--gold);margin:4px 0 8px;font-weight:600}
.theme-list{list-style:none;padding:0;margin:6px 0;font-size:11.5px;color:var(--sub);line-height:1.7}
.theme-list li{padding-left:0}
.theme-list .src{color:var(--accent);font-weight:600}
.theme-tk{margin-top:8px;padding:8px 10px;background:var(--card);border-radius:6px;font-size:11.5px;color:var(--txt);font-style:italic}
.news-details{margin-top:10px}
.news-details summary{cursor:pointer;color:var(--accent);font-size:12.5px;font-weight:600;padding:6px 0;user-select:none}
.news-details summary:hover{color:var(--txt)}
.news-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:8px;margin-top:10px}
.news-card{background:var(--card2);border-radius:8px;padding:10px 12px;border-left:2px solid var(--line);transition:border-color .15s}
.news-card:hover{border-left-color:var(--accent)}
.news-title{font-size:12.5px;color:var(--txt);font-weight:600;line-height:1.4;margin-bottom:4px}
.news-meta{font-size:10.5px;color:var(--sub);display:flex;align-items:center;gap:6px;margin-bottom:4px}
.news-meta .src{background:var(--card);padding:1px 5px;border-radius:4px;font-size:10px}
.news-sum{font-size:11.5px;color:var(--sub);line-height:1.5;margin-top:4px}
.rsi-lbl{display:block;font-size:10px;margin-top:3px;font-weight:700;letter-spacing:.3px}
.rsi-lbl:empty{display:none}
td .rsi-lbl{color:inherit}
.ad-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:10px;margin-top:10px}
.ad-cell{background:var(--card2);border-radius:12px;padding:14px;text-align:center;border:1px solid var(--line)}
.ad-cell .ex{color:var(--sub);font-size:12px;font-weight:600;margin-bottom:6px}
.ad-cell .ratio{font-size:22px;font-weight:800;font-variant-numeric:tabular-nums;margin:4px 0}
.ad-cell .ratio.bull{color:var(--red)}
.ad-cell .ratio.bear{color:var(--green)}
.ad-cell .num{color:var(--sub);font-size:11.5px}
.opt-row{display:grid;grid-template-columns:60px 80px 130px 1fr 110px;gap:8px;align-items:center;padding:9px 12px;background:var(--card2);border-radius:8px;margin:5px 0;font-size:12.5px;border:1px solid var(--line)}
.opt-row b{font-weight:700}
.opt-row .iv{font-weight:700;font-variant-numeric:tabular-nums}
.opt-row .pc{font-variant-numeric:tabular-nums;font-size:12px}

/* 信息卡（AI 提炼的结构化卡片，【类别·子类别】+ 关键数字 + 因果） */
.info-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:8px;margin:6px 0 14px}
.info-card{background:var(--card2);border-radius:10px;padding:12px 14px;border-left:3px solid var(--accent);transition:border-color .15s}
.info-card:hover{border-left-color:var(--red)}
.info-hd{display:flex;justify-content:space-between;align-items:center;margin-bottom:6px}
.info-cat{font-size:11px;font-weight:700;color:var(--accent);background:var(--card);padding:2px 8px;border-radius:4px;letter-spacing:.3px}
.info-no{font-size:10px;color:var(--sub);font-weight:600}
.info-title{font-size:13px;font-weight:700;color:var(--txt);line-height:1.45;margin-bottom:6px}
.info-data{font-size:11.5px;color:var(--red);font-weight:600;margin:4px 0;padding:4px 8px;background:var(--card);border-radius:4px;font-variant-numeric:tabular-nums}
.info-imp{font-size:11.5px;color:var(--txt);line-height:1.5;margin-top:4px;opacity:.9}
.info-src{font-size:10.5px;color:var(--sub);margin-top:6px;font-style:italic}

/* 事件日历的高重要性标记 + 距离标签 */
.cd-done{color:var(--sub);text-decoration:line-through;opacity:.6}
.cd-today{color:var(--red);font-weight:700}
.cd-future{color:var(--txt);font-weight:600}
.date-sm{font-size:10px;color:var(--sub);font-weight:400}
.muted{color:var(--sub)}
.opt-row .pc-bull{color:var(--green)}
.opt-row .pc-bear{color:var(--red)}
.opt-row .vol{color:var(--sub);font-size:11px;font-variant-numeric:tabular-nums}
.opt-row .exp{color:var(--sub);font-size:11px;text-align:right}
.opt-row .iv-high{color:var(--gold)}
.opt-row .iv-low{color:var(--accent)}
.concl{background:var(--card2);border-left:3px solid var(--accent);border-radius:8px;padding:12px 14px;font-size:13px;margin-bottom:12px}
.q4{font-size:12.5px;color:var(--txt)}
.q4 div{margin:5px 0}
.q4 b{color:var(--txt)}
.butter{position:relative;padding:8px 0}
.butter .row{display:grid;grid-template-columns:64px 1fr 110px;align-items:center;gap:8px;margin:9px 0;font-size:12px}
.butter .barwrap{position:relative;height:16px}
.butter .bar{position:absolute;top:0;height:16px;border-radius:4px}
.butter .zero{position:absolute;left:50%;top:0;bottom:0;width:1px;background:var(--line)}
.layer{border:1px solid var(--line);border-radius:10px;padding:10px 12px;margin:8px 0;background:var(--card2)}
.layer .lh{font-weight:700;font-size:12.5px;margin-bottom:4px}
.layer .lt{color:var(--sub);font-size:11.5px;font-weight:400}
.cat{margin:7px 0 2px}
.catlbl{font-size:11px;color:var(--accent);font-weight:600;margin:6px 0 3px}
.tick{display:inline-block;margin:3px 8px 3px 0;font-size:12px;padding:3px 8px;border-radius:8px;border:1px solid var(--line);white-space:nowrap}
.tick .num{color:var(--sub)}
.tick .chg{font-weight:600}
.tick.hold .num,.tick.hold b{font-weight:700}
.tick.hold{border-color:var(--gold)}
.tag-hold{display:inline-block;background:rgba(246,195,77,.16);color:var(--gold);font-size:10px;padding:1px 5px;border-radius:8px;margin-left:2px;font-weight:700}
.note{color:var(--sub);font-size:11px;margin-top:8px}
.heat-matrix{overflow-x:auto;margin-top:4px}
.heat-matrix table{width:100%;border-collapse:collapse;font-size:11.5px;min-width:560px}
.heat-matrix th{font-size:10.5px;color:var(--sub);padding:5px 7px;text-align:center;position:sticky;top:0;background:var(--card)}
.heat-matrix th:first-child{text-align:left}
.heat-matrix td{padding:3px 7px;text-align:center;white-space:nowrap;border-bottom:1px solid var(--line)}
.heat-matrix td.name{text-align:left;font-weight:600}
.heat-matrix .layer-row td{background:var(--card2);font-weight:700;color:var(--accent);font-size:11px;text-align:left;padding:6px 7px;border-top:1px solid var(--line)}
.heat-matrix .num{font-weight:600;font-variant-numeric:tabular-nums}
.foot{color:var(--sub);font-size:11.5px;text-align:center;margin-top:26px;padding:0 14px}
.src{color:var(--sub);font-size:11px}
@media(max-width:640px){
 .grid4{grid-template-columns:repeat(2,1fr)}
 .kv{grid-template-columns:repeat(2,1fr)}
 th,td{font-size:11.5px;padding:6px 5px}
 .butter .row{grid-template-columns:54px 1fr 90px}
}
"""

THEME_JS_HEAD = """<script>(function(){try{var m=localStorage.getItem('wb-dash-theme')||'auto';var d=(m==='auto'?(matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light'):m);document.documentElement.setAttribute('data-theme',d);}catch(e){}})();</script>"""
THEME_JS_BODY = """<script>
(function(){var KEY='wb-dash-theme';var saved=localStorage.getItem(KEY)||'auto';var mq=matchMedia('(prefers-color-scheme: dark)');
function resolve(mode){return mode==='auto'?(mq.matches?'dark':'light'):mode;}
function apply(mode){document.documentElement.setAttribute('data-theme',resolve(mode));
document.querySelectorAll('.tt-btn').forEach(function(b){b.classList.toggle('active',b.getAttribute('data-theme')===mode);});}
document.querySelectorAll('.tt-btn').forEach(function(b){b.addEventListener('click',function(){saved=b.getAttribute('data-theme');localStorage.setItem(KEY,saved);apply(saved);});});
mq.addEventListener('change',function(){if(saved==='auto')apply('auto');});apply(saved);})();
</script>"""


body = f"""
<div class="wrap">
<header>
  <div class="hdr-row">
    <div><h1>每日美股行情看板 <span class="badge">{D_LATEST} 收盘复盘</span></h1></div>
    <div class="theme-toggle" role="group" aria-label="主题切换">
      <span class="tt-label">主题</span>
      <button class="tt-btn" data-theme="auto">跟随系统</button>
      <button class="tt-btn" data-theme="light">白天</button>
      <button class="tt-btn" data-theme="dark">夜间</button>
    </div>
  </div>
  <div class="meta">生成：{GEN_TIME} · 数据截至 {D_LATEST} 美东收盘（vs {D_PREV}） · 涨红跌绿（中国习惯）· 数据源：westockdata / Nasdaq / yfinance / SiliconFlow（Qwen2.5-72B）</div>
</header>

<div class="card">
  <h2>① AI 研判 <span class="tag">SiliconFlow · Qwen2.5-72B</span></h2>
  <div class="concl">{concl}</div>
  <div class="q4">
    <div><b>① 为什么买？</b> {q4[0]}</div>
    <div><b>② 什么情况认错卖？</b> {q4[1]}</div>
    <div><b>③ 情绪几分（0-10）？</b> <b>{q4[2]}</b>；≥7 分请等 24 小时再操作。</div>
    <div><b>④ 最差会怎样？</b> {q4[3]}</div>
  </div>
</div>

<div class="card">
  <h2>② 核心指标速览 <span class="tag">{D_LATEST} 收盘</span></h2>
  <div class="grid4">{idx_html}</div>
  <h2 style="font-size:13.5px;margin-top:16px">市场宽度 · 涨跌家数 <span class="tag">A/D ratio</span></h2>
  <div class="ad-grid">{ad_html}</div>
  <div class="note">标普/纳指/道指/罗素 + DXY：来源 yfinance（纳指优先用 QQQ ETF 价格）；涨跌家数：StockAnalysis 实时 NYSE/NASDAQ 全量股票分桶计算，{D_LATEST}。</div>
</div>

<div class="card">
  <h2>③ 宏观数据 <span class="tag">债市 / 商品</span></h2>
  <div class="kv">{macro_kv or '<div class="it"><div class="k">暂无</div><div class="v">—</div></div>'}</div>
  <div class="note">来源：yfinance（^TNX/^TYX/^VIX/GC=F/CL=F/BTC-USD），{D_LATEST} 收盘。联邦基金目标区间与 FedWatch 概率见「利率预期」模块。</div>
</div>

<div class="card">
  <h2>④ 市场情绪 · 板块 <span class="tag">涨跌 + 超买超卖</span></h2>
  <div class="sec-desc">RSI(14) &gt;70 超买（绿，回调风险）/ &lt;30 超卖（红，机会）；20日乖离率 = 现价偏离 20 日均线。由 westockdata 70 日K线计算。</div>
  <table>
    <tr><th>板块/标的</th><th>最新价</th><th>涨跌幅</th><th>RSI(14)</th><th>20日乖离率</th></tr>
    {comb_rows}
  </table>
</div>

<div class="card">
  <h2>⑤ 持仓与观察</h2>
  <h2 style="font-size:13.5px">核心持仓 · 蝴蝶图（8只 · {D_LATEST} 收盘）</h2>
  {butterfly()}
  {hold_summary}
  <h2 style="font-size:13.5px;margin-top:18px">观察分组 · AI 五层蛋糕（黄仁勋框架 · 自上而下）</h2>
  <div class="sec-desc">标「仓」者为当前持仓；数据为 {D_LATEST} 收盘涨跌幅。</div>
  {layer(*LAYERS[0])}
  {layer(*LAYERS[1])}
  {layer(*LAYERS[2])}
  {layer(*LAYERS[3])}
  {layer(*LAYERS[4])}
  <h2 style="font-size:13.5px;margin-top:20px">趋势热力矩阵 <span class="tag">1日 / 1周 / 1月 / 3月</span></h2>
  <div class="sec-desc">行=个股（按五层分组），列=多周期涨跌幅；背景色块深浅=幅度，红=涨、绿=跌。数据：westockdata 70 日K线，截至 {D_LATEST}。</div>
  {heat_matrix()}
</div>

<div class="card">
  <h2>⑥ 重要信息 <span class="tag">AI 提炼 · {len(news_cards)} 张信息卡</span></h2>

  <div class="sec-desc">基于 RSS 多源新闻（已分类主题），由 SiliconFlow 提炼 {len(news_cards)} 张结构化信息卡：每张含【类别·子类别】+ 关键数字 + 因果 + 来源。下方为全部 RSS 原文（{raw_news_count} 条 / {len(sources_dist)} 个源）。</div>

  <div class="info-grid">{news_cards_html}</div>

  {('<details class="news-details"><summary>📰 主题聚类视图（' + str(len(themes)) + ' 个主题）</summary>' + news_by_theme_html + '</details>') if news_by_theme_html else ''}

  <details class="news-details">
    <summary>📜 查看全部 {raw_news_count} 条原始新闻（按时间倒序）</summary>
    <div class="news-grid">{raw_news_html}</div>
  </details>
</div>

<div class="card">
  <h2>⑦ 利率预期 <span class="tag">实时数据 + AI 定性</span></h2>
  <div class="sec-desc">
    当前联邦基金目标区间：<b>{fw.get("current_range","—")}</b>；
    下次 FOMC：<b>{fw.get("next_meeting","—")} {fw.get("next_meeting_time","")}</b>；
    收益率曲线 2s10s：<b>{fw.get("curve_2s10s_bp","—")} bp</b>
    （正值=陡峭扩张 / 负值=倒挂）。
  </div>
  <div class="kv kv-fedwatch">
    <div class="it">
      <div class="k">AI 综合定性</div>
      <div class="v" style="font-size:16px">{fw.get("stance","—")}</div>
    </div>
    <div class="it">
      <div class="k">最新 CPI</div>
      <div class="v" style="font-size:14px">{fw.get("latest_cpi","—")}</div>
    </div>
    <div class="it">
      <div class="k">最新 非农</div>
      <div class="v" style="font-size:14px">{fw.get("latest_nfp","—")}</div>
    </div>
    <div class="it">
      <div class="k">曲线 / 10Y</div>
      <div class="v" style="font-size:14px">{fw.get("curve_2s10s_bp","—")}bp / {fede_tnx_str}</div>
    </div>
  </div>
  <div class="note"><b>立场理由</b>：{fw.get("stance_reason","") or "—"}</div>
  <div class="note">{fw.get("note","")}</div>
</div>

<div class="card">
  <h2>⑧ 事件日历 <span class="tag">宏观 + AI 五层蛋糕持仓/关注池财报</span></h2>
  <div class="sec-desc">
    未来 7 天高重要性宏观数据（来自 westock 经济日历，权重≥3 事件，含前值/预期/实际）。
    下方为持仓/关注池（AI 五层蛋糕全部 {len(FOCUS)} 只标的）近 6 日财报（Nasdaq keyless 接口）。
  </div>
  <table>
    <tr><th>距今</th><th>事件</th><th>前值</th><th>预期</th><th>实际</th></tr>
    {econ_rows}
  </table>
  <h3 style="margin-top:18px;font-size:13.5px;color:var(--accent)">📊 持仓/关注池 · 近 6 日财报（{len([s for s in ear_fwd_rows.split('<tr>') if s.startswith('<td>')]) if ear_fwd_rows and '无' not in ear_fwd_rows else 0} 条）</h3>
  <table>
    <tr><th>代码</th><th>公司</th><th>日期/时间</th><th>距离</th><th>EPS预测</th><th>去年同期</th></tr>
    {ear_fwd_rows}
  </table>
</div>

<div class="card">
  <h2>⑨ 持仓期权信号 <span class="tag">IV / P-C ratio · 8 只</span></h2>
  <div class="sec-desc">隐含波动率 (IV) 反映市场对后续波动的预期；P/C ratio（用 OI 计算）> 1 偏看跌，&lt; 0.7 偏看涨。来源：yfinance option_chain，取 14-45 DTE 到期日。失败/无数据项显示 —。</div>
  {opt_html or '<div class="note">暂无期权数据</div>'}
</div>

<div class="foot">{DISCLAIMER}</div>
</div>
"""

html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="theme-color" content="#0f1115">
<title>每日美股行情看板 · {D_LATEST} 收盘复盘</title>
{THEME_JS_HEAD}
<style>{CSS}</style>
</head>
<body>{body}
{THEME_JS_BODY}
</body>
</html>"""

out = os.path.join(HERE, "index.html")
with open(out, "w", encoding="utf-8") as f:
    f.write(html)
print(f"已写入 {out}（{len(html)} 字节）")
