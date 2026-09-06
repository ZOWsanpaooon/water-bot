"""
パーソナル水分ナビゲーション計算エンジン
"""

from datetime import datetime, time, timedelta, timezone
from typing import Optional
from src.models import JST, get_current_jst_time, UserSetting, WeatherInfo, WaterRecommendation, DailyProgress


class WaterCalculator:
    """パーソナル水分計算＆ナビゲーションエンジン"""

    @staticmethod
    def calculate_daily_recommended_goal(
        user: UserSetting,
        weather: Optional[WeatherInfo] = None,
        avg_7days: Optional[int] = None
    ) -> int:
        """
        1日のパーソナル推奨「飲料水」目標量 (ml) を算出
        ※食事由来の水分（約800〜1,000ml）や体内代謝水を除いた、純粋に「飲むべき水」の適正値を計算。
        """
        age = user.age or 25
        weight = user.weight_kg or 66.0

        if age < 30:
            ml_per_kg = 25.0
        elif age < 55:
            ml_per_kg = 23.5
        elif age < 65:
            ml_per_kg = 22.0
        else:
            ml_per_kg = 20.5

        base_ml = weight * ml_per_kg

        if user.gender == "male":
            base_ml += 100.0

        if user.height_cm:
            height_diff = user.height_cm - 165.0
            base_ml += height_diff * 2.0

        activity = (user.activity_level or "medium").lower()
        if activity == "low":
            activity_multiplier = 1.0
        elif activity == "high":
            activity_multiplier = 1.30
        else:
            activity_multiplier = 1.15

        target_ml = base_ml * activity_multiplier

        if weather:
            eff_temp = max(weather.apparent_temp, weather.max_temp)
            if eff_temp >= 35.0:
                target_ml += 400.0
            elif eff_temp >= 30.0:
                target_ml += 250.0
            elif eff_temp >= 26.0:
                target_ml += 120.0
            elif eff_temp >= 22.0:
                target_ml += 30.0
            elif eff_temp < 10.0:
                target_ml -= 50.0

            if 0 < weather.humidity < 40:
                target_ml += 80.0

        if avg_7days and avg_7days > 500:
            target_ml = (target_ml * 0.75) + (avg_7days * 0.25)

        final_goal = int(round(target_ml / 50.0) * 50)
        return max(1200, min(2600, final_goal))

    @staticmethod
    def calculate_next_recommendation(
        user: UserSetting,
        progress: DailyProgress,
        weather: Optional[WeatherInfo] = None,
        peak_hours: Optional[list] = None
    ) -> WaterRecommendation:
        """
        現在の進捗、時刻、就寝時間、直前飲水から
        「次に飲む量」「次に飲むタイミング」をリアルタイム算出
        """
        now = get_current_jst_time()
        gulp_ml = user.gulp_ml or 25

        daily_goal = WaterCalculator.calculate_daily_recommended_goal(user, weather)
        if not user.auto_goal_enabled and user.daily_goal_ml > 0:
            daily_goal = user.daily_goal_ml

        remaining_ml = max(0, daily_goal - progress.total_ml)

        bedtime_str = user.bedtime or "24:00"
        try:
            b_hour, b_min = map(int, bedtime_str.split(":"))
            if b_hour == 24:
                b_hour = 0
            bedtime_t = time(b_hour, b_min)
        except Exception:
            bedtime_t = time(0, 0)

        bed_dt = datetime.combine(now.date(), bedtime_t, tzinfo=JST)
        if bedtime_t < time(6, 0) and now.time() >= time(6, 0):
            bed_dt += timedelta(days=1)

        minutes_to_bed = (bed_dt - now).total_seconds() / 60.0
        is_bedtime_near = 0 <= minutes_to_bed <= 120
        is_after_bedtime = minutes_to_bed < 0 and (now.time() < time(6, 0) or now.time() >= time(22, 0))

        last_log = progress.logs[-1] if progress.logs else None
        minutes_since_last_drink = None
        last_amount = 0
        if last_log:
            last_dt = last_log.recorded_at
            if last_dt.tzinfo is None:
                last_dt = last_dt.replace(tzinfo=JST)
            minutes_since_last_drink = (now - last_dt).total_seconds() / 60.0
            last_amount = last_log.amount_ml

        if progress.total_ml >= daily_goal:
            rec_ml = 150
            status_text = "🎉 今日の目標達成済み！渇きに合わせて少量補給"
        elif is_after_bedtime:
            rec_ml = 100
            status_text = "🌙 就寝時間帯です。睡眠前の潤い補給（コップ半分）"
        elif is_bedtime_near:
            rec_ml = min(150, max(100, int(round(remaining_ml / 3.0 / 25.0) * 25)))
            status_text = "🌙 就寝前の水分補給（睡眠を妨げない控えめな量）"
        else:
            if remaining_ml <= 200:
                rec_ml = remaining_ml
            elif remaining_ml <= 500:
                rec_ml = 200
            else:
                eff_temp = weather.apparent_temp if weather else 20.0
                if eff_temp >= 28.0 or user.activity_level == "high":
                    rec_ml = 250
                else:
                    rec_ml = 200

            rec_ml = max(150, min(300, int(round(rec_ml / float(gulp_ml)) * gulp_ml)))
            status_text = "💧 こまめなパーソナル水分補給"

        rec_gulps = max(1, int(round(rec_ml / float(gulp_ml))))

        if last_amount >= 300:
            min_interval_mins = 75
        elif last_amount >= 200:
            min_interval_mins = 60
        else:
            min_interval_mins = 45

        if weather and weather.apparent_temp >= 28.0:
            min_interval_mins = max(35, min_interval_mins - 15)

        if minutes_since_last_drink is not None:
            if minutes_since_last_drink >= min_interval_mins:
                next_dt = now + timedelta(minutes=5)
            else:
                remain_interval = min_interval_mins - minutes_since_last_drink
                next_dt = now + timedelta(minutes=remain_interval)
        else:
            next_dt = now + timedelta(minutes=10)

        rounded_minute = int(round(next_dt.minute / 5.0) * 5)
        if rounded_minute == 60:
            next_dt = next_dt.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        else:
            next_dt = next_dt.replace(minute=rounded_minute, second=0, microsecond=0)

        time_diff_mins = (next_dt - now).total_seconds() / 60.0
        if time_diff_mins <= 5:
            rec_time_str = "今すぐ"
        else:
            rec_time_str = f"{next_dt.strftime('%H:%M')}頃"

        if weather:
            weather_sum = f"西蒲田 {weather.current_temp:.1f}℃ (体感{weather.apparent_temp:.1f}℃) {weather.weather_text}"
        else:
            weather_sum = "西蒲田 (気象連携中)"

        return WaterRecommendation(
            user_id=user.user_id,
            recommended_ml=rec_ml,
            recommended_gulps=rec_gulps,
            recommended_time_str=rec_time_str,
            recommended_dt=next_dt,
            status_summary=status_text,
            daily_recommended_goal_ml=daily_goal,
            weather_summary=weather_sum,
            is_bedtime_near=is_bedtime_near or is_after_bedtime
        )