import os
import requests
from config import CONFIG

# ==============================================================================

# 📐 ポジションサイジング

# ==============================================================================

def calculate_position(entry: float, stop: float, usd_jpy: float) -> int:
“””
資金・リスク許容度・エントリー/ストップ価格からポジションサイズを計算。

```
ルール:
    - 1トレードあたりリスク = 総資金 × ACCOUNT_RISK_PCT
    - 1ポジション最大 = 総資金の40%（集中リスク排除）
    - 0株は除外（買えない銘柄はリストから外れる）

Args:
    entry    : エントリー価格（USD）
    stop     : ストップロス価格（USD）
    usd_jpy  : 為替レート

Returns:
    株数 (int)。買えない場合は 0。
"""
try:
    total_usd   = CONFIG["CAPITAL_JPY"] / usd_jpy
    risk_usd    = total_usd * CONFIG["ACCOUNT_RISK_PCT"]
    diff        = abs(entry - stop)
    if diff <= 0:
        return 0

    shares_risk = int(risk_usd / diff)            # リスクベース
    shares_cap  = int((total_usd * 0.4) / entry)  # 集中リスク上限
    return max(0, min(shares_risk, shares_cap))

except:
    return 0
```

# ==============================================================================

# 📲 LINE通知

# ==============================================================================

def send_line(message: str) -> None:
“””
LINE Messaging API へプッシュ通知を送信。

```
環境変数 LINE_CHANNEL_ACCESS_TOKEN / LINE_USER_ID が未設定の場合は何もしない。
4000文字を超えるメッセージは自動分割。
"""
token   = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "").strip()
user_id = os.getenv("LINE_USER_ID", "").strip()

if not token or not user_id:
    return

headers = {
    "Authorization": f"Bearer {token}",
    "Content-Type":  "application/json",
}

for part in [message[i:i + 4000] for i in range(0, len(message), 4000)]:
    try:
        requests.post(
            "https://api.line.me/v2/bot/message/push",
            headers=headers,
            json={"to": user_id, "messages": [{"type": "text", "text": part}]},
            timeout=15,
        )
    except:
        pass
```