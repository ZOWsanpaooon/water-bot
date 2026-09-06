"""
水分管理専用 Discord Cog (Water Cog)
DM通知 & チャンネル通知、スラッシュコマンド /water-channel、定期監視ループ
"""

import asyncio
import os
import aiohttp
from datetime import datetime, time, timedelta
from typing import Dict, Optional
import discord
from discord import app_commands
from discord.ext import commands, tasks

from src.api import WaterRestApiServer
from src.db import WaterDatabase, get_current_jst_time, JST
from src.panel import build_water_panel_embed, build_reminder_embed
from src.ui import WaterPanelView, WaterReminderView
from src.cloud_db import SupabaseWaterClient
from src.parser import parse_water_message
from src.sync import WaterSyncManager


class WaterCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = WaterDatabase()
        self.panel_view = WaterPanelView(db=self.db, cog=self)
        self.cloud_client = SupabaseWaterClient()
        self.sync_mgr = WaterSyncManager(self.db)

        self.snooze_until: Dict[str, datetime] = {}
        self.active_reminder_messages: Dict[str, discord.Message] = {}
        self.last_date_keys: Dict[str, str] = {}

        api_port = int(os.getenv("PORT") or os.getenv("WATER_API_PORT") or "8080")
        self.api_server = WaterRestApiServer(
            db=self.db,
            port=api_port,
            sync_mgr=self.sync_mgr,
            on_record_callback=self.refresh_all_panels
        )

        self.water_background_task.start()
        self.render_keepalive_task.start()

    async def cog_load(self) -> None:
        self.bot.add_view(self.panel_view)
        try:
            await self.api_server.start()
        except Exception as e:
            print(f"[WaterCog] API Server start skipped: {e}")

    def cog_unload(self) -> None:
        self.water_background_task.cancel()
        self.render_keepalive_task.cancel()
        asyncio.create_task(self.api_server.stop())

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        print("[WaterCog] 水分管理Botが正常に起動しました (24時間クラウド稼働モード)")

        # クラウド同期 (Supabase)
        if self.cloud_client.enabled:
            imported = await self.cloud_client.sync_from_cloud(self.db)
            if imported > 0:
                print(f"[WaterCog] Supabaseから {imported} 件のデータを同期しました。")

        # パネル最新化
        await self.refresh_all_panels()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot:
            return

        is_dm = isinstance(message.channel, discord.DMChannel)
        settings = self.db.get_all_channel_settings()
        is_registered_channel = any(s.channel_id == message.channel.id for s in settings)
        ch_name = getattr(message.channel, "name", "").lower()
        is_named_water_channel = any(w in ch_name for w in ["水", "water", "水分", "bot", "のんだ"])

        is_water_context = is_dm or is_registered_channel or is_named_water_channel

        user = self.db.get_or_create_user(str(message.author.id), message.author.display_name)
        parsed = parse_water_message(message.content, user_gulp_ml=user.gulp_ml)
        if not parsed:
            return

        # 一般チャンネルでの誤爆防止: 明確な水分キーワードが含まれている場合のみ感知
        if not is_water_context:
            text = message.content.lower()
            has_water_keyword = any(k in text for k in ["ごく", "ゴク", "口", "ml", "ミリ", "cc", "杯", "本", "水", "飲", "茶", "アクエ", "ポカリ"])
            if not has_water_keyword:
                return

        amount_ml, gulp_count = parsed
        log, progress = self.db.add_log(
            user_id=str(message.author.id),
            amount_ml=amount_ml,
            gulp_count=gulp_count,
            source="discord_dm" if is_dm else "discord_channel",
            user_name=message.author.display_name
        )

        if is_water_context and not is_dm:
            try:
                await message.delete()
            except Exception:
                pass

        if self.cloud_client.enabled:
            asyncio.create_task(self.cloud_client.upload_log(
                user_id=log.user_id,
                amount_ml=log.amount_ml,
                gulp_count=log.gulp_count,
                recorded_at=log.recorded_at,
                date_key=log.date_key,
                source=log.source
            ))

        await self.refresh_all_panels()

        action_desc = f"{gulp_count}ゴク ({amount_ml:,}ml)" if gulp_count else f"+{amount_ml:,}ml"
        fb_text = f"🥤 **{action_desc}** を記録しました！（本日合計: **{progress.total_ml:,}** / {progress.goal_ml:,} ml）"
        if progress.is_first_achievement:
            fb_text += "\n🎉 **今日の水分目標を達成しました！** 🥳✨"

        try:
            if is_dm:
                await message.channel.send(fb_text)
            else:
                await message.channel.send(fb_text, delete_after=5)
        except Exception:
            pass

    def backup_log_to_cloud(self, log) -> None:
        """ログをクラウド(Supabase)へ非同期バックアップ"""
        if self.cloud_client.enabled:
            asyncio.create_task(self.cloud_client.upload_log(
                user_id=log.user_id,
                amount_ml=log.amount_ml,
                gulp_count=log.gulp_count,
                recorded_at=log.recorded_at,
                date_key=log.date_key,
                source=log.source
            ))

    def backup_user_to_cloud(self, user) -> None:
        """ユーザープロファイルをクラウド(Supabase)へ非同期バックアップ"""
        if self.cloud_client.enabled:
            asyncio.create_task(self.cloud_client.upload_user(user))

    def postpone_user_notification(self, user_id: str, minutes: int = 30) -> None:
        now = get_current_jst_time()
        self.snooze_until[str(user_id)] = now + timedelta(minutes=minutes)

    async def _setup_water_panel(self, channel: discord.TextChannel, user: discord.Member, respond_func) -> None:
        guild = channel.guild
        self.db.get_or_create_user(str(user.id), user.display_name)

        all_progress = self.db.get_all_progress()
        stats_dict = self.panel_view._get_stats_dict()
        embed = build_water_panel_embed(all_progress, stats_dict)

        setting = self.db.get_channel_setting(guild.id)
        if setting and setting.message_id and setting.channel_id == channel.id:
            try:
                old_msg = await channel.fetch_message(setting.message_id)
                await old_msg.edit(embed=embed, view=self.panel_view)
                await respond_func("✅ 既存の水分管理パネルを最新状態に更新しました！")
                return
            except Exception:
                pass

        panel_message = await channel.send(embed=embed, view=self.panel_view)
        self.db.save_channel_setting(
            guild_id=guild.id,
            channel_id=channel.id,
            message_id=panel_message.id
        )

        await respond_func(
            f"✅ **{channel.name}** を水分管理チャンネルに設定し、常設パネルを設置しました！"
        )

    @app_commands.command(
        name="water-channel",
        description="このチャンネルを水分登録専用チャンネルに設定し、常設パネルを設置します。"
    )
    async def water_channel_slash(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        channel = interaction.channel

        if not guild or not channel or not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message("❌ このコマンドはサーバー内のテキストチャンネルで実行してください。", ephemeral=True)
            return

        async def respond(text: str):
            await interaction.response.send_message(text, ephemeral=True)

        await self._setup_water_panel(channel, interaction.user, respond)

    async def refresh_all_panels(self, exclude_message_id: Optional[int] = None) -> None:
        settings = self.db.get_all_channel_settings()
        if not settings:
            return

        all_progress = self.db.get_all_progress()
        stats_dict = self.panel_view._get_stats_dict()
        embed = build_water_panel_embed(all_progress, stats_dict)

        for s in settings:
            if not s.message_id or s.message_id == exclude_message_id:
                continue
            try:
                guild = self.bot.get_guild(s.guild_id)
                if not guild:
                    continue
                channel = guild.get_channel(s.channel_id)
                if not channel or not isinstance(channel, discord.TextChannel):
                    continue
                msg = await channel.fetch_message(s.message_id)
                await msg.edit(embed=embed, view=self.panel_view)
            except Exception:
                pass

    @tasks.loop(minutes=1)
    async def water_background_task(self) -> None:
        now = get_current_jst_time()
        users = self.db.get_all_users()
        if not users:
            return

        need_panel_refresh = False

        for user in users:
            current_date_key = self.db.calculate_date_key(now, user.reset_time)
            last_date_key = self.last_date_keys.get(user.user_id)

            if last_date_key is not None and last_date_key != current_date_key:
                need_panel_refresh = True
            self.last_date_keys[user.user_id] = current_date_key

            if not user.notification_enabled:
                continue

            snooze_time = self.snooze_until.get(user.user_id)
            if snooze_time and now < snooze_time:
                continue

            try:
                s_h, s_m = map(int, user.notification_start.split(":"))
                e_h, e_m = map(int, user.notification_end.split(":"))
                start_t = time(s_h, s_m)
                end_t = time(e_h, e_m)
                current_t = now.time()

                if not (start_t <= current_t <= end_t):
                    continue
            except Exception:
                continue

            progress = self.db.get_daily_progress(user.user_id, date_key=current_date_key)

            if progress.is_achieved:
                continue

            rec = progress.recommendation
            if not rec or not rec.recommended_dt:
                continue

            if now < rec.recommended_dt:
                continue

            if progress.last_recorded_at:
                diff_since_last_drink = (now - progress.last_recorded_at).total_seconds() / 60
                if diff_since_last_drink < 30:
                    continue

            # 通知送信（DM優先）
            await self._send_user_reminder(user, progress)
            self.snooze_until[user.user_id] = now + timedelta(minutes=45)

        if need_panel_refresh:
            await self.refresh_all_panels()

    @water_background_task.before_loop
    async def before_water_task(self) -> None:
        await self.bot.wait_until_ready()

    @tasks.loop(minutes=10)
    async def render_keepalive_task(self) -> None:
        """Render無料プランのスリープ(15分無通信)を防止するための自己Ping"""
        render_url = os.getenv("RENDER_EXTERNAL_URL") or "https://shui-hayabeedaro.onrender.com"
        target_url = f"{render_url.rstrip('/')}/api/health"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(target_url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    pass
        except Exception:
            pass

    @render_keepalive_task.before_loop
    async def before_render_keepalive(self) -> None:
        await self.bot.wait_until_ready()

    async def _send_user_reminder(self, user, progress) -> None:
        rec = progress.recommendation
        rec_ml = rec.recommended_ml if rec else 200

        embed = build_reminder_embed(progress)
        view = WaterReminderView(db=self.db, target_user_id=user.user_id, recommended_ml=rec_ml, cog=self)

        old_msg = self.active_reminder_messages.get(user.user_id)
        if old_msg:
            try:
                await old_msg.delete()
            except Exception:
                pass

        # 1. DM送信を試行 (DMモードまたはユーザー指定)
        sent = False
        try:
            discord_user = await self.bot.fetch_user(int(user.user_id))
            if discord_user:
                dm_msg = await discord_user.send(embed=embed, view=view)
                self.active_reminder_messages[user.user_id] = dm_msg
                sent = True
        except Exception:
            sent = False

        # 2. DMが送れない場合は専用チャンネルへフォールバック
        if not sent:
            settings = self.db.get_all_channel_settings()
            for s in settings:
                try:
                    guild = self.bot.get_guild(s.guild_id)
                    if not guild:
                        continue
                    channel = guild.get_channel(s.channel_id)
                    if not channel or not isinstance(channel, discord.TextChannel):
                        continue
                    ch_msg = await channel.send(content=f"<@{user.user_id}>", embed=embed, view=view)
                    self.active_reminder_messages[user.user_id] = ch_msg
                    break
                except Exception:
                    pass


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(WaterCog(bot))