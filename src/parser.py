"""
水分テキストメッセージ解析モジュール（あいまい自然言語対応）
"""

import re
import unicodedata
from typing import Optional, Tuple

KANJI_NUM_MAP = {
    "一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
    "六": 6, "七": 7, "八": 8, "九": 9, "十": 10
}


def parse_water_message(content: str, user_gulp_ml: int = 25) -> Optional[Tuple[int, Optional[int]]]:
    """
    ユーザーのチャットメッセージから水分摂取量を柔軟・あいまいに解析する。
    戻り値: (amount_ml, gulp_count) または None
    """
    if not content:
        return None

    # 全角英数・記号を半角に正規化
    text = unicodedata.normalize("NFKC", content).strip().lower()

    # 1. 漢数字を数字に簡易変換 (例: 一口 -> 1口, 二杯 -> 2杯)
    for k, v in KANJI_NUM_MAP.items():
        text = re.sub(f"{k}(口|ごく|ゴク|杯|本)", f"{v}\\1", text)

    # 2. 「一口」「ちょっと」「少し」のニュアンス
    if re.search(r"(ひとくち|一口|ちょっと|すこし|少し)(飲んだ|のんだ|のみました)?", text):
        if not re.search(r"\d+", text):
            return user_gulp_ml, 1

    # 3. 「○ごく」「○口」「○gulp」表現 (例: 3ごく, 5ゴク飲んだ, 2口)
    gulp_match = re.search(r"(\d+)\s*(ゴク|ごく|口|くち|goku|gulp)", text)
    if gulp_match:
        count = int(gulp_match.group(1))
        if 1 <= count <= 50:
            return count * user_gulp_ml, count

    # 4. 「コップ○杯」「グラス○杯」「マグカップ○杯」表現 (1杯 = 200ml換算)
    cup_match = re.search(r"(?:コップ|グラス|マグカップ|カップ)?\s*(\d+)\s*(?:杯|はい|ハイ)", text)
    if cup_match:
        cups = int(cup_match.group(1))
        if 1 <= cups <= 10:
            amount = cups * 200
            gulps = int(amount / user_gulp_ml)
            return amount, gulps

    # 5. 「ペットボトル○本」表現 (1本 = 500ml換算)
    bottle_match = re.search(r"ペットボトル\s*(\d+)\s*(?:本|ほん|ポン)", text)
    if bottle_match:
        bottles = int(bottle_match.group(1))
        if 1 <= bottles <= 5:
            amount = bottles * 500
            return amount, int(amount / user_gulp_ml)

    # 6. 「ペットボトル半分」
    if "ペットボトル" in text and ("半分" in text or "はんぶん" in text):
        return 250, int(250 / user_gulp_ml)

    # 7. 「○○ml」「○○ミリ」「○○cc」表現 (例: 250ml, +200, 150ミリ飲んだ)
    ml_match = re.search(r"\+?(\d+)\s*(ml|ミリ|cc|㏄)", text)
    if ml_match:
        amount = int(ml_match.group(1))
        if 10 <= amount <= 3000:
            gulps = int(amount / user_gulp_ml) if user_gulp_ml > 0 else None
            return amount, gulps

    # 8. 「水○○」「お茶○○」「アクエ○○」などの飲料名＋数字 (例: 水200, お茶300飲んだ)
    drink_match = re.search(r"(?:水|お水|白湯|麦茶|お茶|ポカリ|アクエリ|アクエリアス|水分|麦茶)\s*[:：]?\s*(\d+)", text)
    if drink_match:
        amount = int(drink_match.group(1))
        if 10 <= amount <= 3000:
            return amount, int(amount / user_gulp_ml) if user_gulp_ml > 0 else None

    # 9. 純粋な数値のみの入力 (例: 100, 250, +300)
    # ※時刻（12:30）や年号（2026）、電話番号等の誤爆を防ぐ
    cleaned = re.sub(r"^[+＋]?\s*", "", text)
    cleaned = re.sub(r"\s*(飲んだ|のんだ|飲みました|のみました|摂取|完了|です|！|!)*$", "", cleaned)
    if re.fullmatch(r"\d+", cleaned):
        val = int(cleaned)
        # 1〜9の小さい数字なら「○ゴク」と解釈
        if 1 <= val <= 9:
            return val * user_gulp_ml, val
        # 10〜3000の範囲なら「○ml」と解釈
        if 10 <= val <= 3000:
            return val, None

    return None