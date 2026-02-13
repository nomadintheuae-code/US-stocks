“””
engines/analysis.py — テクニカル分析エンジン

- VCPAnalyzer       : Volatility Contraction Pattern スコアリング (0-100)
- RSAnalyzer        : IBD方式 RSパーセンタイルランキング
- StrategyValidator : 250日ウォークフォワードバックテスト
  “””

import pandas as pd
import numpy as np

from config import CONFIG

# ==============================================================================

# 🎯 VCPAnalyzer

# ==============================================================================

class VCPAnalyzer:
“””
Mark Minervini の VCP メソドロジーに基づくスコアリング。

```
採点基準:
    Tightness  (40pt) — 直近10日の値幅収縮
    Volume     (30pt) — 出来高ドライアップ（MA50比）
    MA Align   (30pt) — Price > MA50 > MA200
"""

@staticmethod
def calculate(df: pd.DataFrame) -> dict:
    """
    Returns:
        {
            "score": int,        # 0-100
            "atr": float,        # ATR(14)
            "signals": list,     # 検出シグナル文字列リスト
            "is_dryup": bool,    # 出来高ドライアップフラグ
            "range_pct": float,  # 10日値幅率
            "vol_ratio": float,  # 直近出来高 / MA50
        }
    """
    try:
        close  = df["Close"]
        high   = df["High"]
        low    = df["Low"]
        volume = df["Volume"]

        # ATR(14)
        tr = pd.concat([
            high - low,
            (high - close.shift()).abs(),
            (low  - close.shift()).abs(),
        ], axis=1).max(axis=1)
        atr = float(tr.rolling(14).mean().iloc[-1])

        if pd.isna(atr) or atr <= 0:
            return _empty_vcp()

        # ── 1. Tightness (40pt) ─────────────────────────────────
        h10 = float(high.iloc[-10:].max())
        l10 = float(low.iloc[-10:].min())
        range_pct   = (h10 - l10) / h10
        tight_score = 40 if range_pct <= 0.05 else int(40 * (1 - (range_pct - 0.05) / 0.10))
        tight_score = max(0, min(40, tight_score))

        # ── 2. Volume Dry-Up (30pt) ──────────────────────────────
        vol_ma    = float(volume.rolling(50).mean().iloc[-1])
        vol_ratio = float(volume.iloc[-1] / vol_ma) if vol_ma > 0 else 1.0
        is_dryup  = vol_ratio < 0.7
        vol_score = 30 if is_dryup else (15 if vol_ratio < 1.1 else 0)

        # ── 3. MA Alignment (30pt) ───────────────────────────────
        ma50  = float(close.rolling(50).mean().iloc[-1])
        ma200 = float(close.rolling(200).mean().iloc[-1])
        price = float(close.iloc[-1])
        trend_score = (
            (10 if price > ma50  else 0) +
            (10 if ma50  > ma200 else 0) +
            (10 if price > ma200 else 0)
        )

        signals = []
        if range_pct   < 0.06:  signals.append("Extreme Contraction")
        if is_dryup:            signals.append("Volume Dry-Up")
        if trend_score == 30:   signals.append("MA Aligned")

        return {
            "score":     int(max(0, tight_score + vol_score + trend_score)),
            "atr":       atr,
            "signals":   signals,
            "is_dryup":  is_dryup,
            "range_pct": round(range_pct, 4),
            "vol_ratio": round(vol_ratio, 2),
        }

    except:
        return _empty_vcp()
```

def _empty_vcp() -> dict:
return {“score”: 0, “atr”: 0, “signals”: [], “is_dryup”: False, “range_pct”: 0, “vol_ratio”: 1}

# ==============================================================================

# 📈 RSAnalyzer

# ==============================================================================

class RSAnalyzer:
“””
IBD方式の RS Rating をパーセンタイルランキングで実装。

```
加重式: (12m × 0.4) + (6m × 0.2) + (3m × 0.2) + (1m × 0.2)
全ユニバースに対してパーセンタイル順位（1-99）を割り当てる。
"""

@staticmethod
def get_raw_score(df: pd.DataFrame) -> float:
    """ユニバース全体でソートするための生スコアを返す。"""
    try:
        c = df["Close"]
        r12 = (c.iloc[-1] / c.iloc[-252] - 1) if len(c) >= 252 else (c.iloc[-1] / c.iloc[0] - 1)
        r6  = (c.iloc[-1] / c.iloc[-126] - 1) if len(c) >= 126 else (c.iloc[-1] / c.iloc[0] - 1)
        r3  = (c.iloc[-1] / c.iloc[-63]  - 1) if len(c) >= 63  else (c.iloc[-1] / c.iloc[0] - 1)
        r1  = (c.iloc[-1] / c.iloc[-21]  - 1) if len(c) >= 21  else (c.iloc[-1] / c.iloc[0] - 1)
        return (r12 * 0.4) + (r6 * 0.2) + (r3 * 0.2) + (r1 * 0.2)
    except:
        return -999.0

@staticmethod
def assign_percentiles(raw_list: list[dict]) -> list[dict]:
    """
    raw_rs でソートしてパーセンタイル rank (1-99) を割り当てる。

    Args:
        raw_list: [{"ticker": str, "df": DataFrame, "raw_rs": float}, ...]
    Returns:
        同リストに "rs_rating": int を追加して返す
    """
    raw_list.sort(key=lambda x: x["raw_rs"])
    total = len(raw_list)
    for i, item in enumerate(raw_list):
        item["rs_rating"] = int(((i + 1) / total) * 99)
    return raw_list
```

# ==============================================================================

# 🔬 StrategyValidator

# ==============================================================================

class StrategyValidator:
“””
250日ウォークフォワードバックテスト。

```
エントリー条件: 直近20日ピボット突破 かつ MA50 上
エグジット:     ATR × STOP_LOSS_ATR の損切り または R倍数達成
最終日未決済:  含み益/損を R倍数換算でカウント（v3.3.1 コアロジック）

Returns:
    profit_factor (float) : 利益合計 / 損失合計
"""

@staticmethod
def run(df: pd.DataFrame) -> float:
    try:
        if len(df) < 200:
            return 1.0

        close = df["Close"]
        high  = df["High"]
        low   = df["Low"]

        tr = pd.concat([
            high - low,
            (high - close.shift()).abs(),
            (low  - close.shift()).abs(),
        ], axis=1).max(axis=1)
        atr = tr.rolling(14).mean()

        trades: list[float] = []
        in_pos  = False
        entry_p = 0.0
        stop_p  = 0.0
        target_mult = CONFIG["TARGET_R_MULTIPLE"]
        stop_mult   = CONFIG["STOP_LOSS_ATR"]

        start = max(50, len(df) - 250)
        for i in range(start, len(df)):
            if in_pos:
                # 損切り
                if float(low.iloc[i]) <= stop_p:
                    trades.append(-1.0)
                    in_pos = False
                # 利確
                elif float(high.iloc[i]) >= entry_p + (entry_p - stop_p) * target_mult:
                    trades.append(target_mult)
                    in_pos = False
                # 最終日 — 含み益/損を R換算で記録
                elif i == len(df) - 1:
                    risk = entry_p - stop_p
                    if risk > 0:
                        trades.append(float((float(close.iloc[i]) - entry_p) / risk))
                    in_pos = False
            else:
                pivot = float(high.iloc[i - 20:i].max())
                ma50  = float(close.rolling(50).mean().iloc[i])
                if float(close.iloc[i]) > pivot and float(close.iloc[i]) > ma50:
                    in_pos  = True
                    entry_p = float(close.iloc[i])
                    stop_p  = entry_p - float(atr.iloc[i]) * stop_mult

        if not trades:
            return 1.0

        pos = sum(t for t in trades if t > 0)
        neg = abs(sum(t for t in trades if t < 0))
        pf  = pos / neg if neg > 0 else (5.0 if pos > 0 else 1.0)
        return round(float(min(10.0, pf)), 2)

    except:
        return 1.0
```