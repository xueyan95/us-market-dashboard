#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fetch_news.py — RSS 多源抓取（feedparser）+ yfinance 兜底，写 news.json。

输出 news.json：
  {
    "generated_at": ISO 时间,
    "count": 条数,
    "items": [{title, link, summary, published, source, lang}, ...],  // 按发布时间倒序
    "sources": {source_name: count, ...}  // 各源分布
  }

下游：
  - ai_analysis.py 读 items 做"主题聚类"（5 大主题 + AI 摘要）
  - gen_dashboard.py 渲染 ⑥ 重要信息（卡片化 + 主题标签）
  - notify_telegram.py 摘要里加一条"今日焦点"
"""
import datetime
import json
import os
import re
import time
import urllib.request
import concurrent.futures as cf
from urllib.parse import urlparse

import feedparser


# === RSS 源（实测可用）===
RSS_SOURCES = [
    # (source, url, max_items, lang)
    ("Yahoo Top",     "https://news.yahoo.com/rss/topstories",     8,  "en"),
    ("Yahoo Finance", "https://finance.yahoo.com/news/rssindex",    8,  "en"),
    ("Bloomberg",     "https://feeds.bloomberg.com/markets/news.rss", 6, "en"),
    ("WSJ Markets",   "https://feeds.a.dj.com/rss/RSSMarketsMain.xml", 6, "en"),
    ("CNBC",          "https://www.cnbc.com/id/100003114/device/rss/rss.html", 6, "en"),
    ("MarketWatch",   "https://www.marketwatch.com/rss/topstories", 5, "en"),
    ("Seeking Alpha", "https://seekingalpha.com/feed.xml",         5,  "en"),
    ("Investing",     "https://www.investing.com/rss/news.rss",    4,  "en"),
    ("Investing CN",  "https://www.investing.com/rss/news_25.rss", 4,  "en"),
]

# 关键词 → 主题（用于本地简单主题分类，SiliconFlow 二次精修）
THEME_KEYWORDS = {
    "macro": [
        r"\bFed\b", r"\bFOMC\b", r"\bCPI\b", r"\bPPI\b", r"\bNFP\b",
        r"\brate\b", r"\binflation\b", r"\byield", r"\bDollar\b",
        r"\bUS Treasury\b", r"\bECB\b", r"\bBOJ\b", r"\bPowell\b",
        r"美联储", r"通胀", r"利率", r"加息", r"降息", r"鲍威尔",
    ],
    "ai_tech": [
        r"\bAI\b", r"\bNvidia\b", r"\bNVDA\b", r"\bOpenAI\b", r"\bAnthropic\b",
        r"\bGemini\b", r"\bChatGPT\b", r"\bLLM\b", r"\bDeepSeek\b",
        r"\bsemiconductor\b", r"\bTSMC\b", r"\bchip\b", r"\bGPU\b",
        r"芯片", r"光模块", r"算力", r"大模型",
    ],
    "geopolitics": [
        r"\bRussia\b", r"\bUkraine\b", r"\bChina\b", r"\bTaiwan\b",
        r"\bIran\b", r"\bIsrael\b", r"\bsanction", r"\btariff",
        r"俄乌", r"中东", r"台湾", r"制裁", r"关税",
    ],
    "company": [
        r"\bApple\b", r"\bAAPL\b", r"\bMicrosoft\b", r"\bTesla\b",
        r"\bAmazon\b", r"\bMeta\b", r"\bAlphabet\b", r"\bGoogle\b",
        r"\bBoeing\b", r"\bGoldman\b", r"\bJPMorgan\b",
    ],
    "energy_commodity": [
        r"\bcrude\b", r"\bBrent\b", r"\bWTI\b", r"\bOPEC\b",
        r"\bgold\b", r"\bsilver\b", r"\bcopper\b", r"\biron ore\b",
        r"\buranium\b", r"\bnatural gas\b",
        r"原油", r"黄金", r"铜",
    ],
}


def classify_theme(title: str, summary: str = "") -> list:
    """本地粗分类：返回命中主题列表（按命中数倒序）。"""
    text = (title + " " + summary).lower()
    hits = {}
    for theme, patterns in THEME_KEYWORDS.items():
        score = sum(1 for p in patterns if re.search(p, text, re.IGNORECASE))
        if score > 0:
            hits[theme] = score
    if not hits:
        return ["other"]
    return sorted(hits.keys(), key=lambda k: -hits[k])


def fetch_rss(source, url, limit=5, timeout=15):
    """单源 RSS 抓取。失败返回 []."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=timeout) as response:
            payload = response.read()
        f = feedparser.parse(payload)
        if f.bozo and not f.entries:
            print(f"  [{source}] 解析异常: {f.bozo_exception}", flush=True)
            return []
        items = []
        for e in f.entries[:limit]:
            pub = e.get("published_parsed") or e.get("updated_parsed")
            title = (e.get("title") or "").strip()
            if not title:
                continue
            summary = (e.get("summary") or e.get("description") or e.get("subtitle") or "")[:500]
            # 清理 HTML
            if "<" in summary and ">" in summary:
                summary = re.sub(r"<[^>]+>", "", summary).strip()
            items.append({
                "title": title,
                "link": e.get("link", ""),
                "summary": summary[:400],
                "published": datetime.datetime(*pub[:6]).isoformat() if pub else "",
                "published_ts": time.mktime(pub) if pub else 0,
                "source": source,
            })
        return items
    except Exception as e:  # noqa: BLE001
        print(f"  [{source}] 异常: {e}", flush=True)
        return []


def fetch_yfinance_fallback(syms=None, per=1):
    """yfinance 兜底：每个 ticker 取 per 条。"""
    if syms is None:
        syms = ["^GSPC", "^IXIC", "NVDA", "AAPL", "MSFT", "TSLA",
                "GOOGL", "AMZN", "META", "QQQ", "TSM", "INTC"]
    try:
        import yfinance as yf
    except Exception as e:  # noqa: BLE001
        print(f"  [yfinance] 无法导入: {e}", flush=True)
        return []
    items, seen = [], set()
    for s in syms:
        try:
            t = yf.Ticker(s)
            for n in (t.news or [])[:per]:
                title = (n.get("title") or "").strip()
                if title and title not in seen:
                    seen.add(title)
                    ts = n.get("providerPublishTime", time.time())
                    items.append({
                        "title": title,
                        "link": n.get("link", ""),
                        "summary": (n.get("summary") or "")[:300],
                        "published": datetime.datetime.fromtimestamp(ts).isoformat(),
                        "published_ts": ts,
                        "source": f"yfinance:{s}",
                    })
        except Exception:
            continue
    return items


def dedupe(items):
    """按 link URL / 标题前 60 字去重。"""
    seen_link, seen_title, out = set(), set(), []
    for it in items:
        link = it.get("link") or ""
        try:
            norm_link = urlparse(link).netloc + urlparse(link).path
        except Exception:
            norm_link = link
        title_key = (it.get("title") or "")[:60].lower()
        if norm_link and norm_link in seen_link:
            continue
        if title_key in seen_title:
            continue
        seen_link.add(norm_link)
        seen_title.add(title_key)
        out.append(it)
    return out


def filter_recent(items, max_age_hours=36):
    """过滤掉超过 max_age_hours 的旧闻（published_ts=0 保留）。"""
    now = time.time()
    out = []
    for it in items:
        ts = it.get("published_ts", 0)
        if ts == 0 or (now - ts) <= max_age_hours * 3600:
            out.append(it)
    return out


def main():
    print("=== fetch_news.py ===")
    items = []
    source_dist = {}

    with cf.ThreadPoolExecutor(max_workers=6) as pool:
        futures = [(source, lang, pool.submit(fetch_rss, source, url, limit))
                   for source, url, limit, lang in RSS_SOURCES]
    for source, lang, future in futures:
        got = future.result()
        for g in got:
            g["lang"] = lang
        print(f"  {source}: {len(got)} 条")
        source_dist[source] = len(got)
        items.extend(got)

    # RSS 拿不到数据时用 yfinance 兜底（确保不空跑）
    if not items:
        print("  RSS 全失败，启动 yfinance 兜底...")
        items = fetch_yfinance_fallback()
        for it in items:
            it["lang"] = "en"
        print(f"  yfinance 兜底: {len(items)} 条")

    # 去重 + 时间过滤
    before = len(items)
    items = dedupe(items)
    print(f"  去重: {before} -> {len(items)}")
    before = len(items)
    items = filter_recent(items, max_age_hours=48)
    print(f"  48h 过滤: {before} -> {len(items)}")

    # 本地粗分类主题
    for it in items:
        it["themes"] = classify_theme(it.get("title", ""), it.get("summary", ""))

    # 按发布时间倒序
    items.sort(key=lambda it: it.get("published_ts", 0), reverse=True)

    # 写文件
    here = os.path.dirname(os.path.abspath(__file__))
    out_path = os.path.join(here, "news.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({
            "generated_at": datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(),
            "count": len(items),
            "sources": source_dist,
            "items": items,
        }, f, ensure_ascii=False, indent=2)
    print(f"已写入 {out_path}（{len(items)} 条）")

    # 主题分布
    theme_dist = {}
    for it in items:
        for t in it.get("themes", []):
            theme_dist[t] = theme_dist.get(t, 0) + 1
    print(f"  主题分布: {theme_dist}")


if __name__ == "__main__":
    main()
