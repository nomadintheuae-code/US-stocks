#!/usr/bin/env python3
"""
يولّد تقرير HTML عربي احترافي للصاعدين فقط في جلسة premarket.
الملف الناتج: <PremarketAlerts>_<التاريخ والوقت>.html — جاهز للمشاركة عبر WhatsApp.
"""
from __future__ import annotations

import json
import base64
import os
import re
import socket
import subprocess
import sys
from datetime import datetime
from html import escape
from pathlib import Path
from zoneinfo import ZoneInfo

import premarket_alerts as pa

sys.path.insert(0, str(pa.BASE_DIR))
try:
    from engines.analysis import RSAnalyzer, VCPAnalyzer
    from engines.data import CurrencyEngine, DataEngine
    from engines.earnings import EarningsCalendarEngine
    from engines.regime import MarketRegimeEngine
    from engines.risk import PositionSizer
    TECH_AVAILABLE = True
except Exception:
    TECH_AVAILABLE = False

HISTORY_FILE = pa.CACHE_DIR / "history.json"
SERVE_DIR = pa.BASE_DIR / "serve_premarket"
PID_FILE = pa.CACHE_DIR / "serve.pid"

RS_ERROR = -999.0
VCP_SIGNAL_AR = {
    "Tight Base (VCP)": "قاعدة منكمشة (VCP)",
    "V-Contraction Detected": "انكماش تذبذب مؤكد",
    "Volume Dry-up Detected": "جفاف حجم أثناء القاعدة",
    "Trend Alignment OK": "محاذاة اتجاه جيدة",
    "Near Pivot Point": "قريب من نقطة الانطلاق",
}

MIN_PRICE, MAX_PRICE = 2.0, 50.0
MIN_CHANGE = 5.0
LIMIT = 12
RIYADH = ZoneInfo("Asia/Riyadh")
NEW_YORK = ZoneInfo("America/New_York")


EMOJI_RE = re.compile(
    r"[\U0001F300-\U0001FAFF\u2600-\u27BF\uFE0F\u2713\u2714\u2705\u274C\u2B50\u2190-\u21FF]"
)


def no_emoji(s: str) -> str:
    s = EMOJI_RE.sub("", s or "")
    s = re.sub(r"\s+", " ", s).strip()
    return s

NEGATIVE_RE = re.compile(
    r"(fall|drop|sink|slid|miss(es|ed)?|downgrade|sell(s|ing)?|offering|dilut\w*|"
    r"reverse[- ]?split|warning|loss(es)?|plunge|decline|cuts?|lawsuit|fraud|"
    r"delist\w*|bankrupt\w*|halt(ed)?|volatil\w*|short squeeze|pump|hype|"
    r"down|selloff|tumble|retreat)", re.I)
POSITIVE_RE = re.compile(
    r"(beat|surge|jump|gain|win(s|ning)?|approve\w*|partner\w*|contract|merger|"
    r"acquisit\w*|guidance|upgrade\w*|record|launch\w*|agreement|outperform|"
    r"breakout|soar)", re.I)


def analyze(mover: pa.Mover, news: list[pa.NewsItem]) -> dict:
    text = " ".join(n.title for n in news).lower()
    cat = pa._match(pa.CATALYST_PATTERNS, text)
    spec = pa._match(pa.SPEC_PATTERNS, text)

    structural = []
    if mover.price < 3:
        structural.append("السعر أقل من 3 دولارات")
    if mover.market_cap_usd and mover.market_cap_usd < 200_000_000:
        structural.append("القيمة السوقية أقل من 200 مليون دولار")
    if abs(mover.change_pct) > 100:
        structural.append("حركة تتجاوز 100%")
    if mover.dollar_volume < 10_000_000:
        structural.append("سيولة قبل الافتتاح ضعيفة نسبيا")
    if not mover.dollar_volume:
        structural.append("لا يوجد حجم قبل الافتتاح")

    verdict = pa.classify(mover, news)

    neg_titles = [n for n in news if NEGATIVE_RE.search(n.title)]
    pos_titles = [n for n in news if n not in neg_titles and POSITIVE_RE.search(n.title)]
    other = [n for n in news if n not in neg_titles and n not in pos_titles]

    score = 100
    base = {"catalyst": 74, "mixed": 54, "unclear": 38, "speculative": 22}[verdict.kind]
    score = base
    if 5 <= mover.price <= 40:
        score += 8
    if mover.market_cap_usd >= 500_000_000:
        score += 10
    elif mover.market_cap_usd < 200_000_000:
        score -= 12
    if mover.dollar_volume >= 20_000_000:
        score += 8
    elif 0 < mover.dollar_volume < 5_000_000:
        score -= 8
    if abs(mover.change_pct) > 100:
        score -= 6
    if mover.price < 3:
        score -= 8
    if cat and any(n.published and time_ok(n.published) for n in news):
        score += 6
    score = max(0, min(100, score))

    if score >= 70:
        conf, level = "متوسطة إلى عالية", "عالية"
    elif score >= 50:
        conf, level = "متوسطة", "متوسطة"
    elif score >= 35:
        conf, level = "منخفضة إلى متوسطة", "منخفضة"
    else:
        conf, level = "منخفضة جدا", "منخفضة"

    return {
        "verdict": verdict,
        "cat": list(dict.fromkeys(cat)),
        "spec": list(dict.fromkeys(spec)),
        "structural": structural,
        "pos_titles": pos_titles,
        "neg_titles": neg_titles,
        "other": other,
        "score": score,
        "confidence": conf,
        "confidence_level": level,
        "suit": pa.suitability_hint(mover, verdict),
    }


def time_ok(epoch: float, hours: float = 8.0) -> bool:
    import time as _t
    return epoch and (_t.time() - epoch) < hours * 3600


def _earnings_days(earnings: dict) -> int | None:
    try:
        ed = earnings.get("Earnings Date") if isinstance(earnings, dict) else None
        if not ed:
            return None
        if isinstance(ed, (tuple, list)) and ed:
            ed = ed[0]
        if isinstance(ed, datetime):
            d = ed.date()
        elif isinstance(ed, str):
            d = datetime.fromisoformat(ed[:10].replace("/", "-")).date()
        else:
            return None
        return (d - datetime.now().date()).days
    except Exception:
        return None


def technical_analysis(m: pa.Mover, spy_df, capital_usd: float, risk_pct: float) -> dict:
    """تقييم فني (VCP/RS/حالة السوق) وإدارة مخاطر (ATR/حجم مركز) من محركات المشروع."""
    base = {"ok": False, "note": "بيانات غير كافية"}
    try:
        if not TECH_AVAILABLE:
            return {**base, "note": "الوحدة الفنية غير متاحة"}
        df = DataEngine.get_data(m.symbol)
        if df is None or df.empty or len(df) < 30:
            return {**base, "note": "لا توجد بيانات يومية كافية"}

        vcp = VCPAnalyzer.calculate(df) or {}
        atr = float(vcp.get("atr") or PositionSizer.calculate_atr(df) or 0.0)
        rs_raw = RSAnalyzer.get_raw_score(df)
        spy_raw = RSAnalyzer.get_raw_score(spy_df) if spy_df is not None else None
        regime = MarketRegimeEngine.analyze(spy_df) if spy_df is not None else None
        regime_mult = MarketRegimeEngine.position_size_multiplier(regime.regime) if regime else 1.0
        ps = PositionSizer.size_position(df, capital_usd, risk_pct=risk_pct,
                                         stop_atr_mult=2.0, regime_mult=regime_mult)
        try:
            earnings = EarningsCalendarEngine.get_next_earnings(m.symbol)
        except Exception:
            earnings = None
        earnings_days = _earnings_days(earnings)

        atr_pct = (atr / m.prev_close * 100.0) if (atr > 0 and m.prev_close > 0) else 0.0
        extended = m.change_pct > 15.0 or (atr_pct > 0 and m.change_pct > 3 * atr_pct)
        entry_lo = max(m.prev_close, m.price * 0.96)
        entry_hi = m.price
        stop_swing = entry_hi - 2 * atr
        stop_day = entry_hi - atr
        t1 = entry_hi + 2 * atr * 1.5
        t2 = entry_hi + 2 * atr * 2.5

        rs_text = "غير متاح"
        if rs_raw is not None and rs_raw != RS_ERROR:
            if spy_raw is not None and spy_raw != RS_ERROR:
                diff = rs_raw - spy_raw
                rs_text = f"أقوى من SPY ({diff:+.1f})" if diff >= 0 else f"أضعف من SPY ({diff:+.1f})"
            else:
                rs_text = f"الدرجة {rs_raw:.1f}"

        return {
            "ok": True,
            "vcp_score": int(vcp.get("score") or 0),
            "vcp_signals": [VCP_SIGNAL_AR.get(s, s) for s in vcp.get("signals", [])],
            "atr": atr,
            "atr_pct": atr_pct,
            "rs_raw": rs_raw,
            "rs_text": rs_text,
            "regime": regime.to_dict() if regime else None,
            "regime_mult": regime_mult,
            "extended": extended,
            "entry_lo": entry_lo,
            "entry_hi": entry_hi,
            "stop_day": stop_day,
            "stop_swing": stop_swing,
            "t1": t1,
            "t2": t2,
            "shares": ps.shares if ps else None,
            "dollar_amount": ps.dollar_amount if ps else None,
            "risk_amount": ps.risk_amount if ps else None,
            "earnings_days": earnings_days,
            "note": "",
        }
    except Exception as exc:
        return {**base, "note": f"تعذر التحليل الفني ({type(exc).__name__})"}


def technical_html(m: pa.Mover, tech: dict) -> str:
    if not tech.get("ok"):
        return (f'<div class="sec tech"><h4>الفني (Technical)</h4>'
                f'<p class="note-x">{escape(tech.get("note", "بيانات غير كافية"))}</p></div>')
    c = score_color(tech["vcp_score"])
    vcp_line = f'VCP: <b style="color:{c}">{tech["vcp_score"]}/105</b>'
    if tech["vcp_signals"]:
        vcp_line += " — " + "، ".join(escape(s) for s in tech["vcp_signals"][:3])
    reg = tech.get("regime") or {}
    reg_ar = {"bull": "اتجاه صاعد", "bear": "اتجاه هابط",
              "sideways": "جانبية", "transition": "مرحلة انتقال"}.get(reg.get("regime"), "غير محدد")
    reg_color = {"bull": "#0a7d33", "bear": "#c62828"}.get(reg.get("regime"), "#b8860b")
    conf = round(float(reg.get("confidence", 0)) * 100)
    lines = [f'<p>{vcp_line}</p>',
             f'<p>القوة النسبية: <b>{escape(tech["rs_text"])}</b>'
             + (f' — الترتيب: أعلى من {tech["rank_pct"]}% من قائمة اليوم' if tech.get("rank_pct") is not None else '')
             + '</p>',
             f'<p>حالة السوق (SPY): <b style="color:{reg_color}">{reg_ar}</b> (ثقة {conf}%)</p>']
    if tech.get("extended"):
        lines.append('<p style="color:#c62828"><b>حركة ممددة:</b> تجاوزت 15% أو 3 أضعاف ATR اليومي — لا تلاحق السعر.</p>')
    if tech.get("earnings_days") is not None and 0 <= tech["earnings_days"] <= 10:
        col = "#c62828" if tech["earnings_days"] <= 5 else "#b8860b"
        lines.append(f'<p style="color:{col}"><b>أرباح قريبة:</b> الإعلان بعد {tech["earnings_days"]} يوم — تقلب مرتفع متوقع.</p>')
    return '<div class="sec tech"><h4>الفني (Technical)</h4>' + "".join(lines) + '</div>'


def risk_mgmt_html(tech: dict) -> str:
    if not tech.get("ok"):
        return (f'<div class="sec riskm"><h4>إدارة المخاطر (Risk Management)</h4>'
                f'<p class="note-x">{escape(tech.get("note", "غير متاح"))}</p></div>')
    stop_day_pct = ((tech["entry_hi"] - tech["stop_day"]) / tech["entry_hi"] * 100) if tech["entry_hi"] else 0
    stop_sw_pct = ((tech["entry_hi"] - tech["stop_swing"]) / tech["entry_hi"] * 100) if tech["entry_hi"] else 0
    if tech.get("shares"):
        pos = (f'المركز المقترح: <b>{tech["shares"]:,} سهم</b> ≈ ${tech["dollar_amount"]:,.0f} '
               f'(خطر ${tech["risk_amount"]:,.0f})')
    else:
        pos = "المركز المقترح: غير محسوب (رأس مال غير كاف أو بيانات ناقصة)"
    return (f'<div class="sec riskm"><h4>إدارة المخاطر (Risk Management)</h4>'
            f'<p>منطقة الدخول: <b>${tech["entry_lo"]:.2f} – ${tech["entry_hi"]:.2f}</b></p>'
            f'<p>وقف الداي تريد: <b>${tech["stop_day"]:.2f}</b> (-{stop_day_pct:.1f}%) '
            f'— وقف السوينغ: <b>${tech["stop_swing"]:.2f}</b> (-{stop_sw_pct:.1f}%)</p>'
            f'<p>الأهداف (R = 2×ATR): <b>${tech["t1"]:.2f}</b> (1.5R) ثم <b>${tech["t2"]:.2f}</b> (2.5R)</p>'
            f'<p>{pos}</p>'
            f'<p class="suit">مبني على ATR(14) وحالة السوق ورأس المال من config.yaml</p></div>')


def score_color(s: int) -> str:
    if s >= 70:
        return "#0a7d33"
    if s >= 50:
        return "#b8860b"
    if s >= 35:
        return "#e65100"
    return "#c62828"


def rel_time(epoch: float) -> str:
    return pa.rel_time(epoch) if epoch else "بدون وقت محدد"


def money(v: float) -> str:
    return pa.fmt_money(v)


def stock_link(symbol: str) -> str:
    return f"https://stockanalysis.com/stocks/{symbol.lower()}/"


def news_html(title: str, url: str, published: float, source: str, cls: str) -> str:
    t = escape(title)
    href = escape(url) if url.startswith("http") else "#"
    badge = "سلبية" if cls == "neg" else ("إيجابية" if cls == "pos" else "عامة")
    color = "#c62828" if cls == "neg" else ("#0a7d33" if cls == "pos" else "#546e7a")
    return (f'<div class="news {cls}"><span class="news-badge" style="color:{color}">{badge}</span>'
            f'<a href="{href}" target="_blank" rel="noopener">{t}</a>'
            f'<span class="news-meta">{rel_time(published)} — {escape(source)}</span></div>')


def card_html(i: int, m: pa.Mover, a: dict, tech: dict, is_new: bool = False, is_extra: bool = False) -> str:
    v = a["verdict"]
    label_color = {"catalyst": "#0a7d33", "mixed": "#b8860b",
                   "speculative": "#c62828", "unclear": "#546e7a"}[v.kind]
    v.label = no_emoji(v.label)
    a["suit"] = no_emoji(a["suit"])
    cat_txt = "، ".join(a["cat"]) or "لا يوجد محفز واضح"
    spec_txt = "، ".join(a["spec"]) or "لا توجد مؤشرات مضاربة صريحة"
    struct_txt = "؛ ".join(a["structural"]) or "لا توجد مخاطر هيكلية بارزة"
    risk_css = "#c62828" if a["structural"] else "#8d6e63"

    bull = (news_html(n.title, n.url, n.published, n.source, "pos") for n in a["pos_titles"])
    bear = (news_html(n.title, n.url, n.published, n.source, "neg") for n in a["neg_titles"])
    gen = (news_html(n.title, n.url, n.published, n.source, "gen") for n in a["other"])
    bull_html = "".join(bull) or f'<div class="news none">لا توجد عناوين إيجابية واضحة</div>'
    bear_html = "".join(bear) or f'<div class="news none">لا توجد عناوين سلبية واضحة</div>'
    gen_html = "".join(gen)

    new_badge = ('<span class="badge nb" style="background:#6a1b9a">وافد جديد</span>'
                 if is_new else '')
    extra_badge = ('<span class="badge eb" style="background:#00796b">مصدر إضافي: TradingView</span>'
                   if is_extra else '')
    tech_html = technical_html(m, tech)
    riskm_html = risk_mgmt_html(tech)
    return f"""
<article class="card" id="s{i}">
  <div class="card-head">
    <div class="tick"><a href="{stock_link(m.symbol)}" target="_blank" rel="noopener">{m.symbol}</a>
      <span class="name">{escape(m.name)}</span></div>
    <span class="chg {'up' if m.change_pct >= 0 else 'down'}">{m.change_pct:+.1f}%</span>
  </div>
  <div class="badges"><span class="badge" style="background:{label_color}">{v.label}</span>{new_badge}{extra_badge}</div>
  <table class="stats">
    <tr><td>السعر قبل الافتتاح</td><td>${m.price:.2f}</td>
        <td>الإغلاق السابق</td><td>${m.prev_close:.2f}</td></tr>
    <tr><td>حجم التداول</td><td>{m.volume:,}</td>
        <td>سيولة بالدولار</td><td>${money(m.dollar_volume)}</td></tr>
    <tr><td>القيمة السوقية</td><td>{m.market_cap_raw if m.market_cap_raw else 'غير متوفر'}</td>
        <td>الترتيب</td><td>{m.rank}</td></tr>
  </table>

  {tech_html}
  {riskm_html}

  <div class="sec bull"><h4>إيجابي (Bullish)</h4><p>{escape(cat_txt)}</p>{bull_html}{gen_html}</div>
  <div class="sec bear"><h4>سلبي (Bearish)</h4><p>{escape(spec_txt)}</p>{bear_html}</div>
  <div class="sec risk"><h4>مخاطر (Risks)</h4><p style="color:{risk_css}">{escape(struct_txt)}</p></div>
  <div class="sec action"><h4>خطة العمل (Action Plan)</h4><p>{escape(v.detail)}</p>
    <p class="suit">الملاءمة: {escape(a['suit'])}</p></div>
</article>"""


def exec_summary_html(top, second, all_analyses) -> str:
    m = top["mover"]
    a = top["analysis"]
    tech = top.get("tech") or {}
    if tech.get("ok"):
        entry_lo, entry_hi = tech["entry_lo"], tech["entry_hi"]
        stop_day, stop_swing = tech["stop_day"], tech["stop_swing"]
        t1, t2 = tech["t1"], tech["t2"]
        stop_src = "بناء على ATR(14)"
    else:
        entry_lo = max(m.prev_close, m.price * 0.96)
        entry_hi = m.price
        stop_day = round(m.price * 0.95, 2)
        stop_swing = round(entry_lo * 0.90, 2)
        t1 = round(m.price * 1.10, 2)
        t2 = round(m.price * 1.20, 2)
        stop_src = "تقدير تقريبي (بدون بيانات فنية)"

    alerts = []
    alerts.append(f"راقب حجم أول 15 دقيقة بعد الافتتاح لتأكيد قوة الحركة في {m.symbol}.")
    if a["verdict"].kind == "catalyst":
        alerts.append("تحقق من البيان الرسمي للشركة ومصدر الخبر قبل أي قرار.")
        alerts.append("ضع أوامر معلقة بجوار مناطق الدعم ولا تلاحق السعر أثناء التمدد.")
    else:
        alerts.append("الحركة تحمل مؤشرات مضاربة: تجنب الدخول قبل استقرار السعر.")
        alerts.append("أي خبر تخفيف أو إصدار أسهم قد يقلب الاتجاه فجأة.")
    if a["structural"]:
        alerts.append("القيمة السوقية الصغيرة تزيد حساسية السهم للتقلب الحاد.")
    if tech.get("extended"):
        alerts.append("الحركة ممددة فنيا: انتظر تصحيحا نحو منطقة الدخول قبل الالتزام.")
    if tech.get("earnings_days") is not None and 0 <= tech["earnings_days"] <= 10:
        alerts.append(f"يعلن {m.symbol} أرباحه بعد {tech['earnings_days']} يوم — توقع تقلبا حادا.")
    if tech.get("shares"):
        alerts.append(f"حجم المركز المقترح: {tech['shares']:,} سهم بحوالي ${tech['dollar_amount']:,.0f}.")

    return f"""
<div class="card exec">
  <h3>الملخص التنفيذي (Executive Summary)</h3>
  <table class="exec-table">
    <tr><th>فرصة الاستثمار (Opportunity Score)</th>
        <td><span class="score" style="color:{score_color(a['score'])}">{a['score']} / 100</span>
        — السهم الأقوى: <a href="{stock_link(m.symbol)}" target="_blank" rel="noopener">{m.symbol}</a></td></tr>
    <tr><th>مستوى الثقة (Confidence Level)</th><td>{a['confidence']}</td></tr>
    <tr><th>منطقة الدخول (Entry Zone)</th><td>بين ${entry_lo:.2f} و ${entry_hi:.2f} ({stop_src})</td></tr>
    <tr><th>أهداف الخروج (Exit Targets)</th><td>الهدف الأول ${t1:.2f} (1.5R) — الهدف الثاني ${t2:.2f} (2.5R)</td></tr>
    <tr><th>وقف الخسارة (Stop Loss)</th><td>للداي تريد ${stop_day:.2f} — للسوينغ ${stop_swing:.2f} ({stop_src})</td></tr>
    <tr><th>تنبيهات أساسية (Key Alerts)</th><td><ul>{"".join(f'<li>{escape(x)}</li>' for x in alerts)}</ul></td></tr>
    <tr><th>التوصية النهائية (Final Recommendation)</th><td>{final_reco(a)}</td></tr>
  </table>
  <p class="disclaimer">ملاحظة: الأرقام والمناطق مقترحة آلية مبنية على بيانات ما قبل الافتتاح والتحليل الفني اليومي، ولا تشكل نصيحة مالية.</p>
</div>"""


def final_reco(a: dict) -> str:
    s = a["score"]
    if s >= 70:
        return "دخول تدريجي بعد تأكيد الحجم، مع وقف خسارة صارم وإدارة مخاطر صارمة."
    if s >= 50:
        return "متابعة وانتظار تأكيد الافتتاح؛ لا يفضل الدخول الفوري قبل ثبات السعر."
    if s >= 35:
        return "مراقبة فقط أو تداول سريع بحجم صغير جدا للمتمرسين."
    return "تجنب الاقتراب؛ الحركة مضاربة بدون محفز أساسي واضح."


def build_html(gainers_e, tech_map=None, newcomers=(), compared_ts="", extra_syms=None, share_url="") -> str:
    now_r = datetime.now(RIYADH)
    now_ny = datetime.now(NEW_YORK)
    date_r = now_r.strftime("%Y-%m-%d")
    time_r = now_r.strftime("%H:%M")
    time_ny = now_ny.strftime("%H:%M")
    date_ny = now_ny.strftime("%Y-%m-%d")

    share_html = ""
    if share_url:
        qr_img = qr_data_uri(share_url)
        share_html = f"""<div class="card qr-box">
  <h4>أرسل إلى هاتفك</h4>
  <p>امسح الرمز بكاميرا الهاتف لفتح التقرير (نفس شبكة Wi-Fi):</p>
  {f'<img src="{qr_img}" alt="رمز وصول" class="qr-img">' if qr_img else ''}
  <p class="qr-url">{escape(share_url)}</p>
</div>"""

    analyses = []
    for m, v, news in gainers_e:
        analyses.append({"mover": m, "news": news, "analysis": analyze(m, news)})
    analyses.sort(key=lambda x: x["analysis"]["score"], reverse=True)

    tech_map = tech_map or {}
    rs_vals = [t["rs_raw"] for t in tech_map.values()
               if t.get("ok") and t.get("rs_raw") is not None and t["rs_raw"] != RS_ERROR]

    def rank_pct(raw):
        if raw is None or raw == RS_ERROR or not rs_vals:
            return None
        below = sum(1 for v in rs_vals if v <= raw)
        return int(below / len(rs_vals) * 100)

    for x in analyses:
        t = dict(tech_map.get(x["mover"].symbol) or {})
        if t.get("ok") and t.get("rs_raw") is not None and t["rs_raw"] != RS_ERROR:
            rp = rank_pct(t["rs_raw"])
            if rp is not None:
                t["rank_pct"] = rp
        x["tech"] = t

    new_set = set(newcomers)
    extra_set = set(extra_syms or ())
    cards = "".join(card_html(i + 1, x["mover"], x["analysis"], x["tech"],
                             is_new=x["mover"].symbol in new_set,
                             is_extra=x["mover"].symbol in extra_set) for i, x in enumerate(analyses))
    summary = exec_summary_html(analyses[0], analyses[1] if len(analyses) > 1 else None, analyses) if analyses else ""

    best = analyses[0]["analysis"] if analyses else None
    new_set = set(newcomers)
    newcomer_note = ""
    if newcomers:
        comp = f" (مقارنة بآخر تشغيل {escape(compared_ts)})" if compared_ts else ""
        links = "، ".join(
            f'<a href="{stock_link(s)}" target="_blank" rel="noopener">{s}</a>' for s in newcomers)
        newcomer_note = f"""<div class="card note-new">
  <h4>ملاحظة: وافدون جدد</h4>
  <p>الأسهم التالية ظهرت حديثا في قائمة الصاعدين ولم تكن ضمن آخر تشغيل: {links}{comp} — تحقق من أخبارها قبل أي قرار.</p>
</div>"""
    best_label = (f'<span class="badge" style="background:{score_color(best["score"])}">'
                  f'الأفضل: {analyses[0]["mover"].symbol} — {best["score"]}/100</span>') if best else ""

    return f"""<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="theme-color" content="#ffffff">
<meta property="og:title" content="تنبيهات ما قبل الافتتاح — الأسهم الصاعدة">
<meta property="og:description" content="تقرير تحليلي لأهم الأسهم الصاعدة في جلسة ما قبل الافتتاح بين 2 و50 دولارا">
<title>تنبيهات ما قبل الافتتاح — الأسهم الصاعدة</title>
<style>
  :root {{
    --bg:#f5f7fa; --card:#ffffff; --ink:#1a2333; --muted:#5b6b7f;
    --green:#0a7d33; --green-bg:#e7f6ec; --red:#c62828; --red-bg:#fdecec;
    --blue:#1565c0; --blue-bg:#e8f1fc; --amber:#8a6d00; --amber-bg:#fbf3dd;
    --line:#e3e8ef; --radius:14px;
  }}
  * {{ box-sizing:border-box; margin:0; padding:0; }}
  body {{ background:var(--bg); color:var(--ink); font-family:"Segoe UI","Tahoma","Noto Kufi Arabic",Arial,sans-serif; line-height:1.6; }}
  .wrap {{ max-width:760px; margin:0 auto; padding:14px 12px 30px; }}
  header {{ background:linear-gradient(135deg,#0d2b4e,#14477a); color:#fff; border-radius:var(--radius); padding:20px 18px; text-align:center; }}
  header h1 {{ font-size:1.25rem; font-weight:700; margin-bottom:6px; }}
  header .sub {{ font-size:.9rem; opacity:.9; }}
  .times {{ display:flex; gap:10px; justify-content:center; flex-wrap:wrap; margin-top:12px; }}
  .times div {{ background:rgba(255,255,255,.12); padding:8px 12px; border-radius:10px; font-size:.85rem; }}
  .times b {{ display:block; font-size:1rem; }}
  .filters {{ display:flex; gap:8px; flex-wrap:wrap; justify-content:center; margin:14px 0 4px; }}
  .filters span {{ background:var(--card); border:1px solid var(--line); border-radius:20px; padding:4px 12px; font-size:.8rem; color:var(--muted); }}
  .card {{ background:var(--card); border:1px solid var(--line); border-radius:var(--radius); padding:16px; margin:14px 0; box-shadow:0 1px 4px rgba(16,42,67,.06); }}
  .card-head {{ display:flex; justify-content:space-between; align-items:center; gap:10px; }}
  .tick a {{ font-size:1.25rem; font-weight:800; color:var(--blue); text-decoration:none; }}
  .tick a:hover {{ text-decoration:underline; }}
  .name {{ display:block; font-size:.8rem; color:var(--muted); }}
  .chg {{ font-weight:800; font-size:1.15rem; padding:4px 10px; border-radius:10px; }}
  .chg.up {{ background:var(--green-bg); color:var(--green); }}
  .chg.down {{ background:var(--red-bg); color:var(--red); }}
  .badges {{ display:flex; gap:8px; flex-wrap:wrap; margin:10px 0 8px; }}
  .badge {{ display:inline-block; color:#fff; font-size:.75rem; font-weight:700; padding:3px 10px; border-radius:8px; }}
  .badge.nb {{ border:1px solid #6a1b9a; }}
  .note-new {{ background:var(--amber-bg); border:1px solid #e0c86a; border-right:4px solid var(--amber); }}
  .note-new h4 {{ color:var(--amber); font-size:.9rem; margin-bottom:4px; }}
  .note-new p {{ font-size:.85rem; }}
  .note-new a {{ color:var(--blue); font-weight:700; text-decoration:none; }}
  table.stats {{ width:100%; border-collapse:collapse; font-size:.85rem; margin-bottom:10px; }}
  table.stats td {{ padding:6px 4px; border-bottom:1px dashed var(--line); }}
  table.stats td:nth-child(even) {{ font-weight:700; color:var(--ink); }}
  .sec {{ border-radius:10px; padding:10px 12px; margin:8px 0; font-size:.86rem; }}
  .sec h4 {{ font-size:.8rem; margin-bottom:4px; letter-spacing:.2px; }}
  .sec p {{ color:var(--ink); }}
  .sec.bull {{ background:var(--green-bg); border-right:4px solid var(--green); }}
  .sec.bull h4 {{ color:var(--green); }}
  .sec.bear {{ background:var(--red-bg); border-right:4px solid var(--red); }}
  .sec.bear h4 {{ color:var(--red); }}
  .sec.risk {{ background:#fdf1f0; border-right:4px solid #d84315; }}
  .sec.risk h4 {{ color:#d84315; }}
  .sec.action {{ background:var(--blue-bg); border-right:4px solid var(--blue); }}
  .sec.action h4 {{ color:var(--blue); }}
  .sec.tech {{ background:#eef3f9; border-right:4px solid #546e7a; }}
  .sec.tech h4 {{ color:#455a64; }}
  .sec.riskm {{ background:var(--blue-bg); border-right:4px solid var(--blue); }}
  .sec.riskm h4 {{ color:var(--blue); }}
  .note-x {{ color:var(--muted); font-size:.8rem; }}
  .qr-box {{ text-align:center; }}
  .qr-box h4 {{ color:#0d2b4e; margin-bottom:4px; }}
  .qr-box p {{ font-size:.85rem; color:var(--muted); }}
  .qr-img {{ max-width:220px; width:100%; height:auto; margin:10px auto; display:block; }}
  .qr-url {{ color:var(--blue); font-weight:700; font-size:.9rem; }}
  .news {{ font-size:.8rem; margin:6px 0; padding:6px 8px; background:rgba(255,255,255,.7); border-radius:8px; }}
  .news a {{ color:var(--ink); text-decoration:none; display:block; }}
  .news a:hover {{ color:var(--blue); }}
  .news-badge {{ font-size:.68rem; font-weight:700; margin-left:6px; }}
  .news-meta {{ display:block; color:var(--muted); font-size:.72rem; }}
  .news.none {{ color:var(--muted); background:transparent; padding:2px 0; }}
  .suit {{ color:var(--blue); font-weight:700; }}
  .exec h3 {{ color:var(--ink); margin-bottom:10px; font-size:1rem; }}
  table.exec-table {{ width:100%; border-collapse:collapse; font-size:.85rem; }}
  table.exec-table th {{ text-align:right; background:#eef2f7; padding:8px 10px; width:42%; color:#33475c; font-weight:700; border-bottom:1px solid var(--line); }}
  table.exec-table td {{ padding:8px 10px; border-bottom:1px solid var(--line); vertical-align:top; }}
  table.exec-table ul {{ padding-right:18px; }}
  .score {{ font-weight:800; font-size:1.05rem; }}
  .disclaimer {{ font-size:.75rem; color:var(--muted); margin-top:10px; }}
  footer {{ text-align:center; font-size:.75rem; color:var(--muted); margin-top:18px; }}
  footer a {{ color:var(--blue); text-decoration:none; }}
  @media (max-width:480px) {{
    header h1 {{ font-size:1.05rem; }}
    .wrap {{ padding:8px 8px 24px; }}
    table.stats {{ font-size:.78rem; }}
    table.exec-table th {{ width:38%; font-size:.78rem; }}
    .card {{ padding:12px; }}
  }}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>تنبيهات ما قبل الافتتاح — الأسهم الصاعدة</h1>
    <div class="sub">تحليل آلي للمحفزات وتصنيف الحركة (خبر حقيقي / مضاربة) — للصاعدين فقط</div>
    <div class="times">
      <div><b>{time_r}</b>{date_r} — الرياض</div>
      <div><b>{time_ny}</b>{date_ny} — نيويورك (التوقيت الشرقي)</div>
    </div>
  </header>

  <div class="filters">
    <span>النطاق السعري: ${MIN_PRICE:.1f} — ${MAX_PRICE:.0f}</span>
    <span>الحد الأدنى للتغير: {MIN_CHANGE:.0f}%</span>
    <span>عدد الأسهم المعروضة: {len(analyses)}</span>
  </div>
  <div style="text-align:center;margin:6px 0 2px;">{best_label}</div>

  <h2 style="font-size:1rem;margin:16px 4px 2px;">بطاقات الأسهم</h2>
  {cards}
  {newcomer_note}
  {summary}
  {share_html}

  <footer>
    المصدر: <a href="https://stockanalysis.com/markets/premarket/" target="_blank" rel="noopener">stockanalysis.com — Premarket Movers</a> |
    تم التوليد آليا في {time_r} بتوقيت الرياض<br>
    هذا التقرير تعليمي ولا يعد نصيحة مالية أو دعوة للشراء.
  </footer>
</div>
</body>
</html>"""


def load_history() -> list[dict]:
    if HISTORY_FILE.exists():
        try:
            return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def save_history(entries: list[dict]) -> None:
    HISTORY_FILE.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")


def detect_newcomers(symbols: list[str]) -> tuple[list[str], str]:
    """يعيد الأسهم التي ظهرت الآن ولم تكن ضمن آخر تشغيل، مع وقت ذلك التشغيل."""
    history = load_history()
    if not history:
        return [], ""
    prev = history[-1]
    prev_symbols = set(prev.get("symbols", []))
    newcomers = [s for s in symbols if s not in prev_symbols]
    return newcomers, prev.get("ts", "")


def load_extra_screen(path: str) -> tuple[list[pa.Mover], set[str]]:
    """يقرأ قائمة صاعدين خارجية (TradingView MCP) ويطبق نفس التصفية."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    movers, syms = [], set()
    for it in (data or {}).get("movers", []):
        sym = re.sub(r"^[A-Z]+:", "", str(it.get("symbol", ""))).strip().upper()
        if not sym:
            continue
        price = it.get("price") or it.get("close") or 0
        chg = it.get("change_pct") if it.get("change_pct") is not None else it.get("changePercent", 0)
        indicators = it.get("indicators") or {}
        vol = it.get("volume") or indicators.get("volume") or 0
        m = pa.Mover(rank=0, symbol=sym, name=it.get("name", ""),
                     change_pct=float(chg or 0), price=float(price or 0),
                     volume=int(vol or 0), market_cap_raw=it.get("market_cap_raw", ""))
        if MIN_PRICE <= m.price <= MAX_PRICE and m.change_pct >= MIN_CHANGE:
            movers.append(m)
            syms.add(sym)
    return movers, syms


# ── إرسال التقرير إلى الهاتف عبر LAN + QR ─────────────────────────────

def detect_lan_ip() -> str:
    try:
        out = subprocess.run(
            ["ip", "-4", "-o", "addr", "show", "scope", "global"],
            capture_output=True, text=True, timeout=5).stdout
        for line in out.splitlines():
            parts = line.split()
            for i, p in enumerate(parts):
                if p == "inet" and i + 1 < len(parts):
                    return parts[i + 1].split("/")[0]
    except Exception:
        pass
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        pass
    return "127.0.0.1"


def pick_port(preferred: int = 8765) -> int:
    for port in range(preferred, preferred + 20):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("0.0.0.0", port))
                return port
            except OSError:
                continue
    return 0


def server_alive() -> bool:
    if not PID_FILE.exists():
        return False
    try:
        pid = int(PID_FILE.read_text(encoding="utf-8").strip())
        os.kill(pid, 0)
        return True
    except (ValueError, ProcessLookupError, PermissionError):
        return False


def running_port() -> int | None:
    """يعيد منفذ الخادم الحي من ملف العملية (يدعم الصيغ القديمة)."""
    if not PID_FILE.exists():
        return None
    try:
        parts = PID_FILE.read_text(encoding="utf-8").strip().split()
        pid = int(parts[0])
        os.kill(pid, 0)
    except (ValueError, ProcessLookupError, PermissionError):
        return None
    if len(parts) > 1:
        try:
            return int(parts[1])
        except ValueError:
            return None
    try:
        args = [a.decode() for a in Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0")]
        idx = args.index("http.server")
        return int(args[idx + 1])
    except (ValueError, IndexError, OSError):
        return None


def start_share_server(port: int) -> None:
    if server_alive():
        print(f"خادم الإرسال يعمل بالفعل (المنفذ من ملف العملية)")
        return
    SERVE_DIR.mkdir(exist_ok=True)
    cmd = [sys.executable, "-m", "http.server", str(port), "--directory", str(SERVE_DIR)]
    devnull = open(os.devnull, "w")
    proc = subprocess.Popen(cmd, stdout=devnull, stderr=devnull, start_new_session=True)
    PID_FILE.write_text(f"{proc.pid} {port}", encoding="utf-8")
    print(f"تم تشغيل خادم الإرسال على المنفذ {port} (PID {proc.pid})")


def copy_to_serve(html_path: Path) -> None:
    SERVE_DIR.mkdir(exist_ok=True)
    data = html_path.read_bytes()
    (SERVE_DIR / "index.html").write_bytes(data)
    (SERVE_DIR / html_path.name).write_bytes(data)


def stop_share_server() -> None:
    if PID_FILE.exists():
        try:
            pid = int(PID_FILE.read_text(encoding="utf-8").strip())
            os.kill(pid, 15)
            print(f"تم إيقاف خادم الإرسال (PID {pid}).")
        except (ValueError, ProcessLookupError, PermissionError):
            print("لا توجد عملية حية لإيقافها (ملف معرف قديم).")
        try:
            PID_FILE.unlink()
        except OSError:
            pass
    else:
        print("لا يوجد خادم إرسال قيد التشغيل.")


def print_qr(url: str) -> None:
    print("\n" + "=" * 64)
    print("أرسل إلى هاتفك (Pixel) — امسح الرمز بكاميرا الهاتف:")
    print("  " + url)
    try:
        qr = subprocess.run(["qrencode", "-t", "ANSIUTF8", url],
                            capture_output=True, text=True, timeout=10)
        if qr.returncode == 0 and qr.stdout:
            print(qr.stdout)
    except Exception:
        pass
    print("ملاحظة: الهاتف على نفس شبكة Wi-Fi، والجهاز يبقى شغالًا أثناء القراءة.")
    print("لإيقاف الخادم لاحقا: premarket_html_report.py --stop-serve")
    print("=" * 64 + "\n")


def qr_data_uri(url: str) -> str:
    if not url:
        return ""
    try:
        p = subprocess.run(["qrencode", "-t", "PNG", "-o", "-", "-s", "6", url],
                           capture_output=True, timeout=10)
        if p.returncode == 0 and p.stdout:
            return "data:image/png;base64," + base64.b64encode(p.stdout).decode()
    except Exception:
        pass
    return ""


def main() -> int:
    import argparse
    p = argparse.ArgumentParser(description="توليد تقرير HTML للصاعدين وفتحه في المتصفح")
    p.add_argument("--no-open", action="store_true", help="عدم فتح التقرير في المتصفح بعد التوليد")
    p.add_argument("--no-technical", action="store_true", help="تخطي التحليل الفني وإدارة المخاطر")
    p.add_argument("--extra-screen", type=str, default="",
                   help="دمج قائمة صاعدين خارجية (JSON من TradingView MCP)")
    p.add_argument("--no-send-to-phone", action="store_true",
                   help="تعطيل خادم الإرسال إلى الهاتف ورمز QR")
    p.add_argument("--port", type=int, default=8765, help="منفذ خادم الإرسال إلى الهاتف")
    p.add_argument("--stop-serve", action="store_true", help="إيقاف خادم الإرسال الخلفي")
    args = p.parse_args()

    if args.stop_serve:
        stop_share_server()
        return 0

    print("جلب بيانات premarket (الصاعدون فقط)...")
    html = pa.fetch_page()
    gainers_all, _ = pa.parse_movers(html)
    filtered = [m for m in gainers_all
                if MIN_PRICE <= m.price <= MAX_PRICE and m.change_pct >= MIN_CHANGE][:LIMIT]
    extra_syms: set[str] = set()
    if args.extra_screen:
        extras, extra_syms = load_extra_screen(args.extra_screen)
        seen = {m.symbol for m in filtered}
        added = [m for m in extras if m.symbol not in seen]
        extra_syms = {m.symbol for m in added}
        filtered = filtered + added
        print(f"دمج من TradingView: {len(added)} سهم إضافي (من أصل {len(extras)} مستوفية)")
    print(f"الصاعدون بعد التصفية: {len(filtered)}")

    symbols = [m.symbol for m in filtered]
    newcomers, compared_ts = detect_newcomers(symbols)
    if newcomers:
        print("ملاحظة وافدون جدد (لم يكونوا في آخر تشغيل): " + "، ".join(newcomers))
        if compared_ts:
            print(f"المقارنة مع آخر تشغيل بتاريخ: {compared_ts}")
    else:
        print("لا توجد أسهم وافدة جديدة مقارنة بآخر تشغيل")
    history = load_history()
    now_h = datetime.now(RIYADH)
    history.append({"ts": now_h.isoformat(timespec="seconds"),
                    "date": now_h.strftime("%Y-%m-%d %H:%M"),
                    "symbols": symbols})
    save_history(history[-30:])

    news_map = {}
    with pa.ThreadPoolExecutor(max_workers=8) as ex:
        futs = {ex.submit(pa.fetch_news, m.symbol): m.symbol for m in filtered}
        for fut in pa.as_completed(futs):
            sym = futs[fut]
            try:
                news_map[sym] = fut.result()
            except Exception:
                news_map[sym] = []

    gainers_e = [(m, pa.classify(m, news_map.get(m.symbol, [])), news_map.get(m.symbol, []))
                 for m in filtered]

    tech_map = {}
    if TECH_AVAILABLE and not args.no_technical:
        print("تحليل فني وإدارة مخاطر (yfinance)...")
        try:
            from config import CONFIG as _PROJ_CFG
        except Exception:
            _PROJ_CFG = {}
        capital_jpy = float(_PROJ_CFG.get("CAPITAL_JPY", 1_000_000))
        risk_pct = float(_PROJ_CFG.get("ACCOUNT_RISK_PCT", 0.015))
        usd_jpy = CurrencyEngine.get_usd_jpy() or 150.0
        capital_usd = capital_jpy / usd_jpy
        spy_df = DataEngine.get_data("SPY")
        for idx, m in enumerate(filtered, 1):
            tech_map[m.symbol] = technical_analysis(m, spy_df, capital_usd, risk_pct)
            state = "تم" if tech_map[m.symbol].get("ok") else "ناقص"
            print(f"   [{idx}/{len(filtered)}] {m.symbol}: {state}")

    share_url = ""
    share_port = 0
    if not args.no_send_to_phone:
        live = running_port()
        share_port = live if live else pick_port(args.port)
        if share_port:
            share_url = f"http://{detect_lan_ip()}:{share_port}/"

    page = build_html(gainers_e, tech_map=tech_map,
                      newcomers=newcomers, compared_ts=compared_ts,
                      extra_syms=extra_syms, share_url=share_url)

    now = datetime.now(RIYADH)
    fname = f"PremarketAlerts_{now.strftime('%Y-%m-%d_%H-%M')}.html"
    out = Path.home() / "Documents" / fname
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, encoding="utf-8")
    print(f"تم إنشاء التقرير: {out} ({out.stat().st_size} بايت)")
    if not args.no_open:
        import webbrowser
        webbrowser.open(out.resolve().as_uri())
        print("تم فتح التقرير في المتصفح")

    if share_port:
        if running_port():
            print(f"خادم الإرسال يعمل بالفعل على المنفذ {share_port}")
        else:
            start_share_server(share_port)
        copy_to_serve(out)
        print_qr(share_url)
    return 0


if __name__ == "__main__":
    sys.exit(main())
