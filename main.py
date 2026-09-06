"""
水分管理Bot (Water Bot) - 独立稼働エントリポイント
FadeHost / 24時間クラウド稼働対応
"""

import sys
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from src.bot import run_water_bot

if __name__ == "__main__":
    run_water_bot()