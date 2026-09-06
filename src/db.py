"""
水分管理システム データベース管理 (SQLite Storage)
"""

import json
import os
import sqlite3
from datetime import datetime, time, timedelta, timezone
from typing import Dict, List, Optional, Tuple

from src.models import (
    JST, get_current_jst_time,
    ChannelSetting, DailyProgress, UserSetting, WaterLog, WaterRecommendation,
)


class WaterDatabase:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or os.getenv("WATER_DB_PATH", "data/water.db")
        os.makedirs(os.path.dirname(os.path.abspath(self.db_path)), exist_ok=True)
        self._init_tables()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_tables(self) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    daily_goal_ml INTEGER NOT NULL DEFAULT 2000,
                    gulp_ml INTEGER NOT NULL DEFAULT 25,
                    reset_time TEXT NOT NULL DEFAULT '06:00',
                    notification_enabled INTEGER NOT NULL DEFAULT 1,
                    notification_start TEXT NOT NULL DEFAULT '08:00',
                    notification_end TEXT NOT NULL DEFAULT '23:00',
                    notification_interval INTEGER NOT NULL DEFAULT 60,
                    notification_mode TEXT NOT NULL DEFAULT 'dm',
                    presets TEXT NOT NULL DEFAULT '[100, 250, 500]',
                    visibility TEXT NOT NULL DEFAULT 'all',
                    gender TEXT NOT NULL DEFAULT 'male',
                    age INTEGER NOT NULL DEFAULT 25,
                    height_cm REAL NOT NULL DEFAULT 165.0,
                    weight_kg REAL NOT NULL DEFAULT 66.0,
                    bedtime TEXT NOT NULL DEFAULT '24:00',
                    activity_level TEXT NOT NULL DEFAULT 'medium',
                    auto_goal_enabled INTEGER NOT NULL DEFAULT 1
                )
            """)

            cursor.execute("PRAGMA table_info(users)")
            existing_cols = {row["name"] for row in cursor.fetchall()}

            new_columns = [
                ("notification_mode", "TEXT NOT NULL DEFAULT 'dm'"),
                ("gender", "TEXT NOT NULL DEFAULT 'male'"),
                ("age", "INTEGER NOT NULL DEFAULT 25"),
                ("height_cm", "REAL NOT NULL DEFAULT 165.0"),
                ("weight_kg", "REAL NOT NULL DEFAULT 66.0"),
                ("bedtime", "TEXT NOT NULL DEFAULT '24:00'"),
                ("activity_level", "TEXT NOT NULL DEFAULT 'medium'"),
                ("auto_goal_enabled", "INTEGER NOT NULL DEFAULT 1"),
            ]
            for col_name, col_def in new_columns:
                if col_name not in existing_cols:
                    cursor.execute(f"ALTER TABLE users ADD COLUMN {col_name} {col_def}")

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS water_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    amount_ml INTEGER NOT NULL,
                    gulp_count INTEGER,
                    recorded_at TEXT NOT NULL,
                    date_key TEXT NOT NULL,
                    source TEXT NOT NULL DEFAULT 'discord',
                    FOREIGN KEY(user_id) REFERENCES users(user_id)
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS channel_settings (
                    guild_id INTEGER PRIMARY KEY,
                    channel_id INTEGER NOT NULL,
                    message_id INTEGER
                )
            """)

            cursor.execute("CREATE INDEX IF NOT EXISTS idx_water_logs_user_date ON water_logs(user_id, date_key)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_water_logs_recorded_at ON water_logs(recorded_at)")
            self._seed_initial_defaults(cursor)
            conn.commit()

    def _seed_initial_defaults(self, cursor: sqlite3.Cursor) -> None:
        """Render等のエフェメラル環境でも初期プロファイルと前回の水分量が絶対に消えないように自動シード"""
        cursor.execute("SELECT count(*) FROM users WHERE user_id = '1236356506123894937'")
        if cursor.fetchone()[0] == 0:
            cursor.execute("""
                INSERT OR REPLACE INTO users (
                    user_id, name, daily_goal_ml, gulp_ml, reset_time,
                    notification_enabled, notification_start, notification_end,
                    notification_interval, notification_mode, presets, visibility,
                    gender, age, height_cm, weight_kg, bedtime, activity_level, auto_goal_enabled
                ) VALUES (
                    '1236356506123894937', 'ゆうと', 2050, 25, '06:00',
                    1, '08:00', '23:00', 60, 'dm', '[100, 250, 500]', 'all',
                    'male', 25, 165.0, 66.0, '03:30', 'medium', 0
                )
            """)

        cursor.execute("SELECT count(*) FROM users WHERE user_id = '1023600562907926680'")
        if cursor.fetchone()[0] == 0:
            cursor.execute("""
                INSERT OR REPLACE INTO users (
                    user_id, name, daily_goal_ml, gulp_ml, reset_time,
                    notification_enabled, notification_start, notification_end,
                    notification_interval, notification_mode, presets, visibility,
                    gender, age, height_cm, weight_kg, bedtime, activity_level, auto_goal_enabled
                ) VALUES (
                    '1023600562907926680', 'れん', 2050, 20, '06:00',
                    1, '08:00', '23:00', 60, 'dm', '[100, 250, 500]', 'all',
                    'female', 23, 158.0, 48.0, '03:30', 'medium', 0
                )
            """)

        # Supabase連携が完了したため、固定の初期水分ログのシードは行わない（Supabaseから復元）
        pass

    @staticmethod
    def calculate_date_key(dt: datetime, reset_time_str: str = "06:00") -> str:
        try:
            r_hour, r_minute = map(int, reset_time_str.split(":"))
        except Exception:
            r_hour, r_minute = 6, 0

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=JST)
        else:
            dt = dt.astimezone(JST)

        target_time = time(r_hour, r_minute)
        current_time = dt.time()

        if current_time < target_time:
            actual_date = (dt - timedelta(days=1)).date()
        else:
            actual_date = dt.date()

        return actual_date.strftime("%Y-%m-%d")

    def get_user(self, user_id: str) -> Optional[UserSetting]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE user_id = ?", (str(user_id),))
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_user_setting(row)

    def get_or_create_user(self, user_id: str, name: str = "ユーザー") -> UserSetting:
        user = self.get_user(user_id)
        if user:
            if name != "ユーザー" and user.name == "ユーザー":
                user.name = name
                self.save_user(user)
            return user

        new_user = UserSetting(user_id=str(user_id), name=name)
        self.save_user(new_user)
        return new_user

    def save_user(self, user: UserSetting) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            presets_json = json.dumps(user.presets)
            cursor.execute("""
                INSERT INTO users (
                    user_id, name, daily_goal_ml, gulp_ml, reset_time,
                    notification_enabled, notification_start, notification_end,
                    notification_interval, notification_mode, presets, visibility,
                    gender, age, height_cm, weight_kg, bedtime, activity_level, auto_goal_enabled
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    name = excluded.name,
                    daily_goal_ml = excluded.daily_goal_ml,
                    gulp_ml = excluded.gulp_ml,
                    reset_time = excluded.reset_time,
                    notification_enabled = excluded.notification_enabled,
                    notification_start = excluded.notification_start,
                    notification_end = excluded.notification_end,
                    notification_interval = excluded.notification_interval,
                    notification_mode = excluded.notification_mode,
                    presets = excluded.presets,
                    visibility = excluded.visibility,
                    gender = excluded.gender,
                    age = excluded.age,
                    height_cm = excluded.height_cm,
                    weight_kg = excluded.weight_kg,
                    bedtime = excluded.bedtime,
                    activity_level = excluded.activity_level,
                    auto_goal_enabled = excluded.auto_goal_enabled
            """, (
                str(user.user_id),
                user.name,
                user.daily_goal_ml,
                user.gulp_ml,
                user.reset_time,
                1 if user.notification_enabled else 0,
                user.notification_start,
                user.notification_end,
                user.notification_interval,
                user.notification_mode,
                presets_json,
                user.visibility,
                user.gender,
                user.age,
                user.height_cm,
                user.weight_kg,
                user.bedtime,
                user.activity_level,
                1 if user.auto_goal_enabled else 0
            ))
            conn.commit()

    def get_all_users(self) -> List[UserSetting]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users ORDER BY rowid ASC")
            rows = cursor.fetchall()
            return [self._row_to_user_setting(row) for row in rows]

    def _row_to_user_setting(self, row: sqlite3.Row) -> UserSetting:
        try:
            presets = json.loads(row["presets"])
        except Exception:
            presets = [100, 250, 500]

        def _get_val(col, default):
            try:
                v = row[col]
                return v if v is not None else default
            except Exception:
                return default

        return UserSetting(
            user_id=str(row["user_id"]),
            name=row["name"],
            daily_goal_ml=row["daily_goal_ml"],
            gulp_ml=row["gulp_ml"],
            reset_time=row["reset_time"],
            notification_enabled=bool(row["notification_enabled"]),
            notification_start=row["notification_start"],
            notification_end=row["notification_end"],
            notification_interval=row["notification_interval"],
            notification_mode=_get_val("notification_mode", "dm"),
            presets=presets,
            visibility=row["visibility"],
            gender=_get_val("gender", "male"),
            age=_get_val("age", 25),
            height_cm=float(_get_val("height_cm", 165.0)),
            weight_kg=float(_get_val("weight_kg", 66.0)),
            bedtime=_get_val("bedtime", "24:00"),
            activity_level=_get_val("activity_level", "medium"),
            auto_goal_enabled=bool(_get_val("auto_goal_enabled", 1))
        )

    def add_log(
        self,
        user_id: str,
        amount_ml: int,
        gulp_count: Optional[int] = None,
        recorded_at: Optional[datetime] = None,
        source: str = "discord",
        user_name: Optional[str] = None
    ) -> Tuple[WaterLog, DailyProgress]:
        if recorded_at is None:
            recorded_at = get_current_jst_time()
        elif recorded_at.tzinfo is None:
            recorded_at = recorded_at.replace(tzinfo=JST)
        else:
            recorded_at = recorded_at.astimezone(JST)

        user = self.get_or_create_user(user_id, user_name or "ユーザー")
        date_key = self.calculate_date_key(recorded_at, user.reset_time)

        progress_before = self.get_daily_progress(user.user_id, date_key=date_key, target_dt=recorded_at)
        was_achieved_before = progress_before.is_achieved

        iso_str = recorded_at.isoformat()

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO water_logs (user_id, amount_ml, gulp_count, recorded_at, date_key, source)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (str(user_id), amount_ml, gulp_count, iso_str, date_key, source))
            log_id = cursor.lastrowid
            conn.commit()

        new_log = WaterLog(
            id=log_id,
            user_id=str(user_id),
            amount_ml=amount_ml,
            gulp_count=gulp_count,
            recorded_at=recorded_at,
            date_key=date_key,
            source=source
        )

        progress_after = self.get_daily_progress(user.user_id, date_key=date_key, target_dt=recorded_at)
        progress_after.is_first_achievement = (not was_achieved_before) and progress_after.is_achieved

        return new_log, progress_after

    def get_last_log(self, user_id: str, date_key: Optional[str] = None, target_dt: Optional[datetime] = None) -> Optional[WaterLog]:
        user = self.get_user(user_id)
        if not user:
            return None

        if date_key is None:
            dt = target_dt or get_current_jst_time()
            date_key = self.calculate_date_key(dt, user.reset_time)

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM water_logs
                WHERE user_id = ? AND date_key = ?
                ORDER BY id DESC LIMIT 1
            """, (str(user_id), date_key))
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_water_log(row)

    def delete_last_log(self, user_id: str, date_key: Optional[str] = None, target_dt: Optional[datetime] = None) -> Optional[Tuple[WaterLog, DailyProgress]]:
        last_log = self.get_last_log(user_id, date_key=date_key, target_dt=target_dt)
        if not last_log or last_log.id is None:
            return None

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM water_logs WHERE id = ?", (last_log.id,))
            conn.commit()

        user = self.get_user(user_id)
        current_date_key = date_key or (self.calculate_date_key(target_dt or get_current_jst_time(), user.reset_time if user else "06:00"))
        new_progress = self.get_daily_progress(user_id, date_key=current_date_key)
        return last_log, new_progress

    def get_daily_logs(self, user_id: str, date_key: Optional[str] = None, target_dt: Optional[datetime] = None) -> List[WaterLog]:
        user = self.get_user(user_id)
        if date_key is None:
            dt = target_dt or get_current_jst_time()
            reset_time = user.reset_time if user else "06:00"
            date_key = self.calculate_date_key(dt, reset_time)

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM water_logs
                WHERE user_id = ? AND date_key = ?
                ORDER BY recorded_at ASC, id ASC
            """, (str(user_id), date_key))
            rows = cursor.fetchall()
            return [self._row_to_water_log(row) for row in rows]

    def get_daily_progress(
        self,
        user_id: str,
        date_key: Optional[str] = None,
        target_dt: Optional[datetime] = None,
        weather=None
    ) -> DailyProgress:
        from src.weather import weather_service
        from src.calculator import WaterCalculator

        user = self.get_or_create_user(user_id)
        if date_key is None:
            dt = target_dt or get_current_jst_time()
            date_key = self.calculate_date_key(dt, user.reset_time)

        logs = self.get_daily_logs(user_id, date_key=date_key)
        total_ml = sum(log.amount_ml for log in logs)

        w_info = weather or weather_service.get_weather_sync()

        if user.auto_goal_enabled:
            goal_ml = WaterCalculator.calculate_daily_recommended_goal(user, w_info)
        else:
            goal_ml = user.daily_goal_ml

        remaining_ml = max(0, goal_ml - total_ml)
        percentage = (total_ml / goal_ml * 100.0) if goal_ml > 0 else 100.0
        is_achieved = total_ml >= goal_ml
        last_recorded_at = logs[-1].recorded_at if logs else None

        base_progress = DailyProgress(
            user_id=str(user_id),
            name=user.name,
            date_key=date_key,
            total_ml=total_ml,
            goal_ml=goal_ml,
            remaining_ml=remaining_ml,
            percentage=percentage,
            is_achieved=is_achieved,
            is_first_achievement=False,
            last_recorded_at=last_recorded_at,
            logs=logs
        )

        recommendation = WaterCalculator.calculate_next_recommendation(
            user=user,
            progress=base_progress,
            weather=w_info
        )
        base_progress.recommendation = recommendation

        return base_progress

    def get_all_progress(self, target_dt: Optional[datetime] = None) -> List[DailyProgress]:
        users = self.get_all_users()
        return [self.get_daily_progress(u.user_id, target_dt=target_dt) for u in users]

    def get_statistics(self, user_id: str, days: int = 7) -> Dict:
        user = self.get_user(user_id)
        if not user:
            return {}

        now = get_current_jst_time()
        date_keys = []
        for i in range(days):
            d = now - timedelta(days=i)
            dk = self.calculate_date_key(d, user.reset_time)
            if dk not in date_keys:
                date_keys.append(dk)

        date_keys.sort()

        with self._get_connection() as conn:
            cursor = conn.cursor()
            placeholders = ",".join("?" for _ in date_keys)
            cursor.execute(f"""
                SELECT date_key, SUM(amount_ml) as total_ml, COUNT(*) as record_count
                FROM water_logs
                WHERE user_id = ? AND date_key IN ({placeholders})
                GROUP BY date_key
            """, [str(user_id)] + date_keys)
            rows = cursor.fetchall()
            day_map = {row["date_key"]: row["total_ml"] for row in rows}

        totals = [day_map.get(dk, 0) for dk in date_keys]
        goal = user.daily_goal_ml
        achieved_days = sum(1 for t in totals if t >= goal)
        total_sum = sum(totals)
        avg_ml = (total_sum / len(totals)) if totals else 0
        max_ml = max(totals) if totals else 0
        min_ml = min(totals) if totals else 0
        achievement_rate = (achieved_days / len(totals) * 100.0) if totals else 0.0

        return {
            "days": len(date_keys),
            "date_keys": date_keys,
            "totals": totals,
            "average_ml": int(avg_ml),
            "goal_ml": goal,
            "achieved_days": achieved_days,
            "total_days": len(date_keys),
            "achievement_rate": achievement_rate,
            "max_ml": max_ml,
            "min_ml": min_ml
        }

    def _row_to_water_log(self, row: sqlite3.Row) -> WaterLog:
        rec_str = row["recorded_at"]
        try:
            rec_dt = datetime.fromisoformat(rec_str)
            if rec_dt.tzinfo is None:
                rec_dt = rec_dt.replace(tzinfo=JST)
        except Exception:
            rec_dt = get_current_jst_time()

        return WaterLog(
            id=row["id"],
            user_id=str(row["user_id"]),
            amount_ml=row["amount_ml"],
            gulp_count=row["gulp_count"],
            recorded_at=rec_dt,
            date_key=row["date_key"],
            source=row["source"]
        )

    def get_logs_since(self, user_id: str, since_dt: datetime) -> List[WaterLog]:
        """指定日時以降の全ログを取得する（analytics等の外部モジュール向けパブリックAPI）"""
        if since_dt.tzinfo is None:
            since_dt = since_dt.replace(tzinfo=JST)
        since_iso = since_dt.isoformat()

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM water_logs
                WHERE user_id = ? AND recorded_at >= ?
                ORDER BY recorded_at ASC
            """, (str(user_id), since_iso))
            rows = cursor.fetchall()
            return [self._row_to_water_log(row) for row in rows]

    def save_channel_setting(self, guild_id: int, channel_id: int, message_id: Optional[int] = None) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO channel_settings (guild_id, channel_id, message_id)
                VALUES (?, ?, ?)
                ON CONFLICT(guild_id) DO UPDATE SET
                    channel_id = excluded.channel_id,
                    message_id = COALESCE(excluded.message_id, channel_settings.message_id)
            """, (guild_id, channel_id, message_id))
            conn.commit()

    def get_channel_setting(self, guild_id: int) -> Optional[ChannelSetting]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM channel_settings WHERE guild_id = ?", (guild_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return ChannelSetting(
                guild_id=row["guild_id"],
                channel_id=row["channel_id"],
                message_id=row["message_id"]
            )

    def get_all_channel_settings(self) -> List[ChannelSetting]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM channel_settings")
            rows = cursor.fetchall()
            return [
                ChannelSetting(
                    guild_id=row["guild_id"],
                    channel_id=row["channel_id"],
                    message_id=row["message_id"]
                )
                for row in rows
            ]