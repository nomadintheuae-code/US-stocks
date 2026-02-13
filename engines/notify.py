import os
import requests

from config import config

# ==============================================================================
# 📐 ポジションサイジング
# ==============================================================================

def calculate_position(entry: float, stop: float, usd_jpy: float) -> int:
    """
    資金・リスク許容度・エントリー/ストップ価格からポジションサイズを計算。

    ルール:
        - 1トレードあたりリスク = 総資金 × ACCOUNT_RISK_PCT
        - 1ポジション最大 = 総資金の40%（集中リスク排除）
        - 0株は除外（買えない銘柄はリストから外れる）

    Args:
        entry    : エントリー価格（USD）
        stop     : ストップロス価格（USD）
        usd_jpy  : 為替レート（JPY/USD）

    Returns:
        株数 (int)。買えない場合は 0。
    """
    try:
        if usd_jpy <= 0:
            return 0

        total_usd = CONFIG["CAPITAL_JPY"] / usd_jpy
        risk_usd = total_usd * CONFIG.get("ACCOUNT_RISK_PCT", 0.01)  # デフォルト1%

        diff = abs(entry - stop)
        if diff <= 0:
            return 0

        # リスク許容額に基づく最大株数
        shares_by_risk = int(risk_usd / diff)

        # 1ポジション上限（総資金の40%）
        max_position_usd = total_usd * 0.40
        shares_by_cap = int(max_position_usd / entry)

        # 両方の制約を満たす（小さい方）
        shares = min(shares_by_risk, shares_by_cap)

        return max(0, shares)

    except Exception:
        return 0


# ==============================================================================
# 📲 LINE通知
# ==============================================================================

def send_line(message: str) -> None:
    """
    LINE Messaging API へプッシュ通知を送信。

    環境変数 LINE_CHANNEL_ACCESS_TOKEN / LINE_USER_ID が未設定の場合は何もしない。
    4000文字を超えるメッセージは自動分割して送信。
    """
    token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "").strip()
    user_id = os.getenv("LINE_USER_ID", "").strip()

    if not token or not user_id:
        print("LINE通知スキップ: トークンまたはユーザーIDが設定されていません")
        return

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    # LINEの1メッセージ上限は4000文字 → 分割送信
    chunk_size = 4000
    for i in range(0, len(message), chunk_size):
        part = message[i : i + chunk_size]

        payload = {
            "to": user_id,
            "messages": [{"type": "text", "text": part}],
        }

        try:
            response = requests.post(
                "https://api.line.me/v2/bot/message/push",
                headers=headers,
                json=payload,
                timeout=15,
            )
            response.raise_for_status()  # 4xx/5xxで例外を上げる

        except requests.RequestException as e:
            # 本番ではログ出力推奨（ここでは黙って無視）
            print(f"LINE通知失敗: {e}")
            continue