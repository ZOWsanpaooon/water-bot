"""
水分管理Bot 単体・統合テスト
"""

import os
import sys
import tempfile
import unittest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from src.models import UserSetting, WeatherInfo
from src.db import WaterDatabase
from src.calculator import WaterCalculator
from src.weather import weather_service
from src.parser import parse_water_message
from src.ui import UserProfileModal


class TestWaterBotIndependent(unittest.TestCase):
    def setUp(self):
        self.temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        self.temp_file.close()
        self.db = WaterDatabase(db_path=self.temp_file.name)

    def tearDown(self):
        try:
            if os.path.exists(self.temp_file.name):
                os.remove(self.temp_file.name)
        except Exception:
            pass

    def test_parser(self):
        self.assertEqual(parse_water_message('10ゴク', 25), (250, 10))
        self.assertEqual(parse_water_message('+250ml', 25), (250, 10))
        self.assertEqual(parse_water_message('300'), (300, None))
        self.assertEqual(parse_water_message('一口', 25), (25, 1))
        self.assertEqual(parse_water_message('コップ1杯', 25), (200, 8))

    def test_db_and_calculator(self):
        user = self.db.get_or_create_user('u1', 'ゆうと')
        user.gender = 'male'
        user.age = 25
        user.weight_kg = 66.0
        user.height_cm = 165.0
        user.activity_level = 'medium'
        self.db.save_user(user)

        prog = self.db.get_daily_progress('u1')
        self.assertGreaterEqual(prog.goal_ml, 1800)
        self.assertLessEqual(prog.goal_ml, 2300)
        self.assertIsNotNone(prog.recommendation)

    def test_weather(self):
        w = weather_service.get_weather_sync()
        self.assertIsNotNone(w)
        self.assertGreater(w.current_temp, -50.0)

    def test_profile_modal_parser(self):
        age, h, w, gulp = UserProfileModal.parse_body_stats('20 160 60 20', 25, 165, 66, 25)
        self.assertEqual(age, 20)
        self.assertEqual(h, 160.0)
        self.assertEqual(w, 60.0)
        self.assertEqual(gulp, 20)
        self.assertEqual(UserProfileModal.parse_activity('2'), 'medium')
        self.assertEqual(UserProfileModal.parse_bedtime('03:30'), '03:30')

    def test_jst_models(self):
        from src.models import JST, get_current_jst_time
        now = get_current_jst_time()
        self.assertIsNotNone(now.tzinfo)
        self.assertEqual(now.tzinfo.utcoffset(now).total_seconds(), 9 * 3600)

    def test_wmo_weather_map(self):
        from src.weather import WMO_WEATHER_MAP
        self.assertIn(45, WMO_WEATHER_MAP)
        self.assertIn(48, WMO_WEATHER_MAP)
        self.assertEqual(WMO_WEATHER_MAP[45], "霧 🌫️")
        self.assertEqual(WMO_WEATHER_MAP[48], "濃霧 🌫️")
        self.assertEqual(WMO_WEATHER_MAP[80], "にわか雨 🌦️")

    def test_db_get_logs_since_and_analytics(self):
        from datetime import datetime, timedelta
        from src.models import get_current_jst_time
        from src.analytics import WaterAnalytics

        user = self.db.get_or_create_user('u2', 'れん')
        now = get_current_jst_time()
        self.db.add_log('u2', 200, gulp_count=8, recorded_at=now, source='discord_channel')
        self.db.add_log('u2', 300, gulp_count=12, recorded_at=now - timedelta(minutes=30), source='apple_watch')

        since_dt = now - timedelta(hours=1)
        logs = self.db.get_logs_since('u2', since_dt)
        self.assertEqual(len(logs), 2)

        analytics = WaterAnalytics(self.db)
        stats = analytics.get_comprehensive_stats('u2')
        self.assertEqual(stats['today_total'], 500)
        self.assertEqual(stats['avg_per_drink'], 250)

    def test_panel_source_badges(self):
        from src.panel import build_history_embed
        from src.models import get_current_jst_time
        user = self.db.get_or_create_user('u3', 'テスト')
        now = get_current_jst_time()
        self.db.add_log('u3', 250, recorded_at=now, source='apple_watch')
        self.db.add_log('u3', 100, recorded_at=now, source='discord_channel')

        prog = self.db.get_daily_progress('u3')
        embed = build_history_embed(prog)
        desc = embed.description
        self.assertIn("[⌚Watch]", desc)
        self.assertIn("[💬Ch]", desc)


if __name__ == '__main__':
    unittest.main()