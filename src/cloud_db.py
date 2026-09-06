"""
Supabase クラウド同期（完全永続化）
"""

import os
import json
import asyncio
from datetime import datetime
from typing import Dict, List, Optional
import aiohttp
from src.models import UserSetting, WaterLog

class SupabaseWaterClient:
    def __init__(self, supabase_url: Optional[str] = None, supabase_key: Optional[str] = None):
        self.url = (supabase_url or os.getenv("SUPABASE_URL", "")).rstrip("/")
        self.key = supabase_key or os.getenv("SUPABASE_KEY", "") or os.getenv("SUPABASE_ANON_KEY", "")
        self.enabled = bool(self.url and self.key)

    def _headers(self) -> Dict[str, str]:
        return {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation"
        }

    async def sync_from_cloud(self, local_db) -> int:
        """起動時にクラウドから最新ログおよびユーザー設定をローカルへ完全リストア"""
        if not self.enabled:
            return 0

        # 1. ユーザー設定の同期
        await self.sync_users_from_cloud(local_db)

        # 2. 水分ログの同期
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.url}/rest/v1/water_logs?select=*&order=id.desc&limit=200", headers=self._headers()) as resp:
                    if resp.status == 200:
                        cloud_logs = await resp.json()
                        from src.sync import WaterSyncManager
                        sync_mgr = WaterSyncManager(local_db)
                        user_logs_map = {}
                        for log in cloud_logs:
                            uid = str(log["user_id"])
                            user_logs_map.setdefault(uid, []).append({
                                "amount_ml": log["amount_ml"],
                                "gulp_count": log.get("gulp_count"),
                                "recorded_at": log["recorded_at"],
                                "source": log.get("source", "supabase")
                            })
                        imported = 0
                        for uid, logs in user_logs_map.items():
                            res = sync_mgr.sync_batch_logs(uid, logs)
                            imported += res["imported_count"]
                        return imported
        except Exception as e:
            print(f"[Supabase] ログ復元エラー: {e}")
        return 0

    async def sync_users_from_cloud(self, local_db) -> None:
        """クラウドに保存されているユーザー設定をローカルDBへ復元"""
        if not self.enabled:
            return
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.url}/rest/v1/users?select=*", headers=self._headers()) as resp:
                    if resp.status == 200:
                        users_data = await resp.json()
                        for u_data in users_data:
                            presets = u_data.get("presets", [100, 250, 500])
                            if isinstance(presets, str):
                                try:
                                    presets = json.loads(presets)
                                except Exception:
                                    presets = [100, 250, 500]
                            u = UserSetting(
                                user_id=str(u_data["user_id"]),
                                name=u_data.get("name", "ユーザー"),
                                daily_goal_ml=u_data.get("daily_goal_ml", 2000),
                                gulp_ml=u_data.get("gulp_ml", 25),
                                reset_time=u_data.get("reset_time", "06:00"),
                                notification_enabled=bool(u_data.get("notification_enabled", 1)),
                                notification_start=u_data.get("notification_start", "08:00"),
                                notification_end=u_data.get("notification_end", "23:00"),
                                notification_interval=u_data.get("notification_interval", 60),
                                notification_mode=u_data.get("notification_mode", "dm"),
                                presets=presets,
                                visibility=u_data.get("visibility", "all"),
                                gender=u_data.get("gender", "male"),
                                age=u_data.get("age", 25),
                                height_cm=float(u_data.get("height_cm", 165.0)),
                                weight_kg=float(u_data.get("weight_kg", 66.0)),
                                bedtime=u_data.get("bedtime", "24:00"),
                                activity_level=u_data.get("activity_level", "medium"),
                                auto_goal_enabled=bool(u_data.get("auto_goal_enabled", 1))
                            )
                            local_db.save_user(u)
        except Exception as e:
            print(f"[Supabase] ユーザー復元エラー: {e}")

    async def upload_log(self, user_id: str, amount_ml: int, gulp_count: Optional[int], recorded_at: datetime, date_key: str, source: str) -> None:
        """ローカルで記録された水分ログをクラウドへ非同期アップロード"""
        if not self.enabled:
            return
        payload = {
            "user_id": str(user_id),
            "amount_ml": amount_ml,
            "gulp_count": gulp_count,
            "recorded_at": recorded_at.isoformat(),
            "date_key": date_key,
            "source": source
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(f"{self.url}/rest/v1/water_logs", headers=self._headers(), json=payload) as resp:
                    pass
        except Exception as e:
            print(f"[Supabase] ログ保存エラー: {e}")

    async def upload_user(self, user: UserSetting) -> None:
        """ローカルで更新されたユーザープロフィールをクラウドへアップロード"""
        if not self.enabled:
            return
        payload = {
            "user_id": str(user.user_id),
            "name": user.name,
            "daily_goal_ml": user.daily_goal_ml,
            "gulp_ml": user.gulp_ml,
            "reset_time": user.reset_time,
            "notification_enabled": 1 if user.notification_enabled else 0,
            "notification_start": user.notification_start,
            "notification_end": user.notification_end,
            "notification_interval": user.notification_interval,
            "notification_mode": user.notification_mode,
            "presets": json.dumps(user.presets),
            "visibility": user.visibility,
            "gender": user.gender,
            "age": user.age,
            "height_cm": user.height_cm,
            "weight_kg": user.weight_kg,
            "bedtime": user.bedtime,
            "activity_level": user.activity_level,
            "auto_goal_enabled": 1 if user.auto_goal_enabled else 0
        }
        headers = self._headers()
        headers["Prefer"] = "resolution=merge-duplicates"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(f"{self.url}/rest/v1/users", headers=headers, json=payload) as resp:
                    pass
        except Exception as e:
            print(f"[Supabase] ユーザー保存エラー: {e}")