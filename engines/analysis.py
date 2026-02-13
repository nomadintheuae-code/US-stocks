import pandas as pd
import numpy as np

from config import CONFIG


# ==============================================================================
# 🎯 VCPAnalyzer
# ==============================================================================

class VCPAnalyzer:
    """
    Mark Minervini VCP スコアリング（改良版・総合収縮判定）

    Tightness  (40pt) — 20/30/40日収縮の総合判定
    Volume     (30pt) — 段階的出来高減少
    MA Align   (30pt) — Price > MA50 > MA200
    """

    @staticmethod
    def calculate(df: pd.DataFrame) -> dict:

        try:
            if df is None or len(df) < 80:
                return _empty_vcp()

            close = df["Close"]
            high = df["High"]
            low = df["Low"]
            volume = df["Volume"]

            # ── ATR(14) ─────────────────────────────────────────
            tr = pd.concat([
                high - low,
                (high - close.shift()).abs(),
                (low - close.shift()).abs(),
            ], axis=1).max(axis=1)

            atr = float(tr.rolling(14).mean().iloc[-1])
            if pd.isna(atr) or atr <= 0:
                return _empty_vcp()

            # =====================================================
            # 1️⃣ Tightness（40pt）← ここだけ改良
            # =====================================================
            periods = [20, 30, 40]
            ranges = []

            for p in periods:
                h = float(high.iloc[-p:].max())
                l = float(low.iloc[-p:].min())
                ranges.append((h - l) / h)

            avg_range = float(np.mean(ranges))
            is_contracting = ranges[0] > ranges[1] > ranges[2]

            if is_contracting and avg_range < 0.15:
                tight_score = 40
            elif avg_range < 0.20:
                tight_score = 25
            elif avg_range < 0.25:
                tight_score = 15
            else:
                tight_score = 0

            range_pct = round(ranges[0], 4)  # 表示用は20日

            # =====================================================
            # 2️⃣ Volume（30pt）← 単発ではなく段階減少
            # =====================================================
            v20 = float(volume.iloc[-20:].mean())
            v40 = float(volume.iloc[-40:-20].mean())
            v60 = float(volume.iloc[-60:-40].mean())

            if pd.isna(v20) or pd.isna(v40) or pd.isna(v60):
                return _empty_vcp()

            if v20 < v40 < v60:
                vol_score = 30
                is_dryup = True
            elif v20 < v40:
                vol_score = 20
                is_dryup = True
            else:
                vol_score = 0
                is_dryup = False

            vol_ratio = round(v20 / v60, 2) if v60 > 0 else 1.0

            # =====================================================
            # 3️⃣ MA Alignment（30pt）← 変更なし
            # =====================================================
            ma50 = float(close.rolling(50).mean().iloc[-1])
            ma200 = float(close.rolling(200).mean().iloc[-1])
            price = float(close.iloc[-1])

            trend_score = (
                (10 if price > ma50 else 0) +
                (10 if ma50 > ma200 else 0) +
                (10 if price > ma200 else 0)
            )

            signals = []
            if tight_score == 40:
                signals.append("Multi-Stage Contraction")
            if is_dryup:
                signals.append("Volume Dry-Up")
            if trend_score == 30:
                signals.append("MA Aligned")

            return {
                "score": int(max(0, tight_score + vol_score + trend_score)),
                "atr": atr,
                "signals": signals,
                "is_dryup": is_dryup,
                "range_pct": range_pct,
                "vol_ratio": vol_ratio,
            }

        except Exception:
            return _empty_vcp()


def _empty_vcp() -> dict:
    return {
        "score": 0,
        "atr": 0.0,
        "signals": [],
        "is_dryup": False,
        "range_pct": 0.0,
        "vol_ratio": 1.0
    }


# ==============================================================================
# 📈 RSAnalyzer（変更なし）
# ==============================================================================

class RSAnalyzer:

    @staticmethod
    def get_raw_score(df: pd.DataFrame) -> float:
        try:
            c = df["Close"]
            if len(c) < 21:
                return -999.0

            r12 = (c.iloc[-1] / c.iloc[-252] - 1) if len(c) >= 252 else (c.iloc[-1] / c.iloc[0] - 1)
            r6  = (c.iloc[-1] / c.iloc[-126] - 1) if len(c) >= 126 else (c.iloc[-1] / c.iloc[0] - 1)
            r3  = (c.iloc[-1] / c.iloc[-63]  - 1) if len(c) >= 63  else (c.iloc[-1] / c.iloc[0] - 1)
            r1  = (c.iloc[-1] / c.iloc[-21]  - 1) if len(c) >= 21  else (c.iloc[-1] / c.iloc[0] - 1)

            return (r12 * 0.4) + (r6 * 0.2) + (r3 * 0.2) + (r1 * 0.2)
        except Exception:
            return -999.0

    @staticmethod
    def assign_percentiles(raw_list: list[dict]) -> list[dict]:
        if not raw_list:
            return raw_list

        raw_list.sort(key=lambda x: x["raw_rs"])
        total = len(raw_list)

        for i, item in enumerate(raw_list):
            item["rs_rating"] = int(((i + 1) / total) * 99) + 1

        return raw_list


# ==============================================================================
# 🔬 StrategyValidator（変更なし）
# ==============================================================================

class StrategyValidator:

    @staticmethod
    def run(df: pd.DataFrame) -> float:
        try:
            if len(df) < 200:
                return 1.0

            close = df["Close"]
            high = df["High"]
            low = df["Low"]

            tr = pd.concat([
                high - low,
                (high - close.shift()).abs(),
                (low - close.shift()).abs(),
            ], axis=1).max(axis=1)
            atr = tr.rolling(14).mean()

            trades = []
            in_pos = False
            entry_p = 0.0
            stop_p = 0.0

            target_mult = CONFIG["TARGET_R_MULTIPLE"]
            stop_mult = CONFIG["STOP_LOSS_ATR"]

            start = max(50, len(df) - 250)

            for i in range(start, len(df)):

                if in_pos:
                    if float(low.iloc[i]) <= stop_p:
                        trades.append(-1.0)
                        in_pos = False

                    elif float(high.iloc[i]) >= entry_p + (entry_p - stop_p) * target_mult:
                        trades.append(target_mult)
                        in_pos = False

                    elif i == len(df) - 1:
                        risk = entry_p - stop_p
                        if risk > 0:
                            r = (float(close.iloc[i]) - entry_p) / risk
                            trades.append(r)
                        in_pos = False

                else:
                    if i < 20:
                        continue

                    pivot = float(high.iloc[i - 20:i].max())
                    ma50 = float(close.rolling(50).mean().iloc[i])

                    if (float(close.iloc[i]) > pivot and
                        float(close.iloc[i]) > ma50):

                        in_pos = True
                        entry_p = float(close.iloc[i])
                        stop_p = entry_p - float(atr.iloc[i]) * stop_mult

            if not trades:
                return 1.0

            pos = sum(t for t in trades if t > 0)
            neg = abs(sum(t for t in trades if t < 0))
            pf = pos / neg if neg > 0 else (5.0 if pos > 0 else 1.0)

            return round(min(10.0, float(pf)), 2)

        except Exception:
            return 1.0