import json
import time
from pathlib import Path

import feedparser
import yfinance as yf

from config import CONFIG

CACHE_DIR = Path("./cache_v45")
CACHE_DIR.mkdir(exist_ok=True)

# BeautifulSoup4 が使えるかチェック（オプション機能）
_BS4_AVAILABLE = False
try:
    import requests
    from bs4 import BeautifulSoup
    _BS4_AVAILABLE = True
except ImportError:
    pass

# ==============================================================================
# 📰 NewsEngine
# ==============================================================================

class NewsEngine:
    """
    ニュース見出し＋本文抜粋を取得してAIプロンプト用文字列を返す。

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

        # キャッシュ読み込み
        if cache_file.exists():
            expiry = CONFIG.get("NEWS_CACHE_EXPIRY", 3600)  # デフォルト1時間
            if time.time() - cache_file.stat().st_mtime < expiry:
                try:
                    with open(cache_file, encoding="utf-8") as f:
                        return json.load(f)
                except Exception:
                    pass

        articles: list[dict] = []
        seen: set[str] = set()

        # ① Yahoo Finance ニュース（最大5件）
        try:
            ticker_obj = yf.Ticker(ticker)
            news_items = ticker_obj.news or []
            for n in news_items[:5]:
                title = n.get("title") or n.get("headline", "")
                url = n.get("link") or n.get("url", "")
                if title and title not in seen:
                    seen.add(title)
                    articles.append({"title": title, "url": url, "body": ""})
        except Exception:
            pass

        # ② Google News RSS（直近3日、最大5件）
        try:
            query = f"{ticker}+stock+when:3d"
            rss_url = (
                f"https://news.google.com/rss/search"
                f"?q={query}&hl=en-US&gl=US&ceid=US:en"
            )
            feed = feedparser.parse(rss_url)
            for entry in feed.entries[:5]:
                title = entry.title
                if title not in seen:
                    seen.add(title)
                    articles.append({
                        "title": title,
                        "url": getattr(entry, "link", ""),
                        "body": "",
                    })
        except Exception:
            pass

        # ③ 本文抜粋取得（上位3件まで、BS4が使える場合）
        if _BS4_AVAILABLE:
            timeout = CONFIG.get("NEWS_FETCH_TIMEOUT", 8)      # 秒
            max_chars = CONFIG.get("NEWS_MAX_CHARS", 800)

            for art in articles[:3]:
                url = art.get("url")
                if not url:
                    continue
                try:
                    r = requests.get(
                        url,
                        headers={"User-Agent": "Mozilla/5.0 (compatible; NewsBot/1.0)"},
                        timeout=timeout,
                    )
                    r.raise_for_status()
                    soup = BeautifulSoup(r.text, "html.parser")

                    # 長い段落のみ抽出
                    paras = [
                        p.get_text().strip()
                        for p in soup.find_all("p")
                        if len(p.get_text().strip()) > 50
                    ]
                    body_text = " ".join(paras)[:max_chars]
                    art["body"] = body_text
                except Exception:
                    art["body"] = ""  # 失敗しても空文字で継続

        result = {
            "articles": articles[:8],  # 最大8件に制限
            "fetched_at": time.strftime("%Y-%m-%d %H:%M"),
        }

        # キャッシュ保存
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2, default=str)

        return result

    @staticmethod
    def format_for_prompt(news: dict) -> str:
        """
        AIプロンプトに渡す文字列を生成。
        本文抜粋がある記事は見出し＋抜粋を、ない記事は見出しのみ出力。
        """
        lines: list[str] = []
        articles = news.get("articles", [])

        if not articles:
            return "本日、新規材料は未検出。"

        for a in articles:
            lines.append(f"• {a['title']}")
            body = a.get("body", "").strip()
            if body:
                # 最初の200文字程度に短縮（プロンプト長節約）
                excerpt = body[:200] + ("..." if len(body) > 200 else "")
                lines.append(f"  抜粋: {excerpt}")

        return "\n".join(lines)

    # ========== 新しく追加 ==========
    @staticmethod
    def get_general_market() -> dict:
        """
        市場全体のニュースを取得する（SPYのニュースを代表として使用）
        """
        return NewsEngine.get("SPY")