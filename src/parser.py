"""
水分テキストメッセージ解析モジュール
"""

import re
from typing import Optional, Tuple


def parse_water_message(content: str, user_gulp_ml: int = 25) -> Optional[Tuple[int, Optional[int]]]:
    text = content.strip().lower()

    gulp_match = re.search(r"(\d+)\s*(ゴク|ごく|goku|gulp)", text)
    if gulp_match:
        count = int(gulp_match.group(1))
        if 1 <= count <= 50:
            return count * user_gulp_ml, count

    ml_match = re.search(r"\+?(\d+)\s*(ml|ミリ|㏄|cc)", text)
    if ml_match:
        amount = int(ml_match.group(1))
        if 10 <= amount <= 3000:
            return amount, None

    pure_num = re.sub(r"[^\d]", "", text)
    if pure_num and len(text) <= 6:
        val = int(pure_num)
        if 10 <= val <= 3000:
            return val, None

    return None