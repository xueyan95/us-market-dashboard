#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fetch_data.py — 拉取美股行情 + 财报 + 情绪指标，输出 market_data.json。
完全脱离 WorkBuddy，可在 GitHub Actions 上运行。

数据源（全部公开、零 Key）：
  1. westock-data-clawhub (npm)  —— 日 K 线（行情 / RSI / 乖离率 / 多周期涨跌）
  2. Nasdaq keyless API          —— 财报日历
  3. yfinance                    —— 指数 / VIX / 美债 / 黄金 / BTC
"""
import json
import subprocess
import datetime
import os
import sys
import time
import urllib.request
import concurrent.futures as cf
from portfolio import holding_names, holding_symbols, load_portfolio_config, option_underlyings
from portfolio_snapshot import load_portfolio_snapshot, snapshot_equity_symbols

# ---------------- 配置 ----------------
ALL_SYMS = (
    "usSPY,usQQQ,usIWM,usDIA,usSMH,usXLK,usIGV,usXLF,usXLE,usGLD,"
    "usNVDA,usAMD,usTSM,usAVGO,usMU,usARM,usASML,usAMAT,usMRVL,usCRDO,"
    "usINTC,usWOLF,usCOHR,usMSFT,usAMZN,usGOOGL,usMETA,usORCL,usCRWV,usNBIS,"
    "usANET,usVRT,usEQIX,usLAZR,usFOTO,usEUV,usNOW,usSNOW,usNET,usAPP,"
    "usCRM,usPLTR,usADBE,usCRWD,usAAPL,usTSLA,usVST,usCEG,usGEV,usBE,usOKLO,usNOK,usAEHR,"
    "usCOHX,usNBIL,usNOWL,usBEX,usAPPX"
)
PORTFOLIO_CONFIG = load_portfolio_config()
HOLDINGS = holding_symbols(PORTFOLIO_CONFIG, market_prefix=True)
HOLD_NAME = holding_names(PORTFOLIO_CONFIG)
OPTION_UNDERLYINGS = option_underlyings(PORTFOLIO_CONFIG)

# A/D 涨跌家数自算样本：60 只代表性头部股票（覆盖 90%+ 市值）
AD_SYMS_NYSE = [
    # 金融 10
    "JPM", "BAC", "WFC", "C", "GS", "MS", "BLK", "AXP", "V", "MA",
    # 医疗 7
    "JNJ", "PFE", "MRK", "ABBV", "LLY", "ABT", "TMO",
    # 能源 5
    "XOM", "CVX", "COP", "SLB", "OXY",
    # 消费 8
    "WMT", "HD", "PG", "KO", "PEP", "MCD", "COST", "NKE",
]
AD_SYMS_NASDAQ = [
    # 七巨头 7
    "AAPL", "MSFT", "AMZN", "NVDA", "META", "GOOGL", "TSLA",
    # 半导体 8
    "AVGO", "AMD", "INTC", "QCOM", "TXN", "AMAT", "MU", "ARM",
    # 软件/AI 8
    "ORCL", "CRM", "ADBE", "PLTR", "APP", "NOW", "SNOW", "CRWD",
    # 网络/其他 7
    "NFLX", "PANW", "DDOG", "ADSK", "MCHP", "CSCO", "TMUS",
]


def _yf_chg(sym):
    """单 ticker 拉 5 日 K 线，返回当日 chg_pct。失败/NaN 返回 None。"""
    try:
        import yfinance as yf
        import math
        h = yf.Ticker(sym).history(period="5d", interval="1d")
        if h is None or h.empty or len(h["Close"]) < 2:
            return None
        last, prev = float(h["Close"].iloc[-1]), float(h["Close"].iloc[-2])
        if prev == 0 or not math.isfinite(last) or not math.isfinite(prev):
            return None
        return (last / prev - 1) * 100
    except Exception:
        return None

# 关注池（财报过滤用）
FOCUS = {"NVDA", "AMD", "TSM", "AVGO", "MU", "ARM", "ASML", "AMAT", "MRVL", "CRDO",
         "INTC", "WOLF", "COHR", "LAZR", "FOTO", "EUV", "CRWV", "APP", "NOW", "BE",
         "NBIS", "ORCL", "ANET", "VRT", "EQIX", "AAPL", "TSLA", "SNOW", "NET", "CRM",
         "PLTR", "ADBE", "CRWD", "VST", "CEG", "GEV", "OKLO", "AEHR", "NOK", "CIEN",
         "ZS", "IOT", "GWRE", "DOCU", "PATH", "LULU", "TTC", "AMBA", "MSFT", "AMZN",
         "GOOGL", "META"}
# 注：FOCUS 在 fetch_data.py 仅占位（不直接过滤）；gen_dashboard.py 第 357 行
# 用 `sym in FOCUS` 过滤「财报命中」表。两边保持一致避免后续维护混乱。


def run_kline(syms, limit):
    """调用 westockdata 拉日 K 线，返回原始文本。"""
    r = subprocess.run(
        ["npx", "-y", "westock-data-clawhub@1.0.4", "kline", syms,
         "--period", "day", "--limit", str(limit)],
        capture_output=True, text=True, timeout=300)
    return r.stdout


def parse_kline(out):
    """解析 westockdata 表格文本 → {sym: {date: close}}。"""
    rows = {}
    for line in out.splitlines():
        line = line.strip()
        if not line.startswith("| us"):
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 9:
            continue
        sym, date = parts[1], parts[2]
        try:
            close = float(parts[4])
        except ValueError:
            continue
        rows.setdefault(sym, {})[date] = close
    return rows


def rsi(closes, period=14):
    if len(closes) <= period:
        return None
    gains, losses = [], []
    for i in range(1, len(closes)):
        d = closes[i] - closes[i - 1]
        gains.append(max(d, 0.0))
        losses.append(max(-d, 0.0))
    ag = sum(gains[:period]) / period
    al = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        ag = (ag * (period - 1) + gains[i]) / period
        al = (al * (period - 1) + losses[i]) / period
    if al == 0:
        return 100.0
    return round(100 - 100 / (1 + ag / al), 1)


def bias(closes, n):
    if len(closes) < n:
        return None
    ma = sum(closes[-n:]) / n
    last = closes[-1]
    if ma == 0:
        return None
    return round((last - ma) / ma * 100, 2)


def fetch_earnings(datestr):
    """拉取 Nasdaq 财报日历（keyless）。datestr 格式 YYYY-MM-DD。"""
    url = f"https://api.nasdaq.com/api/calendar/earnings?date={datestr}"
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        rows = data.get("data", {}).get("rows", []) or []
        out = []
        for r in rows:
            t = r.get("time", "")
            tlabel = "盘前" if "pre-market" in t else ("盘后" if "after-hours" in t else "未定")
            sym = r.get("symbol", "")
            out.append({
                "symbol": sym,
                "name": r.get("name", ""),
                "time": tlabel,
                "epsForecast": r.get("epsForecast", ""),
                "epsLastYear": r.get("lastYearEPS", ""),
                "marketCap": r.get("marketCap", ""),
            })
        return out
    except Exception as e:  # noqa: BLE001
        print(f"[earnings] {datestr} 拉取失败: {e}")
        return []


def fetch_yf():
    """用 yfinance 拉指数/VIX/美债/黄金/BTC。失败不中断，但每条 ticker 失败都会 print。

    关键防御：Yahoo API 偶发返回 NaN / 空 / <2 行，必须先校验，否则写出去的 nan
    会把 notify_telegram 里的 f-string 渲染成 "nan" 字符串污染推送。
    """
    import math
    out = {}
    try:
        import yfinance as yf
        tickers = {
            # 三大指数（用户偏好：纳指用 QQQ ETF 价格替代指数点，更贴近交易视角）
            "spx": "^GSPC", "ndx": "^IXIC", "dji": "^DJI", "rut": "^RUT",
            "qqq": "QQQ", "dxy": "DX-Y.NYB",
            # 宏观 / 商品 / 加密
            "vix": "^VIX", "tnx": "^TNX", "tyx": "^TYX", "fvx": "^FVX",
            "gold": "GC=F", "wti": "CL=F", "btc": "BTC-USD",
        }
        for k, t in tickers.items():
            for attempt in range(2):
                try:
                    tk = yf.Ticker(t)
                    h = tk.history(period="5d", interval="1d")
                    if h is None or h.empty or "Close" not in h or len(h["Close"]) < 2:
                        print(f"[yf] {t} 数据不足（attempt {attempt+1}）")
                        time.sleep(1)
                        continue
                    closes = [float(x) for x in h["Close"].tolist()]
                    last, prev = closes[-1], closes[-2]
                    # NaN / 零价格防御（Yahoo 限流时偶尔返回 NaN）
                    if (math.isnan(last) or math.isnan(prev) or prev == 0
                            or not math.isfinite(last) or not math.isfinite(prev)):
                        print(f"[yf] {t} 含 NaN/Inf（attempt {attempt+1}）")
                        time.sleep(1)
                        continue
                    chg = (last / prev - 1) * 100
                    out[k] = {
                        "last": round(last, 4),
                        "chg_pct": round(chg, 3),
                    }
                    break  # 成功，退出重试
                except Exception as e:  # noqa: BLE001
                    print(f"[yf] {t} 抛异常（attempt {attempt+1}）: {e}")
                    time.sleep(1)
    except Exception as e:  # noqa: BLE001
        print(f"[yf] 整体失败（可能未装 yfinance）: {e}")
    return out


def fetch_options_one(sym):
    """拉单只股票的 ATM IV + P/C ratio（volume / OI）。

    选 14-45 DTE 的到期日（避免末日效应），fallback 最近一期。
    返回 dict 含 {iv_pct, pc_vol, pc_oi, call_vol, put_vol, expiry, last} 或 None。

    兼容 usLAZR / LAZR 两种调用约定（fetch_data.py 用 us 前缀）。
    """
    clean = sym.replace("us", "") if sym.lower().startswith("us") else sym
    try:
        import yfinance as yf
        t = yf.Ticker(clean)
        exps = t.options
        if not exps:
            return None
        today = datetime.date.today()
        target = None
        for e in exps:
            d = datetime.datetime.strptime(e, "%Y-%m-%d").date()
            dte = (d - today).days
            if 14 <= dte <= 45:
                target = e
                break
        if target is None:
            target = exps[0]  # 兜底
        chain = t.option_chain(target)
        calls, puts = chain.calls, chain.puts
        if calls is None or calls.empty or puts is None or puts.empty:
            return None
        # ATM 隐含波动率：取 strike 最接近 last 的 call IV
        try:
            hist = t.history(period="5d", interval="1d")["Close"].dropna()
            last = float(hist.iloc[-1])
        except Exception:
            last = None
        if last is not None:
            # 取 ATM 附近 strike ±5% 的期权 IV 中位数（避免 deep OTM/ITM 占位值如 1e-5）
            near = calls[(calls["strike"] >= last * 0.95) & (calls["strike"] <= last * 1.05)]
            ivs = near["impliedVolatility"].dropna() if "impliedVolatility" in calls.columns else None
            iv_raw = float(ivs.median()) if ivs is not None and len(ivs) > 0 else None
        else:
            iv_raw = None
        call_vol = int(calls["volume"].fillna(0).sum()) if "volume" in calls.columns else 0
        put_vol = int(puts["volume"].fillna(0).sum()) if "volume" in puts.columns else 0
        call_oi = int(calls["openInterest"].fillna(0).sum()) if "openInterest" in calls.columns else 0
        put_oi = int(puts["openInterest"].fillna(0).sum()) if "openInterest" in puts.columns else 0
        pc_vol = round(put_vol / call_vol, 2) if call_vol > 0 else None
        pc_oi = round(put_oi / call_oi, 2) if call_oi > 0 else None
        return {
            "expiry": target,
            "last": round(last, 2) if last is not None else None,
            "iv_pct": round(iv_raw * 100, 1) if iv_raw else None,
            "pc_vol": pc_vol,
            "pc_oi": pc_oi,
            "call_vol": call_vol,
            "put_vol": put_vol,
        }
    except Exception as e:  # noqa: BLE001
        print(f"[options] {sym} 失败: {e}")
        return None


def fetch_options(syms):
    """批量拉持仓期权链。每只 25s timeout，整体 5 分钟内完成。"""
    print("拉取期权 IV / P-C ratio...")
    out = {}
    for s in syms:
        d = fetch_options_one(s)
        if d is not None:
            print(f"  {s}: IV={d.get('iv_pct')}% P/C(Vol)={d.get('pc_vol')} P/C(OI)={d.get('pc_oi')}")
        else:
            print(f"  {s}: 失败/无期权数据")
        out[s] = d
        time.sleep(0.5)  # 防 yfinance 限流
    return out


def _num(value):
    """Coerce a number to float; return None for absent/invalid values."""
    try:
        v = float(value)
        return v if v == v and abs(v) != float("inf") else None
    except (TypeError, ValueError):
        return None


def fetch_position_option_quote(position):
    """Fetch the current mark for one exact option contract from yfinance."""
    try:
        import yfinance as yf
        underlying = str(position["underlying"]).upper()
        expiry = str(position["expiration_date"])
        option_type = str(position["type"]).lower()
        strike = float(position["strike"])
        chain = yf.Ticker(underlying).option_chain(expiry)
        frame = chain.calls if option_type == "call" else chain.puts
        match = frame[(frame["strike"] - strike).abs() < 0.0001]
        if match.empty:
            return None
        row = match.iloc[0]
        bid = _num(row.get("bid"))
        ask = _num(row.get("ask"))
        last = _num(row.get("lastPrice"))
        mark = (bid + ask) / 2 if bid is not None and ask is not None and bid > 0 and ask > 0 else last
        if mark is None:
            return None
        return {"mark": round(mark, 4), "bid": bid, "ask": ask, "source": "yfinance option chain"}
    except Exception as e:  # noqa: BLE001
        print(f"[portfolio option] {position.get('underlying', '?')} 失败: {e}")
        return None


def enrich_portfolio_snapshot(snapshot, quotes):
    """Price snapshot positions at workflow runtime and calculate P&L."""
    if not snapshot.get("available"):
        return snapshot
    result = dict(snapshot)
    equities = []
    equity_value = 0.0
    equity_complete = True
    for raw in snapshot.get("equities", []):
        item = dict(raw)
        symbol = str(item.get("symbol", "")).upper()
        quantity = _num(item.get("quantity")) or 0.0
        average_cost = _num(item.get("average_cost"))
        current_price = _num((quotes.get(f"us{symbol}") or {}).get("last"))
        market_value = current_price * quantity if current_price is not None else None
        cost_basis = average_cost * quantity if average_cost is not None else None
        pnl = market_value - cost_basis if market_value is not None and cost_basis is not None else None
        pnl_pct = pnl / cost_basis * 100 if pnl is not None and cost_basis else None
        item.update({"current_price": current_price, "market_value": market_value,
                     "cost_basis": cost_basis, "unrealized_pnl": pnl,
                     "unrealized_pnl_pct": pnl_pct, "price_source": "westockdata daily close"})
        equities.append(item)
        if market_value is None:
            equity_complete = False
        else:
            equity_value += market_value

    options = []
    options_value = 0.0
    options_complete = True
    for raw in snapshot.get("options", []):
        item = dict(raw)
        quote = fetch_position_option_quote(item)
        quantity = _num(item.get("quantity")) or 0.0
        average_price = _num(item.get("average_price"))
        mark = quote.get("mark") if quote else None
        market_value = mark * quantity * 100 if mark is not None else None
        cost_basis = average_price * quantity if average_price is not None else None
        pnl = market_value - cost_basis if market_value is not None and cost_basis is not None else None
        pnl_pct = pnl / cost_basis * 100 if pnl is not None and cost_basis else None
        item.update({"current_price": mark, "market_value": market_value,
                     "cost_basis": cost_basis, "unrealized_pnl": pnl,
                     "unrealized_pnl_pct": pnl_pct,
                     "price_source": quote.get("source") if quote else None})
        options.append(item)
        if market_value is None:
            options_complete = False
        else:
            options_value += market_value

    cash = _num(snapshot.get("account", {}).get("cash")) or 0.0
    complete = equity_complete and options_complete
    result["equities"] = equities
    result["options"] = options
    result["valuation"] = {
        "as_of": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "equity_value": round(equity_value, 2),
        "options_value": round(options_value, 2),
        "total_value": round(cash + equity_value + options_value, 2) if complete else None,
        "complete": complete,
        "price_sources": ["westockdata daily close", "yfinance option chain"],
    }
    return result


def fetch_adv_dec():
    """自算 NYSE/NASDAQ 涨跌家数（60 只代表性头部股票近似）。

    数据源说明：
      - Yahoo Finance v7 / StockAnalysis API / FINRA JSON 已下线或限制，
      暂时用 30 + 30 = 60 只头部股 yfinance 自算，覆盖 90%+ 市值。
      - 不是交易所全量（NYSE 2800+ / NASDAQ 3300+ 只），
      但作为"市场宽度 proxy"够稳定。
    """
    print("拉取 NYSE/NASDAQ 涨跌家数（60 只代表性大票，yfinance + 并行）...")

    pairs = [("NYSE", AD_SYMS_NYSE), ("NASDAQ", AD_SYMS_NASDAQ)]
    out = {}
    with cf.ThreadPoolExecutor(max_workers=10) as pool:
        for label, syms in pairs:
            chgs = list(pool.map(_yf_chg, syms))
            adv = sum(1 for c in chgs if c is not None and c > 0)
            dec = sum(1 for c in chgs if c is not None and c < 0)
            unc = sum(1 for c in chgs if c is None or c == 0)
            total = adv + dec + unc
            ratio = round(adv / dec, 2) if dec > 0 else None
            out[label.lower()] = {
                "adv": adv, "dec": dec, "unc": unc, "total": total, "ad_ratio": ratio,
                "sample_size": len(syms),
            }
            print(f"  {label}: 涨 {adv} / 跌 {dec} / 平 {unc}（A/D={ratio}, 样本={len(syms)}）")
    return out


def fetch_econ_calendar(days=7):
    """用 westock-data-clawhub 拉未来 N 天美国经济数据日历。

    返回结构：
      {
        "YYYY-MM-DD": [
            {
              "date": "2026-09-04", "time": "20:30",
              "weight": 3,        # 重要性 1-3（3=高）
              "event": "8月非农就业人口变动",
              "country": "美国",
              "previous": "+125k", "forecast": "+75k", "actual": ""
            },
            ...
        ],
        ...
      }

    只保留 Weightiness >= 2（中/高重要性），避免低权重噪音。
    """
    print(f"拉取未来 {days} 天美国经济日历（westock calendar）...")
    out = {}
    for offset in range(days):
        d = (datetime.datetime.now() + datetime.timedelta(days=offset)).strftime("%Y-%m-%d")
        try:
            r = subprocess.run(
                ["npx", "-y", "westock-data-clawhub@1.0.4", "calendar", d,
                 "--country", "US", "--raw"],
                capture_output=True, text=True, timeout=30)
            events = _parse_westock_calendar(r.stdout)
            # 只留美国 + 中高重要性
            events = [e for e in events
                      if e.get("country") == "美国" and e.get("weight", 0) >= 2]
            if events:
                out[d] = events
                print(f"  {d}: {len(events)} 条美国重要事件")
        except Exception as e:  # noqa: BLE001
            print(f"  [econ_cal] {d} 失败: {e}")
    return out


def _parse_westock_calendar(stdout):
    """解析 westock calendar --raw 的 markdown 表格 → list[dict]."""
    rows = []
    lines = stdout.splitlines()
    # 找表头
    header_idx = -1
    for i, line in enumerate(lines):
        if line.startswith("| date |"):
            header_idx = i
            break
    if header_idx < 0 or header_idx + 2 >= len(lines):
        return rows
    # 跳过表头和分隔行
    for line in lines[header_idx + 2:]:
        line = line.strip()
        if not line.startswith("|"):
            break
        parts = [p.strip() for p in line.split("|")]
        # | date | oid | time | Weightiness | Content | CountryName | CountryCode | Previous | Predict | CurrentValue | ColumnCode | Area | FinancialEvent | Flag |
        if len(parts) < 14:
            continue
        try:
            rows.append({
                "date": parts[1],
                "time": parts[3],
                "weight": int(parts[4]) if parts[4].isdigit() else 1,
                "event": parts[5] or parts[13],  # 优先 Content，否则 FinancialEvent（讲话）
                "country": parts[6],
                "previous": parts[8],
                "forecast": parts[9],
                "actual": parts[10],
                "area": parts[12],
                "is_speech": not parts[5].strip(),  # Content(parts[5]) 空 = 讲话/休市；非空 = 经济数据
            })
        except (ValueError, IndexError):
            continue
    return rows


def fetch_fedwatch(yf_data, econ_calendar):
    """构造利率预期面板（定性 + 数据驱动，非 CME FedWatch 精确概率）。

    数据来源：
      - yfinance 已拉取的 ^TNX（10Y）、^TYX（30Y）、^FVX（5Y）→ 收益率曲线
      - 已发布的 CPI/非农/PPI/PMI（从 econ_calendar 取最新有 actual 的事件）
      - 下次 FOMC 日期（从 econ_calendar 找 "联邦基金" / "美联储利率决议" 或 hard-coded）

    返回：
      {
        "current_range": "3.50%-3.75%",
        "next_meeting": "2026-09-17",
        "next_meeting_time": "02:00",
        "curve_2s10s":  +35bp / -15bp / ...,
        "dxy_chg_pct": -0.5,
        "tnx_chg_pct": -1.2,
        "latest_cpi": {"yoy": "2.9%", "date": "2026-08-12"},
        "latest_nfp": {"value": "-23k", "date": "2026-09-04"},
        "stance_hint": "数据驱动定性（鸽/中/鹰）由 ai_analysis.py 给出"
      }
    """
    out = {
        "current_range": "3.50%-3.75%",
        "next_meeting": "—",
        "next_meeting_time": "—",
        "curve_2s10s": None,
        "dxy_chg_pct": None,
        "tnx_chg_pct": None,
        "latest_cpi": None,
        "latest_nfp": None,
        "stance_hint": "由 ai_analysis.py 综合判断",
    }
    # 1) 收益率曲线（5Y vs 10Y，简化版 2s10s）
    tnx = yf_data.get("tnx", {}).get("last")
    fvx = yf_data.get("fvx", {}).get("last")
    if tnx is not None and fvx is not None:
        # FVX 是 5Y，TNX 是 10Y；2s10s ≈ 10Y - 5Y（简化）
        out["curve_2s10s"] = round(tnx - fvx, 2)
    # 2) DXY 当日涨跌
    out["dxy_chg_pct"] = yf_data.get("dxy", {}).get("chg_pct")
    out["tnx_chg_pct"] = yf_data.get("tnx", {}).get("chg_pct")
    # 3) 最近已发布的 CPI / 非农（从 econ_calendar 找 actual）
    today = datetime.date.today().isoformat()
    for d_str in sorted(econ_calendar.keys(), reverse=True):
        for e in econ_calendar[d_str]:
            ev = e.get("event", "")
            actual = e.get("actual", "")
            if not actual:
                continue
            if out["latest_cpi"] is None and "CPI" in ev.upper() or "消费者物价" in ev:
                out["latest_cpi"] = {"value": actual, "date": d_str, "event": ev,
                                     "previous": e.get("previous"), "forecast": e.get("forecast")}
            if out["latest_nfp"] is None and ("非农" in ev or "Non-Farm" in ev or "NFP" in ev.upper()):
                out["latest_nfp"] = {"value": actual, "date": d_str, "event": ev,
                                     "previous": e.get("previous"), "forecast": e.get("forecast")}
    # 已知 2026-2027 FOMC 利率决议日期（hard-coded 兜底，westock 没显示时用）
    # 决议通常在北京时间次日凌晨 02:00 发布
    FOMC_DATES = [
        "2026-01-29", "2026-03-18", "2026-04-29", "2026-06-17", "2026-07-29",
        "2026-09-17", "2026-10-28", "2026-12-16",
        "2027-01-27", "2027-03-17", "2027-04-28",
    ]
    today_date = datetime.datetime.now().date()
    for d_iso in FOMC_DATES:
        try:
            d = datetime.date.fromisoformat(d_iso)
        except ValueError:
            continue
        if d >= today_date:
            out["next_meeting"] = d_iso
            out["next_meeting_time"] = "02:00 CST"
            break
    return out


def main():
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    print(f"=== fetch_data.py 运行于 {today} ===")
    private_snapshot = load_portfolio_snapshot()
    snapshot_symbols = snapshot_equity_symbols(private_snapshot)
    market_symbols = list(dict.fromkeys(
        ALL_SYMS.split(",") + [f"us{symbol}" for symbol in snapshot_symbols]
    ))
    market_symbols_csv = ",".join(market_symbols)
    state = f"已载入（{len(snapshot_symbols)} 只股票）" if private_snapshot.get("available") else "未载入"
    print(f"Robinhood 仓位快照：{state}")

    # 1) 行情 K 线（70 日，覆盖 1日/1周/1月/3月 + RSI + 乖离率）
    print("拉取 westockdata K 线...")
    kline_out = run_kline(market_symbols_csv, 70)
    rows = parse_kline(kline_out)
    if not rows:
        # 兜底：重试一次
        print("首次拉取为空，重试...")
        kline_out = run_kline(market_symbols_csv, 70)
        rows = parse_kline(kline_out)

    # 确定最新两个交易日
    all_dates = sorted({d for by in rows.values() for d in by})
    if len(all_dates) < 2:
        print("K 线数据不足，退出")
        return
    d_latest = all_dates[-1]
    d_prev = all_dates[-2]

    # 每只股票：最新价、当日涨跌、1周/1月/3月涨跌
    quotes = {}
    for sym, by in rows.items():
        arr = sorted(by.items(), reverse=True)  # 最新在前
        closes = [v for _, v in arr]
        dates = [d for d, _ in arr]
        if not closes:
            continue
        last = closes[0]
        prev = by.get(d_prev)
        chg = (last / prev - 1) * 100 if prev else None
        def period_chg(off):
            if len(closes) > off and closes[off] > 0:
                return round((last / closes[off] - 1) * 100, 2)
            return None
        quotes[sym] = {
            "last": round(last, 2),
            "chg_pct": round(chg, 2) if chg is not None else None,
            "p1w": period_chg(5),
            "p1m": period_chg(21),
            "p3m": period_chg(63),
        }

    # 情绪（RSI / 乖离率）—— 用同一批 70 日数据对 10 只 ETF 计算
    sent = {}
    sent_syms = ["usSPY", "usQQQ", "usIWM", "usDIA", "usSMH", "usXLK",
                 "usIGV", "usXLF", "usXLE", "usGLD"]
    for sym in sent_syms:
        by = rows.get(sym, {})
        arr = sorted(by.items())
        closes = [v for _, v in arr]
        if len(closes) >= 20:
            sent[sym] = {"rsi14": rsi(closes), "bias20": bias(closes, 20)}

    # 2) 财报日历（今天 + 未来 5 天）
    print("拉取 Nasdaq 财报日历...")
    earnings = {}
    for offset in range(6):
        d = (datetime.datetime.now() + datetime.timedelta(days=offset)).strftime("%Y-%m-%d")
        earnings[d] = fetch_earnings(d)

    # 3) yfinance 宏观
    print("拉取 yfinance 宏观...")
    yf_data = fetch_yf()

    # 4) 持仓期权 IV / P-C ratio（期权标的由配置文件单独声明）
    print("拉取持仓期权数据...")
    options_data = fetch_options(OPTION_UNDERLYINGS)
    private_snapshot = enrich_portfolio_snapshot(private_snapshot, quotes)

    # 5) NYSE / NASDAQ 涨跌家数（市场宽度）
    print("拉取 NYSE/NASDAQ 涨跌家数...")
    adv_dec = fetch_adv_dec()

    # 6) 多源 RSS 新闻（Yahoo/Bloomberg/WSJ/CNBC/MarketWatch/Seeking Alpha/Investing）
    print("拉取多源 RSS 新闻...")
    news_data = {}
    try:
        import subprocess
        here = os.path.dirname(os.path.abspath(__file__))
        r = subprocess.run(
            [sys.executable, os.path.join(here, "fetch_news.py")],
            capture_output=True, text=True, timeout=120)
        # 解析 stdout 提取条数
        for line in r.stdout.splitlines():
            if line.startswith("  主题分布:"):
                print(f"  [news] {line.strip()}")
            elif "已写入" in line:
                print(f"  [news] {line.strip()}")
        # 读 news.json
        news_path = os.path.join(here, "news.json")
        if os.path.exists(news_path):
            with open(news_path, encoding="utf-8") as f:
                news_data = json.load(f)
    except Exception as e:  # noqa: BLE001
        print(f"  [news] 拉取失败: {e}")

    # 7) 宏观经济日历（未来 7 天 + 已发布数据）
    econ_calendar = fetch_econ_calendar(days=7)

    # 8) 利率预期面板（收益率曲线 + 最近 CPI/非农 + 下次 FOMC）
    fedwatch = fetch_fedwatch(yf_data, econ_calendar)
    print(f"  FedWatch 面板: curve_2s10s={fedwatch.get('curve_2s10s')}bp "
          f"next_FOMC={fedwatch.get('next_meeting')} {fedwatch.get('next_meeting_time')}")

    result = {
        "generated_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "d_latest": d_latest,
        "d_prev": d_prev,
        "quotes": quotes,
        "sentiment": sent,
        "holdings": {HOLD_NAME[s]: quotes.get(s) for s in HOLDINGS},
        "portfolio": {
            "schema_version": PORTFOLIO_CONFIG.get("schema_version"),
            "holdings": PORTFOLIO_CONFIG["holdings"],
            "option_underlyings": OPTION_UNDERLYINGS,
            "note": "Public symbol-only configuration; quantities and cost basis are intentionally excluded.",
        },
        "private_portfolio_snapshot": private_snapshot,
        "earnings": earnings,
        "yf": yf_data,
        "options": options_data,
        "adv_dec": adv_dec,
        "news": news_data,
        "econ_calendar": econ_calendar,
        "fedwatch": fedwatch,
    }

    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "market_data.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"已写入 {out_path}（{len(quotes)} 只股票，最新交易日 {d_latest}）")


if __name__ == "__main__":
    main()
