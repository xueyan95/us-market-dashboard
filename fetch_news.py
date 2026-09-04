#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fetch_news.py — RSS 多源抓取（feedparser）+ yfinance 兜底，写 news.json。

输出 news.json：
  {
    "generated_at": ISO 时间,
    "count": 条数,
    "items": [{title, link, summary, published, source}, ...]  // 按发布时间倒序
  }

下游 ai_analysis.py 读 items 做主题聚类（5 大主题）。
"""
import datetime
import json
import os
import time

import feedparser


# 精选 8 个 RSS 源：5 英文权威 + 1 综合 + 1 中文 + 1 个股研报
RSS_SOURCES = [
    # (source, url, max_items)
    ("Reuters",      "https://feeds.reuters.com/reuters/businessNews", 4),
    ("Bloomberg",    "https://feeds.bloomberg.com/markets/news.rss", 4),
    ("WSJ Markets",  "https://feeds.a.dj.com/rss/RSSMarketsMain.xml", 4),
    ("CNBC",         "https://www.cnbc.com/id/100003114/device/rss/rss.html", 4),
    ("MarketWatch",  "https://www.marketwatch.com/rss/topstories", 4),
    ("Seeking Alpha","https://seekingalpha.com/feed.xml", 3),
    ("华尔街见闻",    "https://wallstreetcn.com/feed", 3),
]


def fetch_rss(source, url, limit=5, timeout=15):
    """单源 RSS 抓取。失败返回 []."""
    try:
        f = feedparser.parse(url, agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)")
        if f.bozo and not f.entries:
            print(f"  [{source}] 解析异常: {f.bozo_exception}", flush=True)
            return []
        items = []
        for e in f.entries[:limit]:
            pub = e.get("published_parsed") or e.get("updated_parsed")
            title = (e.get("title") or "").strip()
            if not title:
                continue
            # 摘要：summary > description > subtitle，截 400 字
            summary = (e.get("summary") or e.get("description") or e.get("subtitle") or "")[:400]
            # 清理 HTML
            if "<" in summary and ">" in summary:
                import re
                summary = re.sub(r"<[^>]+>", "", summary).strip()
            items.append({
                "title": title,
                "link": e.get("link", ""),
                "summary": summary,
                "published": datetime.datetime(*pub[:6]).isoformat() if pub else "",
                "source": source,
            })
        return items
    except Exception as e:  # noqa: BLE001
        print(f"  [{source}] 异常: {e}", flush=True)
        return []


def fetch_yfinance_fallback(syms=None, per=1):
    """yfinance 兜底：每个 ticker 取 per 条。syms 默认主流指数 + 大盘股 + QQQ。"""
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
                    items.append({
                        "title": title,
                        "link": n.get("link", ""),
                        "summary": (n.get("summary") or "")[:300],
                        "published": datetime.datetime.fromtimestamp(
                            n.get("providerPublishTime", time.time())
                        ).isoformat(),
                        "source": f"yfinance:{s}",
                    })
        except Exception:
            continue
    return items


def main():
    print("=== fetch_news.py ===")
    items = []
    for source, url, limit in RSS_SOURCES:
        got = fetch_rss(source, url, limit=limit)
        print(f"  {source}: {len(got)} 条")
        items.extend(got)

    # RSS 拿不到数据时用 yfinance 兜底（确保不空跑）
    if not items:
        print("  RSS 全失败，启动 yfinance 兜底...")
        items = fetch_yfinance_fallback()
        print(f"  yfinance 兜底: {len(items)} 条")

    # 按发布时间倒序（无时间的排最后）
    def keyfn(it):
        return it.get("published") or ""
    items.sort(key=keyfn, reverse=True)

    here = os.path.dirname(os.path.abspath(__file__))
    out_path = os.path.join(here, "news.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({
            "generated_at": datetime.datetime.now().isoformat(),
            "count": len(items),
            "items": items,
        }, f, ensure_ascii=False, indent=2)
    print(f"已写入 {out_path}（{len(items)} 条）")


if __name__ == "__main__":
    main()