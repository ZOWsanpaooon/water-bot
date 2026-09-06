"""
水分管理Bot クラス定義
"""

import asyncio
import os
from typing import Optional
import discord
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

TOKEN: Optional[str] = os.getenv("WATER_BOT_TOKEN") or os.getenv("DISCORD_BOT_TOKEN")


class WaterBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.dm_messages = True
        activity = discord.Activity(type=discord.ActivityType.watching, name="💧 水分補給")
        super().__init__(
            command_prefix="!water ",
            intents=intents,
            status=discord.Status.online,
            activity=activity
        )

    async def setup_hook(self) -> None:
        await self.load_extension("src.cog")
        print("[WaterBot] 水分管理Cogをロードしました。")

    async def _safe_sync_commands(self) -> None:
        """起動を妨げないようにバックグラウンドで安全にスラッシュコマンドを同期"""
        await asyncio.sleep(1)  # 接続の安定化をわずかに待機
        for guild in self.guilds:
            try:
                self.tree.copy_global_to(guild=guild)
                await asyncio.wait_for(self.tree.sync(guild=guild), timeout=10.0)
                print(f"[WaterBot] サーバー '{guild.name}' にスラッシュコマンドを同期しました。")
            except Exception as e:
                print(f"[WaterBot] ギルド同期スキップ ({guild.name}): {e}")

        try:
            synced = await asyncio.wait_for(self.tree.sync(), timeout=10.0)
            print(f"[WaterBot] グローバルコマンド {len(synced)} 件を同期しました。")
        except Exception as e:
            # ギルド同期が成功していればスラッシュコマンドは即座に使用可能
            pass

    async def on_ready(self) -> None:
        await self.change_presence(
            status=discord.Status.online,
            activity=discord.Activity(type=discord.ActivityType.watching, name="💧 水分補給")
        )
        print(f"[WaterBot] 🟢 ログイン成功: {self.user.name}#{self.user.discriminator} (ID: {self.user.id})")
        print(f"[WaterBot] 参加サーバー数: {len(self.guilds)}")
        for g in self.guilds:
            print(f"  ・ {g.name} (ID: {g.id})")

        # コマンド同期を非同期でバックグラウンド実行（起動を一切ブロックしない）
        asyncio.create_task(self._safe_sync_commands())

    async def close(self) -> None:
        await super().close()


def run_water_bot() -> None:
    if not TOKEN:
        print("❌ エラー: WATER_BOT_TOKEN が .env に設定されていません。")
        exit(1)

    bot = WaterBot()
    bot.run(TOKEN)