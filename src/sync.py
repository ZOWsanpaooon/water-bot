"""
水分同期マネージャー
"""

from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional
from src.db import JST, get_current_jst_time

class WaterSyncManager:
    def __init__(self, db):
        self.db = db

    def sync_batch_logs(self, user_id: str, logs_data: List[Dict], user_name: Optional[str] = None) -> Dict:
        imported_count = 0
        skipped_count = 0
        user = self.db.get_or_create_user(user_id, user_name or "ユーザー")

        for item in logs_data:
            amount_ml = int(item.get("amount_ml", 0))
            if amount_ml <= 0:
                continue

            gulp_count = item.get("gulp_count")
            rec_str = item.get("recorded_at")
            source = item.get("source", "sync")

            try:
                rec_dt = datetime.fromisoformat(rec_str)
                if rec_dt.tzinfo is None:
                    rec_dt = rec_dt.replace(tzinfo=JST)
                else:
                    rec_dt = rec_dt.astimezone(JST)
            except Exception:
                rec_dt = get_current_jst_time()

            date_key = self.db.calculate_date_key(rec_dt, user.reset_time)
            existing_logs = self.db.get_daily_logs(user_id, date_key=date_key)

            is_dup = False
            for ex in existing_logs:
                if ex.amount_ml == amount_ml:
                    diff_sec = abs((ex.recorded_at - rec_dt).total_seconds())
                    if diff_sec <= 60:
                        is_dup = True
                        break

            if is_dup:
                skipped_count += 1
                continue

            self.db.add_log(
                user_id=user_id,
                amount_ml=amount_ml,
                gulp_count=gulp_count,
                recorded_at=rec_dt,
                source=source,
                user_name=user_name
            )
            imported_count += 1

        progress = self.db.get_daily_progress(user_id)
        return {
            "success": True,
            "imported_count": imported_count,
            "skipped_count": skipped_count,
            "total_ml": progress.total_ml,
            "goal_ml": progress.goal_ml,
            "remaining_ml": progress.remaining_ml,
            "is_achieved": progress.is_achieved
        }