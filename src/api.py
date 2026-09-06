"""
水分管理Bot REST API サーバー (Apple Watch / iPhone ショートカット連携)
"""

import asyncio
import os
from typing import Callable, Optional
from aiohttp import web
from src.db import WaterDatabase
from src.panel import format_time_jst
from src.sync import WaterSyncManager

class WaterRestApiServer:
    def __init__(
        self,
        db: WaterDatabase,
        port: int = 8080,
        host: str = "0.0.0.0",
        sync_mgr: Optional[WaterSyncManager] = None,
        on_record_callback: Optional[Callable[[], asyncio.Future]] = None
    ):
        self.db = db
        self.port = port
        self.host = host
        self.sync_mgr = sync_mgr or WaterSyncManager(db)
        self.on_record_callback = on_record_callback
        self.app = web.Application()
        self.runner: Optional[web.AppRunner] = None
        self.site: Optional[web.TCPSite] = None
        self._setup_routes()

    def _trigger_callback(self) -> None:
        """記録完了時のUI更新コールバックを安全に非同期起動"""
        if self.on_record_callback:
            try:
                res = self.on_record_callback()
                if asyncio.iscoroutine(res):
                    asyncio.create_task(res)
            except Exception:
                pass

    def _setup_routes(self) -> None:
        self.app.router.add_get("/api/health", self.handle_health)
        self.app.router.add_get("/api/water/status", self.handle_get_status)
        self.app.router.add_get("/api/water/recommendation", self.handle_get_recommendation)
        self.app.router.add_get("/api/water/recommendation_val", self.handle_get_recommendation_val)
        self.app.router.add_post("/api/water/record", self.handle_post_record)
        self.app.router.add_get("/api/water/record", self.handle_get_record_shortcut)
        self.app.router.add_post("/api/water/sync", self.handle_post_sync)

    async def handle_health(self, request: web.Request) -> web.Response:
        return web.json_response({"status": "ok", "service": "water-bot", "version": "2.1"})

    async def handle_get_status(self, request: web.Request) -> web.Response:
        user_id = request.query.get("user_id")
        if not user_id:
            progresses = self.db.get_all_progress()
            return web.json_response({
                "progresses": [
                    {
                        "user_id": p.user_id,
                        "name": p.name,
                        "total_ml": p.total_ml,
                        "goal_ml": p.goal_ml,
                        "remaining_ml": p.remaining_ml,
                        "percentage": round(p.percentage, 1),
                        "is_achieved": p.is_achieved,
                        "last_recorded_at": format_time_jst(p.last_recorded_at)
                    }
                    for p in progresses
                ]
            })

        p = self.db.get_daily_progress(user_id)
        return web.json_response({
            "user_id": p.user_id,
            "name": p.name,
            "total_ml": p.total_ml,
            "goal_ml": p.goal_ml,
            "remaining_ml": p.remaining_ml,
            "percentage": round(p.percentage, 1),
            "is_achieved": p.is_achieved,
            "last_recorded_at": format_time_jst(p.last_recorded_at)
        })

    async def handle_get_recommendation(self, request: web.Request) -> web.Response:
        user_id = request.query.get("user_id")
        if not user_id:
            users = self.db.get_all_users()
            user_id = users[0].user_id if users else "default"

        user = self.db.get_or_create_user(user_id)
        p = self.db.get_daily_progress(user_id)
        rec = p.recommendation

        rec_ml = rec.recommended_ml if rec else 200
        rec_gulps = rec.recommended_gulps if rec else 8
        rec_time = rec.recommended_time_str if rec else "今すぐ"

        speech_text = f"現在のおすすめは{rec_ml}ミリリットル、{rec_gulps}ゴクです。目安時刻は{rec_time}です。"
        if p.is_achieved:
            speech_text = f"本日の目標{p.goal_ml}ミリリットルを達成しています！喉の渇きに合わせて少量補給してください。"

        return web.json_response({
            "user_id": user_id,
            "name": user.name,
            "recommended_ml": rec_ml,
            "recommended_gulps": rec_gulps,
            "recommended_time": rec_time,
            "status_summary": rec.status_summary if rec else "",
            "total_ml": p.total_ml,
            "goal_ml": p.goal_ml,
            "remaining_ml": p.remaining_ml,
            "percentage": round(p.percentage, 1),
            "is_achieved": p.is_achieved,
            "speech_text": speech_text
        })

    async def handle_get_recommendation_val(self, request: web.Request) -> web.Response:
        user_id = request.query.get("user_id")
        if not user_id:
            users = self.db.get_all_users()
            user_id = users[0].user_id if users else "default"

        p = self.db.get_daily_progress(user_id)
        rec = p.recommendation
        rec_ml = rec.recommended_ml if rec else 200
        return web.Response(text=str(rec_ml), content_type="text/plain")

    async def _process_record(self, user_id: str, amount_ml: Optional[int], gulp_count: Optional[int], source: str, user_name: Optional[str]) -> web.Response:
        user = self.db.get_or_create_user(user_id, user_name or "ユーザー")

        if amount_ml is None and gulp_count is not None:
            amount_ml = gulp_count * user.gulp_ml

        if amount_ml is None or amount_ml <= 0:
            return web.json_response({"error": "Invalid amount_ml or gulp_count"}, status=400)

        log, progress = self.db.add_log(
            user_id=user_id,
            amount_ml=amount_ml,
            gulp_count=gulp_count,
            source=source,
            user_name=user_name
        )

        self._trigger_callback()

        speech_text = f"{amount_ml}ミリリットル記録しました。本日合計{progress.total_ml}ミリリットルです。"
        if progress.is_first_achievement:
            speech_text += " 今日の目標達成です！おめでとうございます。"

        return web.json_response({
            "success": True,
            "message": f"{amount_ml}ml記録しました",
            "speech_text": speech_text,
            "total_ml": progress.total_ml,
            "goal_ml": progress.goal_ml,
            "remaining_ml": progress.remaining_ml,
            "percentage": round(progress.percentage, 1),
            "is_achieved": progress.is_achieved
        })

    async def handle_post_record(self, request: web.Request) -> web.Response:
        try:
            data = await request.json()
        except Exception:
            data = {}

        user_id = data.get("user_id") or request.query.get("user_id")
        if not user_id:
            users = self.db.get_all_users()
            user_id = users[0].user_id if users else "default"

        amount_ml = data.get("amount_ml")
        gulp_count = data.get("gulp_count")
        source = data.get("source", "apple_watch")
        user_name = data.get("name")

        return await self._process_record(str(user_id), amount_ml, gulp_count, source, user_name)

    async def handle_get_record_shortcut(self, request: web.Request) -> web.Response:
        user_id = request.query.get("user_id")
        if not user_id:
            users = self.db.get_all_users()
            user_id = users[0].user_id if users else "default"

        amount_str = (
            request.query.get("amount_ml")
            or request.query.get("amount")
            or request.query.get("ml")
            or request.query.get("value")
            or request.query.get("val")
        )
        gulp_str = request.query.get("gulp_count") or request.query.get("gulp")

        amount_ml = None
        gulp_count = None

        if amount_str:
            digits = "".join(c for c in amount_str if c.isdigit())
            if digits:
                val = int(digits)
                if val <= 20 and gulp_str is None:
                    gulp_count = val
                else:
                    amount_ml = val

        if gulp_str:
            digits = "".join(c for c in gulp_str if c.isdigit())
            if digits:
                gulp_count = int(digits)

        if amount_ml is None and gulp_count is None:
            p = self.db.get_daily_progress(str(user_id))
            rec = p.recommendation
            amount_ml = rec.recommended_ml if rec else 200

        source = request.query.get("source", "apple_watch")
        user_name = request.query.get("name")

        return await self._process_record(str(user_id), amount_ml, gulp_count, source, user_name)

    async def handle_post_sync(self, request: web.Request) -> web.Response:
        from src.sync import WaterSyncManager
        try:
            data = await request.json()
        except Exception:
            return web.json_response({"error": "Invalid JSON body"}, status=400)

        user_id = data.get("user_id")
        logs = data.get("logs", [])
        user_name = data.get("name")

        if not user_id:
            users = self.db.get_all_users()
            user_id = users[0].user_id if users else "default"

        result = self.sync_mgr.sync_batch_logs(str(user_id), logs, user_name)
        self._trigger_callback()
        return web.json_response(result)

    async def start(self) -> None:
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()

        # ポート競合時は次のポート（+1〜+5）を自動試行
        base_port = self.port
        for offset in range(6):
            target_port = base_port + offset
            try:
                self.site = web.TCPSite(self.runner, self.host, target_port)
                await self.site.start()
                self.port = target_port
                print(f"[WaterRestApi] API server listening on http://{self.host}:{self.port}")
                return
            except OSError as e:
                if offset == 5:
                    raise e
                continue

    async def stop(self) -> None:
        if self.runner:
            await self.runner.cleanup()