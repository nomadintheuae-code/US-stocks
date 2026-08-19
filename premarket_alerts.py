#!/usr/bin/env python3
"""
تنبيهات ما قبل الافتتاح (Premarket) — أسهم بين $2 و $50
=====================================================
المصدر  : https://stockanalysis.com/markets/premarket/
الهدف    : معرفة أسباب الحركة (أخبار/محفزات) وتصنيفها إلى:
           - 🔥 محفز حقيقي (خبر أساسي يستحق المتابعة)
           - ⚠️ خبر + مؤشرات مضاربة (حذر)
           - 🎰 مضاربة غالبًا (بدون محفز أساسي واضح)
           - ❓ غير واضح (توصيلات/ضجيج بلا خبر واضح)

الاستخدام:
    cd Projects/US-stocks
    ./venv/bin/python premarket_alerts.py
    ./venv/bin/python premarket_alerts.py --side gainers --min-change 10 --line

خيارات مفيدة:
    --min-price 2 --max-price 50 --min-change 5 --side both
    --refresh (تجاهل كاش الصفحة) --no-news (بدون جلب أخبار) --limit 25
    --json مسار_ملف (حفظ النتائج JSON) --line (إرسال ملخص LINE)
"""
from __future__ import annotations

import argparse
import calendar
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import feedparser
import requests
from bs4 import BeautifulSoup

try:
    import yfinance as yf
    HAS_YF = True
except Exception:  # pragma: no cover
    HAS_YF = False

BASE_DIR = Path(__file__).resolve().parent
CACHE_DIR = BASE_DIR / "cache_premarket"
RESULTS_DIR = BASE_DIR / "results"
CACHE_DIR.mkdir(exist_ok=True)
RESULTS_DIR.mkdir(exist_ok=True)

PAGE_URL = "https://stockanalysis.com/markets/premarket/"
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

PAGE_CACHE_TTL = 5 * 60        # الصفحة تتغير خلال الجلسة → كاش قصير
NEWS_CACHE_TTL = 30 * 60       # الأخبار أبطأ تغيرًا

RIYADH = ZoneInfo("Asia/Riyadh")
NEW_YORK = ZoneInfo("America/New_York")

# ── محفزات أساسية حقيقية (كلمات مفتاحية في العناوين) ──────────────────────
CATALYST_PATTERNS: list[tuple[str, str]] = [
    (r"\bearnings?\b", "إعلان أرباح/نتائج"),
    (r"\b(report|reports)\b", "إعلان نتائج"),
    (r"\bbeat[s]?\b", "تجاوز التوقعات"),
    (r"\bguidance\b", "توجيهات مستقبلية"),
    (r"\b(fiscal|quarter|q[1-4]|fy\d{2})\b", "نتائج ربعية/سنوية"),
    (r"\bfda\b", "موافقة FDA"),
    (r"\b(approval|approved|clearance)\b", "موافقة تنظيمية"),
    (r"\b(clinical trial|phase [123])\b", "تجربة سريرية"),
    (r"\b(contract|awarded?|grant)\b", "عقد/منحة"),
    (r"\b(partnership|partners?|collaboration|alliance)\b", "شراكة/تعاون"),
    (r"\b(merger|acquisition|acquires?|buyout|takeover)\b", "اندماج/استحواذ"),
    (r"\b(agreement|deal|tender offer)\b", "اتفاقية/صفقة"),
    (r"\b(upgraded?|initiated|price target|outperform|overweight|buy rating)\b", "توصية محللين"),
    (r"\b(dividend|buyback|repurchase)\b", "توزيعات/إعادة شراء"),
    (r"\b(ipo|spin[- ]?off|listing)\b", "اكتتاب/توزيع أسهم"),
    (r"\b(product launch|launches?|launched|licens(e|ing))\b", "إطلاق منتج/ترخيص"),
    (r"\b(revenue|sales|growth)\b", "نمو إيرادات/مبيعات"),
    (r"\b(debt|refinanc(e|ing)|restructuring)\b", "هيكلة ديون"),
    (r"\b(lawsuit|settlement|patent)\b", "تطور قانوني/براءة اختراع"),
    (r"\bprofit warning\b|\bwarning\b", "تحذير أرباح"),
]

# ── مؤشرات مضاربة (كلمات مفتاحية في العناوين) ─────────────────────────────
SPEC_PATTERNS: list[tuple[str, str]] = [
    (r"\bshort squeeze\b|\bsqueeze\b", "ضغط قصير (Short Squeeze)"),
    (r"\bgamma\b|\boptions\b", "تحركات خيارات/جاما"),
    (r"\bmeme\b|\breddit\b|\bwallstreetbets\b|\bwsb\b", "ضجة ريديت/ميمي"),
    (r"\b(public offering|offering|dilution|secondary offering|private placement)\b", "إصدار أسهم/تخفيف"),
    (r"\breverse[- ]?split\b|\bsplit\b", "دمج/تقسيم أسهم"),
    (r"\bpump\b|\bhype\b|\btiktok\b|\bsocial media\b", "ترويج مضاربي"),
    (r"\b(halted?|volatil\w*)\b", "تذبذب حاد/إيقاف"),
    (r"\b(bankruptcy|chapter 11|delist\w*|going concern)\b", "مخاطر إفلاس/شطب"),
]

# ══════════════════════════════════════════════════════════════════════════
# نماذج البيانات
# ══════════════════════════════════════════════════════════════════════════

@dataclass
class Mover:
    rank: int
    symbol: str
    name: str
    change_pct: float
    price: float
    volume: int
    market_cap_raw: str
    market_cap_usd: float = 0.0
    prev_close: float = 0.0
    dollar_volume: float = 0.0

    def __post_init__(self) -> None:
        self.prev_close = self.price / (1 + self.change_pct / 100.0) if self.price else 0.0
        self.dollar_volume = self.price * self.volume
        self.market_cap_usd = parse_market_cap(self.market_cap_raw)


@dataclass
class NewsItem:
    title: str
    url: str
    source: str
    published: float = 0.0  # epoch


@dataclass
class Verdict:
    kind: str                      # catalyst / mixed / speculative / unclear
    label: str                     # نص عربي قصير
    reasons: list[str] = field(default_factory=list)
    detail: str = ""


# ══════════════════════════════════════════════════════════════════════════
# جلب الصفحة وتحليلها
# ══════════════════════════════════════════════════════════════════════════

def fetch_page(refresh: bool = False) -> str:
    cache_file = CACHE_DIR / "page.html"
    if not refresh and cache_file.exists() and time.time() - cache_file.stat().st_mtime < PAGE_CACHE_TTL:
        return cache_file.read_text(encoding="utf-8")
    r = requests.get(PAGE_URL, headers={"User-Agent": UA}, timeout=20)
    r.raise_for_status()
    cache_file.write_text(r.text, encoding="utf-8")
    return r.text


def parse_market_cap(raw: str) -> float:
    """يحول '63.13M' أو '1.2B' إلى قيمة بالدولار."""
    s = (raw or "").strip().replace(",", "").upper()
    if not s or s in ("—", "-", "N/A"):
        return 0.0
    mult = 1.0
    if s.endswith("B"):
        mult, s = 1e9, s[:-1]
    elif s.endswith("M"):
        mult, s = 1e6, s[:-1]
    elif s.endswith("K"):
        mult, s = 1e3, s[:-1]
    try:
        return float(s) * mult
    except ValueError:
        return 0.0


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def parse_movers(html: str) -> tuple[list[Mover], list[Mover]]:
    soup = BeautifulSoup(html, "lxml")
    tables = soup.find_all("table")
    out: list[list[Mover]] = []
    for table in tables[:2]:
        movers: list[Mover] = []
        for tr in table.find_all("tr"):
            cells = [_clean(c.get_text(" ", strip=True)) for c in tr.find_all("td")]
            if len(cells) < 7:
                continue
            try:
                sym_link = tr.find("td", class_="sym")
                symbol = _clean(sym_link.get_text(" ", strip=True)) if sym_link else cells[1]
                movers.append(Mover(
                    rank=int(cells[0]) if cells[0].isdigit() else len(movers) + 1,
                    symbol=symbol,
                    name=cells[2],
                    change_pct=float(cells[3].rstrip("%")),
                    price=float(cells[4].replace(",", "")),
                    volume=int(cells[5].replace(",", "")) if cells[5].replace(",", "").isdigit() else 0,
                    market_cap_raw=cells[6],
                ))
            except (ValueError, IndexError):
                continue
        out.append(movers)
    gainers = out[0] if out else []
    losers = out[1] if len(out) > 1 else []
    return gainers, losers


# ══════════════════════════════════════════════════════════════════════════
# جلب الأخبار (Yahoo Finance + Google News RSS) مع كاش
# ══════════════════════════════════════════════════════════════════════════

def _load_news_cache(symbol: str) -> list[NewsItem] | None:
    f = CACHE_DIR / f"news_{symbol}.json"
    if f.exists() and time.time() - f.stat().st_mtime < NEWS_CACHE_TTL:
        try:
            return [NewsItem(**x) for x in json.loads(f.read_text(encoding="utf-8"))]
        except Exception:
            pass
    return None


def _save_news_cache(symbol: str, items: list[NewsItem]) -> None:
    f = CACHE_DIR / f"news_{symbol}.json"
    f.write_text(json.dumps([x.__dict__ for x in items], ensure_ascii=False), encoding="utf-8")


def _yf_news(symbol: str) -> list[NewsItem]:
    if not HAS_YF:
        return []
    items: list[NewsItem] = []
    try:
        news = yf.Ticker(symbol).news or []
        for n in news[:6]:
            title = (n.get("title") or "").strip()
            if not title:
                continue
            items.append(NewsItem(
                title=title,
                url=n.get("link") or n.get("url") or "",
                source="Yahoo",
                published=float(n.get("providerPublishTime") or 0),
            ))
    except Exception:
        pass
    return items


def _google_news(symbol: str) -> list[NewsItem]:
    items: list[NewsItem] = []
    try:
        url = ("https://news.google.com/rss/search"
               f"?q={requests.utils.quote(symbol + ' stock')}&hl=en-US&gl=US&ceid=US:en")
        feed = feedparser.parse(url)
        for e in feed.entries[:6]:
            title = _clean(getattr(e, "title", ""))
            if not title:
                continue
            pub = 0.0
            if getattr(e, "published_parsed", None):
                pub = float(calendar.timegm(e.published_parsed))
            items.append(NewsItem(title=title, url=getattr(e, "link", ""), source="Google News", published=pub))
    except Exception:
        pass
    return items


def fetch_news(symbol: str) -> list[NewsItem]:
    cached = _load_news_cache(symbol)
    if cached is not None:
        return cached
    items: list[NewsItem] = []
    seen: set[str] = set()
    for item in _yf_news(symbol) + _google_news(symbol):
        key = re.sub(r"[^a-z0-9 ]", "", item.title.lower())
        if not key or key in seen:
            continue
        seen.add(key)
        items.append(item)
    items = items[:8]
    _save_news_cache(symbol, items)
    return items


# ══════════════════════════════════════════════════════════════════════════
# التصنيف: محفز حقيقي أم مضاربة؟
# ══════════════════════════════════════════════════════════════════════════

def _match(patterns: list[tuple[str, str]], text: str) -> list[str]:
    found = []
    for pat, label in patterns:
        if re.search(pat, text):
            found.append(label)
    return found


def classify(mover: Mover, news: list[NewsItem]) -> Verdict:
    text = " ".join(n.title for n in news).lower()

    cat = _match(CATALYST_PATTERNS, text)
    spec = _match(SPEC_PATTERNS, text)

    structural: list[str] = []
    if mover.price < 3:
        structural.append("السعر أقل من 3$")
    if mover.market_cap_usd and mover.market_cap_usd < 200_000_000:
        structural.append("قيمة سوقية أقل من 200 مليون $")
    if abs(mover.change_pct) > 100:
        structural.append("حركة تتجاوز 100%")
    if mover.dollar_volume < 10_000_000:
        structural.append("سيولة قبل الافتتاح ضعيفة نسبيًا")
    if not mover.dollar_volume:
        structural.append("بدون حجم قبل الافتتاح")

    cap = mover.market_cap_usd or 0
    risky_mix = mover.price < 3 and cap < 200_000_000

    if cat and not spec:
        kind, label = "catalyst", "🔥 محفز حقيقي"
    elif cat and spec:
        if spec and risky_mix:
            kind, label = "mixed", "⚠️ خبر لكن مضاربة عالية"
        else:
            kind, label = "mixed", "⚠️ خبر + مؤشرات مضاربة"
    elif spec:
        kind, label = "speculative", "🎰 مضاربة غالبًا"
    elif len(structural) >= 2:
        kind, label = "speculative", "🎰 مضاربة غالبًا"
    elif news:
        kind, label = "unclear", "❓ غير واضح"
    else:
        kind, label = "speculative", "🎰 مضاربة غالبًا (بدون أخبار)"

    reasons = []
    if cat:
        reasons.append("المحفزات: " + "، ".join(dict.fromkeys(cat)))
    if spec:
        reasons.append("مؤشرات مضاربة: " + "، ".join(dict.fromkeys(spec)))
    if structural:
        reasons.append("خصائص السهم: " + "، ".join(structural))
    if not reasons:
        reasons.append("لا توجد أخبار أو محفزات واضحة حتى الآن")

    return Verdict(kind=kind, label=label, reasons=reasons, detail=verdict_detail(kind, mover))


def verdict_detail(kind: str, m: Mover) -> str:
    if kind == "catalyst":
        if m.market_cap_usd >= 500_000_000 and m.price >= 5:
            return "مناسب للمتابعة السوينغ — تحقق من اختراق الافتتاح وثبات السيولة."
        return "خبر جيد لكن السهم صغير — مناسب كداي تريد بحذر، ولا تعتمد عليه للاحتفاظ الطويل."
    if kind == "mixed":
        return "الخبر قد يكون حقيقيًا لكن الخصائص مضاربة — انتظر تأكيد الحجم بعد الافتتاح قبل أي دخول."
    if kind == "unclear":
        return "يوجد بعض الأخبار لكن لا محفز واضح — راقب قبل اتخاذ قرار."
    return "حركة بلا محفز أساسي واضح — عادة فخ للداي تريد، الأفضل تجنبها أو الدخول السريع بحجم صغير فقط."


def suitability_hint(m: Mover, verdict: Verdict) -> str:
    cap = m.market_cap_usd or 0
    hints = []
    if verdict.kind == "catalyst" and cap >= 500_000_000 and m.price >= 5:
        hints.append("سوينغ ✓")
    else:
        hints.append("داي تريد فقط بحذر")
    if m.dollar_volume >= 20_000_000:
        hints.append("سيولة ممتازة")
    elif m.dollar_volume >= 5_000_000:
        hints.append("سيولة مقبولة")
    else:
        hints.append("سيولة ضعيفة")
    return " / ".join(hints)


# ══════════════════════════════════════════════════════════════════════════
# تقارير
# ══════════════════════════════════════════════════════════════════════════

def fmt_money(v: float) -> str:
    if v >= 1e9:
        return f"{v/1e9:.2f}B"
    if v >= 1e6:
        return f"{v/1e6:.1f}M"
    if v >= 1e3:
        return f"{v/1e3:.1f}K"
    return f"{v:.0f}"


def rel_time(epoch: float) -> str:
    if not epoch:
        return "بدون وقت"
    diff = time.time() - epoch
    if diff < 0:
        return "الآن"
    if diff < 3600:
        return f"قبل {int(diff//60)} دقيقة"
    if diff < 86400:
        return f"قبل {int(diff//3600)} ساعة"
    return f"قبل {int(diff//86400)} يوم"


def _stock_block(m: Mover, verdict: Verdict, news: list[NewsItem], show_news: bool) -> str:
    lines = [
        f"{m.symbol} — {m.name}",
        f"  السعر ${m.price:.2f} | التغير {m.change_pct:+.1f}% | السابق ${m.prev_close:.2f} "
        f"| حجم ${fmt_money(m.dollar_volume)} | قيمة ${m.market_cap_raw}",
    ]
    if show_news:
        if news:
            for n in news[:4]:
                lines.append(f"  📰 ({rel_time(n.published)} | {n.source}) {n.title}")
        else:
            lines.append("  📰 لا توجد أخبار واضحة")
    lines.append(f"  🏷️ {verdict.label}")
    for r in verdict.reasons:
        lines.append(f"     • {r}")
    lines.append(f"  💡 {verdict.detail}")
    lines.append(f"  🎯 {suitability_hint(m, verdict)}")
    return "\n".join(lines)


def build_report(gainers: list[tuple[Mover, Verdict, list[NewsItem]]],
                 losers: list[tuple[Mover, Verdict, list[NewsItem]]],
                 show_news: bool, side: str) -> str:
    now_riyadh = datetime.now(RIYADH).strftime("%Y-%m-%d %H:%M")
    now_ny = datetime.now(NEW_YORK).strftime("%H:%M")

    counts = {}
    for _, v, _ in gainers:
        counts[v.kind] = counts.get(v.kind, 0) + 1

    head = [
        "═" * 70,
        "🛰️  تنبيهات ما قبل الافتتاح — stockanalysis.com",
        f"   الآن: {now_riyadh} (الرياض) | {now_ny} (نيويورك)",
        f"   النطاق: ${args.min_price}–${args.max_price} | الصاعدون: {len(gainers)} | الهابطون: {len(losers)}",
        f"   التصنيف: 🔥 محفز {counts.get('catalyst', 0)} | ⚠️ خبر+مضاربة {counts.get('mixed', 0)} "
        f"| 🎰 مضاربة {counts.get('speculative', 0)} | ❓ غير واضح {counts.get('unclear', 0)}",
        "═" * 70,
    ]
    if side in ("both", "gainers") and gainers:
        head.append("\n🟢 الصاعدون (مفترزون حسب الأهمية)")
        order = {"catalyst": 0, "mixed": 1, "unclear": 2, "speculative": 3}
        for m, v, news in sorted(gainers, key=lambda x: (order[x[1].kind], -x[0].change_pct)):
            head.append(_stock_block(m, v, news, show_news))
            head.append("")
    if side in ("both", "losers") and losers:
        head.append("🔴 الهابطون")
        for m, v, news in sorted(losers, key=lambda x: x[0].change_pct):
            head.append(_stock_block(m, v, news, show_news))
            head.append("")
    head.append("═" * 70)
    head.append("نصيحة: اطلع على حجم أول 15 دقيقة بعد الافتتاح — الحجم يؤكد المحفز الحقيقي.")
    return "\n".join(head)


def build_line_summary(gainers: list[tuple[Mover, Verdict, list[NewsItem]]], max_items: int = 8) -> str:
    order = {"catalyst": 0, "mixed": 1, "unclear": 2, "speculative": 3}
    top = sorted(gainers, key=lambda x: (order[x[1].kind], -x[0].change_pct))[:max_items]
    lines = ["🛰️ تنبيهات Premarket (2-50$)"]
    for m, v, _ in top:
        lines.append(f"{v.label.split()[0]} {m.symbol} {m.change_pct:+.1f}% @ ${m.price:.2f}")
    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════
# main
# ══════════════════════════════════════════════════════════════════════════

def main() -> int:
    global args
    p = argparse.ArgumentParser(description="تنبيهات premarket لأسهم $2–$50 مع تحليل الأخبار")
    p.add_argument("--min-price", type=float, default=2.0)
    p.add_argument("--max-price", type=float, default=50.0)
    p.add_argument("--min-change", type=float, default=5.0, help="أقل تغيير (نسبة مئوية) للتنبيه")
    p.add_argument("--side", choices=["gainers", "losers", "both"], default="both")
    p.add_argument("--limit", type=int, default=40, help="أقصى عدد لكل قائمة")
    p.add_argument("--refresh", action="store_true", help="تجاهل كاش الصفحة")
    p.add_argument("--no-news", action="store_true", help="بدون جلب أخبار")
    p.add_argument("--line", action="store_true", help="إرسال ملخص عبر LINE")
    p.add_argument("--json", type=str, default="", help="حفظ النتائج بصيغة JSON")
    args = p.parse_args()

    print("جلب بيانات premarket...")
    html = fetch_page(refresh=args.refresh)
    gainers_all, losers_all = parse_movers(html)

    def filt(items: list[Mover]) -> list[Mover]:
        return [m for m in items
                if args.min_price <= m.price <= args.max_price
                and abs(m.change_pct) >= args.min_change][: args.limit]

    gainers_f, losers_f = filt(gainers_all), filt(losers_all)
    print(f"تم: {len(gainers_all)} صاعد / {len(losers_all)} هابط — بعد التصفية: "
          f"{len(gainers_f)} صاعد / {len(losers_f)} هابط")

    targets = gainers_f + (losers_f if args.side in ("both", "losers") else [])
    targets = list({m.symbol: m for m in targets}.values())

    if args.no_news:
        news_map = {m.symbol: [] for m in targets}
    else:
        print("جلب الأخبار والتصنيف...")
        news_map: dict[str, list[NewsItem]] = {}
        with ThreadPoolExecutor(max_workers=8) as ex:
            futs = {ex.submit(fetch_news, m.symbol): m.symbol for m in targets}
            done = 0
            for fut in as_completed(futs):
                done += 1
                sym = futs[fut]
                try:
                    news_map[sym] = fut.result()
                except Exception:
                    news_map[sym] = []
                print(f"   [{done}/{len(futs)}] {sym}")
        sys.stdout.flush()

    def enrich(items: list[Mover]) -> list[tuple[Mover, Verdict, list[NewsItem]]]:
        return [(m, classify(m, news_map.get(m.symbol, [])), news_map.get(m.symbol, [])) for m in items]

    gainers_e, losers_e = enrich(gainers_f), enrich(losers_f)
    report = build_report(gainers_e, losers_e, show_news=not args.no_news, side=args.side)
    print("\n" + report)

    if args.json:
        payload = {
            "generated_at": datetime.now(RIYADH).isoformat(),
            "filter": {"min_price": args.min_price, "max_price": args.max_price, "min_change": args.min_change},
            "gainers": [{"symbol": m.symbol, "name": m.name, "price": m.price, "change_pct": m.change_pct,
                         "volume": m.volume, "market_cap": m.market_cap_raw, "verdict": v.kind,
                         "reasons": v.reasons, "news": [n.title for n in news]} for m, v, news in gainers_e],
            "losers": [{"symbol": m.symbol, "name": m.name, "price": m.price, "change_pct": m.change_pct,
                        "volume": m.volume, "market_cap": m.market_cap_raw, "verdict": v.kind,
                        "reasons": v.reasons, "news": [n.title for n in news]} for m, v, news in losers_e],
        }
        out = Path(args.json)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n📦 حُفظت النتائج في: {out}")

    if args.line:
        try:
            from engines.notify import send_line
            send_line(build_line_summary(gainers_e))
        except Exception as e:
            print(f"LINE فشل: {e}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
