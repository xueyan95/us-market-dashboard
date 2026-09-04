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
import urllib.request

# ---------------- 配置 ----------------
ALL_SYMS = (
    "usSPY,usQQQ,usIWM,usDIA,usSMH,usXLK,usIGV,usXLF,usXLE,usGLD,"
    "usNVDA,usAMD,usTSM,usAVGO,usMU,usARM,usASML,usAMAT,usMRVL,usCRDO,"
    "usINTC,usWOLF,usCOHR,usMSFT,usAMZN,usGOOGL,usMETA,usORCL,usCRWV,usNBIS,"
    "usANET,usVRT,usEQIX,usLAZR,usFOTO,usEUV,usNOW,usSNOW,usNET,usAPP,"
    "usCRM,usPLTR,usADBE,usCRWD,usAAPL,usTSLA,usVST,usCEG,usGEV,usBE,usOKLO,usNOK,usAEHR"
)
HOLDINGS = ["usLAZR", "usINTC", "usAPP", "usBE", "usCOHR", "usWOLF", "usNBIS", "usNOW"]
HOLD_NAME = {"usLAZR": "LAZR", "usINTC": "INTC", "usAPP": "APP", "usBE": "BE",
             "usCOHR": "COHR", "usWOLF": "WOLF", "usNBIS": "NBIS", "usNOW": "NOW"}

# 关注池（财报过滤用）
FOCUS = {"NVDA", "AMD", "TSM", "AVGO", "MU", "ARM", "ASML", "AMAT", "MRVL", "CRDO",
         "INTC", "WOLF", "COHR", "LAZR", "FOTO", "EUV", "APP", "NOW", "BE", "NBIS",
         "ORCL", "ANET", "VRT", "EQIX", "AAPL", "TSLA", "SNOW", "NET", "CRM", "PLTR",
         "ADBE", "CRWD", "VST", "CEG", "GEV", "OKLO", "AEHR", "NOK", "CIEN", "ZS",
         "IOT", "GWRE", "DOCU", "PATH", "LULU", "TTC", "AMBA", "MSFT", "AMZN", "GOOGL", "META"}


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
    """用 yfinance 拉指数/VIX/美债/黄金/BTC。失败不中断。"""
    out = {}
    try:
        import yfinance as yf
        tickers = {
            "spx": "^GSPC", "ndx": "^IXIC", "dji": "^DJI", "rut": "^RUT",
            "vix": "^VIX", "tnx": "^TNX", "tyx": "^TYX", "fvx": "^FVX",
            "gold": "GC=F", "wti": "CL=F", "btc": "BTC-USD",
        }
        for k, t in tickers.items():
            try:
                tk = yf.Ticker(t)
                h = tk.history(period="5d", interval="1d")
                if h.empty or "Close" not in h:
                    continue
                closes = [float(x) for x in h["Close"].tolist()]
                last = closes[-1]
                prev = closes[-2] if len(closes) > 1 else last
                out[k] = {
                    "last": round(last, 4),
                    "chg_pct": round((last / prev - 1) * 100, 3) if prev else None,
                }
            except Exception as e:  # noqa: BLE001
                print(f"[yf] {t} 失败: {e}")
    except Exception as e:  # noqa: BLE001
        print(f"[yf] 整体失败（可能未装 yfinance）: {e}")
    return out


def main():
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    print(f"=== fetch_data.py 运行于 {today} ===")

    # 1) 行情 K 线（70 日，覆盖 1日/1周/1月/3月 + RSI + 乖离率）
    print("拉取 westockdata K 线...")
    kline_out = run_kline(ALL_SYMS, 70)
    rows = parse_kline(kline_out)
    if not rows:
        # 兜底：重试一次
        print("首次拉取为空，重试...")
        kline_out = run_kline(ALL_SYMS, 70)
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

    result = {
        "generated_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "d_latest": d_latest,
        "d_prev": d_prev,
        "quotes": quotes,
        "sentiment": sent,
        "holdings": {HOLD_NAME[s]: quotes.get(s) for s in HOLDINGS},
        "earnings": earnings,
        "yf": yf_data,
    }

    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "market_data.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"已写入 {out_path}（{len(quotes)} 只股票，最新交易日 {d_latest}）")


if __name__ == "__main__":
    main()
