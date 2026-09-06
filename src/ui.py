"""
水分管理システム Discord UI コンポーネント (Persistent Views & Modals)
"""

from typing import TYPE_CHECKING, Optional, Tuple
import re
import discord
from discord import ui

from src.db import WaterDatabase, get_current_jst_time
from src.models import UserSetting, DailyProgress, WaterRecommendation
from src.panel import build_history_embed, build_water_panel_embed, build_reminder_embed
from src.analytics import WaterAnalytics

if TYPE_CHECKING:
    from src.cog import WaterCog


class WaterPanelView(ui.View):
    def __init__(self, db: WaterDatabase, cog: Optional["WaterCog"] = None):
        super().__init__(timeout=None)
        self.db = db
        self.cog = cog
        self.analytics = WaterAnalytics(db)

    def _get_stats_dict(self) -> dict:
        users = self.db.get_all_users()
        return {u.user_id: self.analytics.get_comprehensive_stats(u.user_id) for u in users}

    async def _handle_record(
        self,
        interaction: discord.Interaction,
        amount_ml: int,
        gulp_count: Optional[int] = None,
        source: str = "discord"
    ) -> None:
        user_id = str(interaction.user.id)
        user_name = interaction.user.display_name

        log, progress = self.db.add_log(
            user_id=user_id,
            amount_ml=amount_ml,
            gulp_count=gulp_count,
            source=source,
            user_name=user_name
        )

        all_progress = self.db.get_all_progress()
        stats_dict = self._get_stats_dict()
        embed = build_water_panel_embed(all_progress, stats_dict)

        if interaction.message:
            try:
                await interaction.response.edit_message(embed=embed, view=self)
            except Exception:
                pass

        action_desc = f"{gulp_count}ゴク (+{amount_ml:,}ml)" if gulp_count else f"+{amount_ml:,}ml"
        feedback = f"🥤 **{action_desc}** を記録しました！（本日合計: **{progress.total_ml:,}** / {progress.goal_ml:,} ml）"
        if progress.is_first_achievement:
            feedback += "\n\n🎉 **おめでとうございます！今日の水分目標を達成しました！** 🥳✨"

        if not interaction.response.is_done():
            await interaction.response.send_message(feedback, ephemeral=True)
        else:
            await interaction.followup.send(feedback, ephemeral=True)

        if self.cog:
            self.cog.backup_log_to_cloud(log)
            await self.cog.refresh_all_panels(exclude_message_id=interaction.message.id if interaction.message else None)

    async def _handle_gulp(self, interaction: discord.Interaction, count: int) -> None:
        user = self.db.get_or_create_user(str(interaction.user.id), interaction.user.display_name)
        gulp_ml = user.gulp_ml or 25
        amount_ml = count * gulp_ml
        await self._handle_record(interaction, amount_ml=amount_ml, gulp_count=count)

    @ui.button(label="1ゴク", style=discord.ButtonStyle.primary, emoji="💧", custom_id="water:gulp:1", row=0)
    async def gulp_1_button(self, interaction: discord.Interaction, button: ui.Button):
        await self._handle_gulp(interaction, count=1)

    @ui.button(label="2ゴク", style=discord.ButtonStyle.primary, emoji="💧", custom_id="water:gulp:2", row=0)
    async def gulp_2_button(self, interaction: discord.Interaction, button: ui.Button):
        await self._handle_gulp(interaction, count=2)

    @ui.button(label="3ゴク", style=discord.ButtonStyle.primary, emoji="💧", custom_id="water:gulp:3", row=0)
    async def gulp_3_button(self, interaction: discord.Interaction, button: ui.Button):
        await self._handle_gulp(interaction, count=3)

    @ui.button(label="4ゴク", style=discord.ButtonStyle.primary, emoji="💧", custom_id="water:gulp:4", row=0)
    async def gulp_4_button(self, interaction: discord.Interaction, button: ui.Button):
        await self._handle_gulp(interaction, count=4)

    @ui.button(label="5ゴク", style=discord.ButtonStyle.primary, emoji="💧", custom_id="water:gulp:5", row=0)
    async def gulp_5_button(self, interaction: discord.Interaction, button: ui.Button):
        await self._handle_gulp(interaction, count=5)

    @ui.button(label="履歴", style=discord.ButtonStyle.secondary, emoji="📊", custom_id="water:history", row=1)
    async def history_button(self, interaction: discord.Interaction, button: ui.Button):
        user_id = str(interaction.user.id)
        user_name = interaction.user.display_name
        self.db.get_or_create_user(user_id, user_name)
        progress = self.db.get_daily_progress(user_id)
        stats = self.analytics.get_comprehensive_stats(user_id)
        embed = build_history_embed(progress, stats)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @ui.button(label="取り消す", style=discord.ButtonStyle.danger, emoji="↩️", custom_id="water:undo", row=1)
    async def undo_button(self, interaction: discord.Interaction, button: ui.Button):
        user_id = str(interaction.user.id)
        last_log = self.db.get_last_log(user_id)
        if not last_log:
            await interaction.response.send_message("❌ 本日の取り消し可能な記録がありません。", ephemeral=True)
            return

        undo_view = UndoConfirmView(panel_view=self, log_id=last_log.id, amount_ml=last_log.amount_ml, recorded_at_str=last_log.recorded_at.strftime("%H:%M"))
        msg = f"直近の記録： **{last_log.recorded_at.strftime('%H:%M')} (+{last_log.amount_ml:,}ml)**\nこの記録を取り消しますか？"
        await interaction.response.send_message(msg, view=undo_view, ephemeral=True)

    @ui.button(label="設定", style=discord.ButtonStyle.secondary, emoji="⚙️", custom_id="water:settings", row=1)
    async def settings_button(self, interaction: discord.Interaction, button: ui.Button):
        user = self.db.get_or_create_user(str(interaction.user.id), interaction.user.display_name)
        modal = UserProfileModal(db=self.db, user=user, panel_view=self)
        await interaction.response.send_modal(modal)


class WaterReminderView(ui.View):
    def __init__(self, db: WaterDatabase, target_user_id: str, recommended_ml: int, cog: Optional["WaterCog"] = None):
        super().__init__(timeout=None)
        self.db = db
        self.target_user_id = str(target_user_id)
        self.recommended_ml = recommended_ml
        self.cog = cog
        self.drink_recommended_btn.label = f"💧 {recommended_ml}ml飲んだ"

    async def _check_user(self, interaction: discord.Interaction) -> bool:
        if str(interaction.user.id) != self.target_user_id:
            await interaction.response.send_message("❌ これは他のユーザー宛ての通知です。", ephemeral=True)
            return False
        return True

    @ui.button(label="💧 推奨量を飲んだ", style=discord.ButtonStyle.primary, row=0)
    async def drink_recommended_btn(self, interaction: discord.Interaction, button: ui.Button):
        if not await self._check_user(interaction):
            return

        user_id = str(interaction.user.id)
        user_name = interaction.user.display_name
        log, progress = self.db.add_log(
            user_id=user_id,
            amount_ml=self.recommended_ml,
            source="discord_reminder",
            user_name=user_name
        )

        msg = f"✅ **+{self.recommended_ml:,}ml** を記録しました！（本日合計: **{progress.total_ml:,}** / {progress.goal_ml:,} ml）"
        await interaction.response.edit_message(content=msg, embed=None, view=None)

        if self.cog:
            await self.cog.refresh_all_panels()

    @ui.button(label="🥤 別の量を記録", style=discord.ButtonStyle.secondary, row=0)
    async def drink_custom_btn(self, interaction: discord.Interaction, button: ui.Button):
        if not await self._check_user(interaction):
            return

        modal = ReminderCustomAmountModal(db=self.db, cog=self.cog, reminder_message=interaction.message)
        await interaction.response.send_modal(modal)

    @ui.button(label="⏰ 30分後", style=discord.ButtonStyle.secondary, row=0)
    async def snooze_30m_btn(self, interaction: discord.Interaction, button: ui.Button):
        if not await self._check_user(interaction):
            return

        if self.cog:
            self.cog.postpone_user_notification(self.target_user_id, minutes=30)

        await interaction.response.edit_message(
            content="⏰ **リマインダーを30分後に延期しました。**",
            embed=None,
            view=None
        )

    @ui.button(label="✕ 通知を閉じる", style=discord.ButtonStyle.danger, row=0)
    async def close_btn(self, interaction: discord.Interaction, button: ui.Button):
        if not await self._check_user(interaction):
            return

        try:
            await interaction.message.delete()
        except Exception:
            await interaction.response.edit_message(content="通知を閉じました。", embed=None, view=None)


class ReminderCustomAmountModal(ui.Modal, title="🥤 水分摂取量の記録"):
    amount_input = ui.TextInput(
        label="実際に飲んだ量 (ml)",
        placeholder="例: 200",
        required=True,
        min_length=1,
        max_length=6
    )

    def __init__(self, db: WaterDatabase, cog: Optional["WaterCog"], reminder_message: Optional[discord.Message]):
        super().__init__()
        self.db = db
        self.cog = cog
        self.reminder_message = reminder_message

    async def on_submit(self, interaction: discord.Interaction):
        val_str = self.amount_input.value.strip()
        if not val_str.isdigit() or int(val_str) <= 0:
            await interaction.response.send_message("❌ 有効なml数を半角数字で入力してください。", ephemeral=True)
            return

        amount = int(val_str)
        user_id = str(interaction.user.id)
        user_name = interaction.user.display_name

        log, progress = self.db.add_log(
            user_id=user_id,
            amount_ml=amount,
            source="discord_reminder",
            user_name=user_name
        )

        msg = f"✅ **+{amount:,}ml** を記録しました！（本日合計: **{progress.total_ml:,}** / {progress.goal_ml:,} ml）"

        if self.reminder_message:
            try:
                await self.reminder_message.edit(content=msg, embed=None, view=None)
            except Exception:
                pass

        await interaction.response.send_message(msg, ephemeral=True)

        if self.cog:
            await self.cog.refresh_all_panels()


class UserProfileModal(ui.Modal, title="⚙️ プロフィール設定"):
    def __init__(self, db: WaterDatabase, user: UserSetting, panel_view: WaterPanelView):
        super().__init__()
        self.db = db
        self.user = user
        self.panel_view = panel_view

        self.name_input = ui.TextInput(
            label="1. 表示名",
            default=user.name,
            placeholder="例: ゆうと / れん",
            required=True,
            max_length=32
        )

        self.gender_input = ui.TextInput(
            label="2. 性別 (男 または 女)",
            default="男" if user.gender == "male" else "女",
            placeholder="男 / 女 （1文字でOK）",
            required=True,
            max_length=10
        )

        self.body_input = ui.TextInput(
            label="3. 年齢 身長cm 体重kg 1ゴクml (数字でOK)",
            default=f"{user.age} {user.height_cm:.0f} {user.weight_kg:.0f} {user.gulp_ml}",
            placeholder="例: 20 160 60 25 （スペース区切り）",
            required=True,
            max_length=35
        )

        act_display = "1 (少ない)" if user.activity_level == "low" else ("3 (多い)" if user.activity_level == "high" else "2 (普通)")
        self.activity_input = ui.TextInput(
            label="4. 日中の活動量 (1:少 / 2:普通 / 3:多)",
            default=act_display,
            placeholder="1=少ない / 2=普通 / 3=多い",
            required=True,
            max_length=20
        )

        self.bedtime_input = ui.TextInput(
            label="5. 就寝時間 (HH:MM)",
            default=user.bedtime or "24:00",
            placeholder="例: 03:30 / 24:00 / 1:00",
            required=True,
            max_length=10
        )

        self.add_item(self.name_input)
        self.add_item(self.gender_input)
        self.add_item(self.body_input)
        self.add_item(self.activity_input)
        self.add_item(self.bedtime_input)

    @staticmethod
    def parse_body_stats(raw_str: str, default_age: int, default_h: float, default_w: float, default_gulp: int = 25) -> Tuple[int, float, float, int]:
        numbers = [float(n) for n in re.findall(r"\d+(?:\.\d+)?", raw_str)]
        if not numbers:
            return default_age, default_h, default_w, default_gulp

        age = default_age
        height = default_h
        weight = default_w
        gulp = default_gulp

        if len(numbers) >= 4:
            age = int(numbers[0])
            height = float(numbers[1])
            weight = float(numbers[2])
            gulp = int(numbers[3])
        elif len(numbers) == 3:
            h_cands = [n for n in numbers if 120.0 <= n <= 230.0]
            if h_cands:
                height = h_cands[0]
                rest = [n for n in numbers if n != height]
                if len(rest) >= 2:
                    age = int(rest[0])
                    weight = float(rest[1])
            else:
                age = int(numbers[0])
                height = float(numbers[1])
                weight = float(numbers[2])
        elif len(numbers) == 2:
            height = float(numbers[0])
            weight = float(numbers[1])
        elif len(numbers) == 1:
            if numbers[0] >= 100:
                height = float(numbers[0])
            else:
                weight = float(numbers[0])

        return int(age), float(height), float(weight), max(5, min(100, int(gulp)))

    @staticmethod
    def parse_activity(raw_str: str) -> str:
        s = raw_str.strip().lower()
        if "1" in s or "少" in s or "low" in s or "低" in s:
            return "low"
        elif "3" in s or "多" in s or "high" in s or "高" in s or "激" in s:
            return "high"
        else:
            return "medium"

    @staticmethod
    def parse_bedtime(raw_str: str) -> str:
        s = raw_str.strip().replace("：", ":").replace("時", ":").replace("分", "")
        if ":" in s:
            parts = s.split(":")
            h = int(parts[0]) if parts[0].isdigit() else 24
            m = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
        elif s.isdigit():
            val = int(s)
            if len(s) in (3, 4):
                h = int(s[:-2])
                m = int(s[-2:])
            else:
                h = val
                m = 0
        else:
            return "24:00"

        h = h % 24 if h != 24 else 24
        m = max(0, min(59, m))
        return f"{h:02d}:{m:02d}"

    async def on_submit(self, interaction: discord.Interaction):
        self.user.name = self.name_input.value.strip() or "ユーザー"
        g_val = self.gender_input.value.strip().lower()
        self.user.gender = "female" if ("女" in g_val or "f" in g_val or "2" in g_val) else "male"

        age, height, weight, gulp = self.parse_body_stats(
            self.body_input.value,
            default_age=self.user.age,
            default_h=self.user.height_cm,
            default_w=self.user.weight_kg,
            default_gulp=self.user.gulp_ml
        )
        self.user.age = age
        self.user.height_cm = height
        self.user.weight_kg = weight
        self.user.gulp_ml = gulp
        self.user.activity_level = self.parse_activity(self.activity_input.value)
        self.user.bedtime = self.parse_bedtime(self.bedtime_input.value)
        self.user.auto_goal_enabled = True

        self.db.save_user(self.user)

        all_progress = self.db.get_all_progress()
        stats_dict = self.panel_view._get_stats_dict()
        embed = build_water_panel_embed(all_progress, stats_dict)

        act_label = "🟢 少ない" if self.user.activity_level == "low" else ("🔴 多い" if self.user.activity_level == "high" else "🟡 普通")
        await interaction.response.send_message(
            f"✅ **プロフィールを更新しました！**\n"
            f"・お名前: **{self.user.name}**\n"
            f"・性別: **{'男性' if self.user.gender == 'male' else '女性'}** / 年齢: **{self.user.age}歳**\n"
            f"・身長: **{self.user.height_cm:.0f}cm** / 体重: **{self.user.weight_kg:.0f}kg**\n"
            f"・1ゴクの量: **{self.user.gulp_ml}ml**\n"
            f"・活動量: **{act_label}**\n"
            f"・就寝時間: **{self.user.bedtime}**",
            ephemeral=True
        )

        if self.panel_view.cog:
            self.panel_view.cog.backup_user_to_cloud(self.user)
            await self.panel_view.cog.refresh_all_panels()


class UndoConfirmView(ui.View):
    def __init__(self, panel_view: WaterPanelView, log_id: Optional[int], amount_ml: int, recorded_at_str: str):
        super().__init__(timeout=60)
        self.panel_view = panel_view
        self.log_id = log_id
        self.amount_ml = amount_ml
        self.recorded_at_str = recorded_at_str

    @ui.button(label="取り消す", style=discord.ButtonStyle.danger, emoji="✅")
    async def confirm_undo(self, interaction: discord.Interaction, button: ui.Button):
        user_id = str(interaction.user.id)
        res = self.panel_view.db.delete_last_log(user_id)
        if not res:
            await interaction.response.edit_message(content="❌ 取り消し対象の記録が見つかりませんでした。", view=None)
            return

        deleted_log, new_progress = res
        all_progress = self.panel_view.db.get_all_progress()
        stats_dict = self.panel_view._get_stats_dict()
        embed = build_water_panel_embed(all_progress, stats_dict)

        msg_text = f"↩️ **{self.recorded_at_str} (+{self.amount_ml:,}ml)** の記録を取り消しました。\n（現在の合計: **{new_progress.total_ml:,}** / {new_progress.goal_ml:,} ml）"
        await interaction.response.edit_message(content=msg_text, view=None)

        if self.panel_view.cog:
            await self.panel_view.cog.refresh_all_panels()

    @ui.button(label="キャンセル", style=discord.ButtonStyle.secondary, emoji="❌")
    async def cancel_undo(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.edit_message(content="取り消しをキャンセルしました。", view=None)