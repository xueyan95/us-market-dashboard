#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gen_dashboard.py — 数据驱动生成每日美股行情看板 index.html。
读取 market_data.json（行情/财报/宏观）+ analysis.json（Gemini 研判），
生成单文件、零外链、涨红跌绿、三态主题的 HTML。
完全脱离 WorkBuddy。
"""
import json
import os
import datetime

HERE = os.path.dirname(os.path.abspath(__file__))

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
         "INTC", "WOLF", "COHR", "LAZR", "APP", "NOW", "BE", "NBIS", "ORCL", "ANET",
         "VRT", "EQIX", "AAPL", "TSLA", "SNOW", "NET", "CRM", "PLTR", "ADBE", "CRWD",
         "VST", "CEG", "GEV", "OKLO", "AEHR", "NOK", "CIEN", "ZS", "IOT", "GWRE",
         "DOCU", "PATH", "LULU", "TTC", "AMBA", "MSFT", "AMZN", "GOOGL", "META"}

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
GEN_TIME = datetime.datetime.now().strftime("%Y-%m-%d %H:%M") + "（北京时间）"


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
# 核心指标速览：优先用 yfinance 的真实指数点位（^GSPC/^IXIC/^DJI/^RUT），失败则回退 ETF
IDX_MAP = [("标普500 S&P 500", "spx", "usSPY"), ("纳斯达克综合", "ndx", "usQQQ"),
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

COMBINED = [("半导体 SMH", "usSMH"), ("科技 XLK", "usXLK"), ("软件 IGV", "usIGV"),
            ("金融 XLF", "usXLF"), ("能源 XLE", "usXLE"), ("黄金 GLD", "usGLD"),
            ("小盘 IWM", "usIWM"), ("标普 SPY", "usSPY"), ("纳指 QQQ", "usQQQ"), ("道指 DIA", "usDIA")]
comb_rows = ""
for n, s in COMBINED:
    p, c = get(s)
    d = SENT.get(s, {})
    r = d.get("rsi14"); b20 = d.get("bias20")
    chg_cls = "up" if (c or 0) > 0 else ("down" if (c or 0) < 0 else "flat")
    rc = "up" if (r is not None and r <= 30) else ("down" if (r is not None and r >= 70) else "flat")
    bc = "up" if (b20 is not None and b20 > 0) else ("down" if (b20 is not None and b20 < 0) else "flat")
    comb_rows += (f'<tr><td>{n}</td><td>{fmt_price(s)}</td>'
                  f'<td class="{chg_cls}">{arrow(c)} {chg_str(c)}</td>'
                  f'<td class="{rc}">{r if r is not None else "—"}</td>'
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
for offset in range(6):
    d = (datetime.date.today() + datetime.timedelta(days=offset)).isoformat()
    for r in earnings.get(d, []):
        sym = r.get("symbol", "")
        if sym in FOCUS and sym not in seen:
            seen.add(sym)
            t = r.get("time", "未定")
            dlabel = "今天" if d == today else d[5:].replace("-", "/")
            ear_fwd_rows += (f'<tr><td><b>{sym}</b></td><td>{r.get("name","")}</td>'
                             f'<td>{dlabel} {t}</td><td>{r.get("epsForecast","")}</td>'
                             f'<td>{r.get("epsLastYear","")}</td></tr>')
if not ear_fwd_rows:
    ear_fwd_rows = '<tr><td colspan="5" style="text-align:center;color:var(--sub);padding:12px">近 6 日无持仓/关注池财报</td></tr>'

# AI 研判
concl = A.get("conclusion", "（暂无研判）")
q4 = A.get("q4_why_buy", ""), A.get("q4_when_sell", ""), A.get("q4_emotion", "5/10"), A.get("q4_worst", "")
news_items = A.get("news", [])
news_html = "".join(
    f'<li><b>{x.get("title","")}</b>：{x.get("detail","")} <span class="src">[{x.get("source","")}]</span></li>'
    for x in news_items) if news_items else '<li>（暂无新闻）</li>'

fw = A.get("fedwatch", {})
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
.grid3{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}
.idx{background:var(--card2);border-radius:12px;padding:14px;text-align:center}
.idx .n{font-size:20px;font-weight:700}
.idx .l{font-size:12px;color:var(--sub);margin-bottom:4px}
.idx .c{font-size:13px;font-weight:600}
.kv{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}
.kv .it{background:var(--card2);border-radius:12px;padding:12px}
.kv .k{font-size:11.5px;color:var(--sub)}
.kv .v{font-size:17px;font-weight:700;margin-top:3px}
.news li{margin:7px 0;font-size:12.5px;color:var(--txt)}
.news li b{color:var(--txt)}
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
 .grid3{grid-template-columns:1fr}
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
  <div class="meta">生成：{GEN_TIME} · 数据截至 {D_LATEST} 美东收盘（vs {D_PREV}） · 涨红跌绿（中国习惯）· 数据源：westockdata / Nasdaq / yfinance / Gemini 联网</div>
</header>

<div class="card">
  <h2>① AI 研判 <span class="tag">Gemini · 联网</span></h2>
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
  <div class="grid3">{idx_html}</div>
  <div class="note">三大指数 + 罗素2000 由 ETF（SPY/QQQ/DIA/IWM）日K近似，来源 westockdata，{D_LATEST} 收盘。</div>
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
  <h2>⑥ 重要信息 <span class="tag">半导体 / AI 专题</span></h2>
  <ul class="news">{news_html}</ul>
  <div class="note">来源：Gemini 联网检索（Google Search grounding），{GEN_TIME}。</div>
</div>

<div class="card">
  <h2>⑦ 利率预期 <span class="tag">CME FedWatch</span></h2>
  <div class="sec-desc">下次 FOMC：{fw.get("meeting","—")}。当前目标区间 3.50%–3.75%。</div>
  <div class="kv">
    <div class="it"><div class="k">加息概率</div><div class="v">{fw.get("hike","—")}</div></div>
    <div class="it"><div class="k">维持不变</div><div class="v">{fw.get("hold","—")}</div></div>
    <div class="it"><div class="k">降息概率</div><div class="v">{fw.get("cut","—")}</div></div>
    <div class="it"><div class="k">下次决议</div><div class="v" style="font-size:15px">{fw.get("meeting","—")}</div></div>
  </div>
  <div class="note">{fw.get("note","")}</div>
</div>

<div class="card">
  <h2>⑧ 事件日历 <span class="tag">财报 + 前瞻</span></h2>
  <div class="sec-desc">近 6 日持仓/关注池财报（Nasdaq keyless 接口）。</div>
  <table>
    <tr><th>代码</th><th>公司</th><th>日期/时间</th><th>EPS预测</th><th>去年同期</th></tr>
    {ear_fwd_rows}
  </table>
  <div class="note" style="margin-top:10px">近期宏观节点：{tomorrow or '（暂无）'}</div>
  <div class="note">持仓预警：{hold_alert or '（暂无）'}</div>
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
