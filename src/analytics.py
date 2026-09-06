"""
水分摂取パターン学習・統計分析モジュール
"""

from collections import defaultdict
from datetime import timedelta
from typing import Dict, List
from src.models import JST, get_current_jst_time, WaterLog


class WaterAnalytics:
    def __init__(self, db):
        self.db = db

    def get_comprehensive_stats(self, user_id: str) -> Dict:
        user = self.db.get_user(user_id)
        if not user:
            return {
                "today_total": 0,
                "yesterday_total": 0,
                "avg_7days": 0,
                "avg_30days": 0,
                "avg_per_drink": 200,
                "peak_hours": [],
                "achievement_rate_7d": 0.0,
                "achievement_rate_30d": 0.0,
            }

        now = get_current_jst_time()
        today_key = self.db.calculate_date_key(now, user.reset_time)
        yesterday_dt = now - timedelta(days=1)
        yesterday_key = self.db.calculate_date_key(yesterday_dt, user.reset_time)

        today_progress = self.db.get_daily_progress(user_id, date_key=today_key)
        today_total = today_progress.total_ml

        yesterday_logs = self.db.get_daily_logs(user_id, date_key=yesterday_key)
        yesterday_total = sum(log.amount_ml for log in yesterday_logs)

        stats_7d = self.db.get_statistics(user_id, days=7)
        avg_7d = stats_7d.get("average_ml", 0)
        rate_7d = stats_7d.get("achievement_rate", 0.0)

        stats_30d = self.db.get_statistics(user_id, days=30)
        avg_30d = stats_30d.get("average_ml", 0)
        rate_30d = stats_30d.get("achievement_rate", 0.0)

        since_dt = now - timedelta(days=30)
        recent_logs = self.db.get_logs_since(user_id, since_dt)
        avg_per_drink = int(sum(l.amount_ml for l in recent_logs) / len(recent_logs)) if recent_logs else 200

        hour_counts = defaultdict(int)
        for l in recent_logs:
            hour_counts[l.recorded_at.hour] += 1

        sorted_hours = sorted(hour_counts.items(), key=lambda x: x[1], reverse=True)
        peak_hours = [h for h, cnt in sorted_hours[:3] if cnt >= 2]

        return {
            "today_total": today_total,
            "yesterday_total": yesterday_total,
            "avg_7days": avg_7d,
            "avg_30days": avg_30d,
            "avg_per_drink": avg_per_drink,
            "peak_hours": peak_hours,
            "achievement_rate_7d": rate_7d,
            "achievement_rate_30d": rate_30d,
            "total_logs_30d": len(recent_logs),
        }