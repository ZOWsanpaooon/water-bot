"""
水分管理システム データモデル (Data Models)
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import List, Optional

# ── 共通タイムゾーン定義（全モジュールからここを参照） ──
JST = timezone(timedelta(hours=9), name="JST")

def get_current_jst_time() -> datetime:
    """現在の日本標準時を返す"""
    return datetime.now(JST)


@dataclass
class WeatherInfo:
    """西蒲田（東京都大田区）の気象情報"""
    current_temp: float = 20.0       # 現在気温 (°C)
    max_temp: float = 22.0           # 予想最高気温 (°C)
    min_temp: float = 16.0           # 予想最低気温 (°C)
    humidity: int = 50               # 湿度 (%)
    apparent_temp: float = 20.0      # 体感温度 (°C)
    weather_code: int = 0            # WMO天候コード
    weather_text: str = "晴れ ☀️"    # 天候テキスト
    updated_at: Optional[datetime] = None


@dataclass
class UserSetting:
    """ユーザーごとの水分管理設定およびプロフィール"""
    user_id: str
    name: str = "ユーザー"
    daily_goal_ml: int = 2000
    gulp_ml: int = 25
    reset_time: str = "06:00"        # "HH:MM" 形式
    notification_enabled: bool = True
    notification_start: str = "08:00"# "HH:MM" 形式
    notification_end: str = "23:00"  # "HH:MM" 形式
    notification_interval: int = 60  # 分単位
    notification_mode: str = "dm"    # "dm" (Discord DM) | "channel" (チャンネル)
    presets: List[int] = field(default_factory=lambda: [100, 250, 500])
    visibility: str = "all"          # "all" | "self"

    # プロフィール項目
    gender: str = "male"             # "male" | "female"
    age: int = 25                    # 年齢
    height_cm: float = 165.0         # 身長 (cm)
    weight_kg: float = 66.0          # 体重 (kg)
    bedtime: str = "24:00"           # 就寝時間 ("HH:MM")
    activity_level: str = "medium"   # "low" | "medium" | "high"
    auto_goal_enabled: bool = True   # 自動推奨目標の有効化


@dataclass
class WaterLog:
    """水分摂取ログ"""
    id: Optional[int]
    user_id: str
    amount_ml: int
    gulp_count: Optional[int]
    recorded_at: datetime
    date_key: str                    # "YYYY-MM-DD"
    source: str = "discord"          # "discord" | "apple_watch" | "iphone" | "api" | "dm"


@dataclass
class WaterRecommendation:
    """パーソナル水分ナビゲーションの推奨結果"""
    user_id: str
    recommended_ml: int              # 次回おすすめ量 (ml)
    recommended_gulps: int           # 次回おすすめゴク数
    recommended_time_str: str        # 次回おすすめ時刻 (例: "17:00頃")
    recommended_dt: Optional[datetime] # 次回おすすめ日時
    status_summary: str              # 状態要約
    daily_recommended_goal_ml: int   # 当日のパーソナル推奨1日目標 (ml)
    weather_summary: str             # 気象サマリー
    is_bedtime_near: bool = False    # 就寝時間が近いか


@dataclass
class DailyProgress:
    """当日の進捗状況"""
    user_id: str
    name: str
    date_key: str
    total_ml: int
    goal_ml: int
    remaining_ml: int
    percentage: float
    is_achieved: bool
    is_first_achievement: bool
    last_recorded_at: Optional[datetime]
    logs: List[WaterLog] = field(default_factory=list)
    recommendation: Optional[WaterRecommendation] = None


@dataclass
class ChannelSetting:
    """水分管理パネルを設置しているチャンネル情報"""
    guild_id: int
    channel_id: int
    message_id: Optional[int] = None