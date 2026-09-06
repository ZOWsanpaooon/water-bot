"""
水分管理システム パネル表示ロジック (Panel Formatting & Embed Generation)
"""

from datetime import datetime
from typing import List, Optional
import discord

from src.models import DailyProgress, WaterRecommendation, WeatherInfo


def generate_progress_bar(percentage: float, length: int = 10) -> str:
    pct = max(0.0, percentage)
    filled_length = int(round(length * min(100.0, pct) / 100.0))
    bar = "█" * filled_length + "░" * (length - filled_length)
    return f"{bar} **{pct:.0f}%**"


def format_time_jst(dt: Optional[datetime]) -> str:
    if not dt:
        return "まだ記録なし"
    return dt.strftime("%H:%M")


def build_water_panel_embed(progresses: List[DailyProgress], stats_dict: Optional[dict] = None) -> discord.Embed:
    embed = discord.Embed(
        title="💧 水分管理",
        description="水を飲んだら下のボタンから記録してください ✨",
        color=discord.Color.from_rgb(52, 152, 219)
    )

    if not progresses:
        embed.add_field(
            name="ℹ️ まだユーザーが登録されていません",
            value="下のボタンを押して最初の水分を記録すると自動で登録されます！",
            inline=False
        )
    else:
        for p in progresses:
            bar_str = generate_progress_bar(p.percentage)
            amount_str = f"**{p.total_ml:,}** / {p.goal_ml:,} ml"

            if p.is_achieved:
                over_ml = p.total_ml - p.goal_ml
                over_str = f" (+{over_ml:,}ml)" if over_ml > 0 else ""
                status_header = f"🎉 **目標達成！**{over_str}"
            else:
                status_header = f"あと **{p.remaining_ml:,}** ml"

            last_time_str = format_time_jst(p.last_recorded_at)

            field_value = (
                f"{bar_str}\n\n"
                f"💧 **今日の水分**: {amount_str} （{status_header}）\n"
                f"⏰ **前回摂取**: {last_time_str}"
            )

            embed.add_field(
                name=f"👤 {p.name}",
                value=field_value,
                inline=False
            )

    embed.set_footer(text="ゆうゆうじてき 水分管理Bot (24時間クラウド稼働)")
    return embed


def build_reminder_embed(progress: DailyProgress) -> discord.Embed:
    rec = progress.recommendation
    rec_ml = rec.recommended_ml if rec else 200
    rec_gulps = rec.recommended_gulps if rec else 8
    rec_time = rec.recommended_time_str if rec else "今すぐ"
    status_summary = rec.status_summary if rec else "こまめな水分補給"

    embed = discord.Embed(
        title="💧 水分補給の目安",
        description=f"{status_summary}\n無理のない量でこまめに水分を摂りましょう ✨",
        color=discord.Color.from_rgb(52, 152, 219)
    )

    embed.add_field(
        name="📊 現在",
        value=f"**{progress.total_ml:,}** / {progress.goal_ml:,} ml (達成率 {progress.percentage:.0f}%)",
        inline=False
    )

    embed.add_field(
        name="🎯 次のおすすめ",
        value=f"**{rec_ml:,}ml** （{rec_gulps}ゴク）",
        inline=True
    )

    embed.add_field(
        name="🕐 目安時間",
        value=f"**{rec_time}**",
        inline=True
    )

    return embed


def build_history_embed(progress: DailyProgress, stats: Optional[dict] = None) -> discord.Embed:
    embed = discord.Embed(
        title=f"📊 {progress.name} さんの水分履歴 & 統計",
        color=discord.Color.blue()
    )

    if not progress.logs:
        embed.description = "本日はまだ水分の記録がありません。"
    else:
        lines = []
        for log in progress.logs:
            t_str = format_time_jst(log.recorded_at)
            source_map = {
                "apple_watch": " [⌚Watch]",
                "iphone": " [📱iPhone]",
                "api": " [🌐API]",
                "discord": " [💬Discord]",
                "discord_channel": " [💬Ch]",
                "discord_dm": " [✉️DM]",
                "discord_reminder": " [🔔通知]",
                "sync": " [☁️Sync]",
                "supabase": " [☁️Cloud]",
            }
            source_badge = source_map.get(log.source, "")

            gulp_str = f" ({log.gulp_count}ゴク)" if log.gulp_count is not None else ""
            lines.append(f"{t_str}　**+{log.amount_ml:,}ml**{gulp_str}{source_badge}")

        embed.description = "\n".join(lines)

    bar_str = generate_progress_bar(progress.percentage)
    summary_text = (
        f"━━━━━━━━━━━━━━\n"
        f"💧 本日合計： **{progress.total_ml:,}ml**\n"
        f"🎯 推奨目標： **{progress.goal_ml:,}ml**\n"
        f"📈 進捗： {bar_str}\n"
    )

    if stats:
        summary_text += (
            f"\n📊 **統計サマリー**\n"
            f"・昨日の合計: **{stats.get('yesterday_total', 0):,}ml**\n"
            f"・過去7日平均: **{stats.get('avg_7days', 0):,}ml** (達成率 {stats.get('achievement_rate_7d', 0):.0f}%)\n"
            f"・過去30日平均: **{stats.get('avg_30days', 0):,}ml** (達成率 {stats.get('achievement_rate_30d', 0):.0f}%)\n"
            f"・1回平均量: **{stats.get('avg_per_drink', 200)}ml**\n"
        )

    embed.add_field(name="📈 集計データ", value=summary_text, inline=False)
    return embed