import json
import time
from pathlib import Path

import feedparser
import yfinance as yf

from config import CONFIG

CACHE_DIR = Path(”./cache_v45”)
CACHE_DIR.mkdir(exist_ok=True)

# BeautifulSoup4 はオプション（インストール済みなら本文fetchを有効化）

try:
import requests
from bs4 import BeautifulSoup
_BS4_AVAILABLE = True
except ImportError:
_BS4_AVAILABLE = False

# ==============================================================================

# 📰 NewsEngine

# ==============================================================================

class NewsEngine:
“””
ニュース見出し＋本文抜粋を取得してAIプロンプト用文字列を返す。

```
キャッシュ TTL = 1時間（スキャン頻度に合わせて更新）
"""

@staticmethod
def get(ticker: str) -> dict:
    """
    Returns:
        {
            "articles": [{"title": str, "url": str, "body": str}, ...],
            "fetched_at": str
        }
    """
    cache_file = CACHE_DIR / f"news_{ticker}.json"

    if cache_file.exists():
        if time.time() - cache_file.stat().st_mtime < CONFIG["NEWS_CACHE_EXPIRY"]:
            try:
                with open(cache_file) as f:
                    return json.load(f)
            except:
                pass

    articles: list[dict] = []
    seen: set[str] = set()

    # ① Yahoo Finance ニュース
    try:
        for n in (yf.Ticker(ticker).news or [])[:5]:
            title = n.get("title", n.get("headline", ""))
            url   = n.get("link",  n.get("url", ""))
            if title and title not in seen:
                seen.add(title)
                articles.append({"title": title, "url": url, "body": ""})
    except:
        pass

    # ② Google News RSS（直近3日）
    try:
        feed = feedparser.parse(
            f"https://news.google.com/rss/search"
            f"?q={ticker}+stock+when:3d&hl=en-US&gl=US&ceid=US:en"
        )
        for entry in feed.entries[:5]:
            if entry.title not in seen:
                seen.add(entry.title)
                articles.append({
                    "title": entry.title,
                    "url":   getattr(entry, "link", ""),
                    "body":  "",
                })
    except:
        pass

    # ③ 本文fetch（上位3記事）
    if _BS4_AVAILABLE:
        import requests as _req
        for art in articles[:3]:
            if not art["url"]:
                continue
            try:
                r = _req.get(
                    art["url"],
                    headers={"User-Agent": "Mozilla/5.0"},
                    timeout=CONFIG["NEWS_FETCH_TIMEOUT"],
                )
                soup  = BeautifulSoup(r.text, "html.parser")
                paras = [
                    p.get_text().strip()
                    for p in soup.find_all("p")
                    if len(p.get_text().strip()) > 50
                ]
                art["body"] = " ".join(paras)[:CONFIG["NEWS_MAX_CHARS"]]
            except:
                pass

    result = {
        "articles":   articles[:8],
        "fetched_at": time.strftime("%Y-%m-%d %H:%M"),
    }

    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False)

    return result

@staticmethod
def format_for_prompt(news: dict) -> str:
    """
    AIプロンプトに渡す文字列を生成。
    本文抜粋がある記事は見出し＋抜粋を、ない記事は見出しのみ出力。
    """
    lines: list[str] = []
    for a in news.get("articles", []):
        lines.append(f"• {a['title']}")
        if a.get("body"):
            lines.append(f"  抜粋: {a['body'][:200]}")
    return "\n".join(lines) if lines else "本日、新規材料は未検出。"
```