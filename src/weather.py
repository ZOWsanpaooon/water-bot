"""
気象情報連携モジュール (Weather Service)
東京都大田区西蒲田の気象データを自動取得・キャッシュ
"""

import json
import urllib.request
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Optional
from src.models import JST, get_current_jst_time, WeatherInfo

# 東京都大田区西蒲田の座標
NISHIKAMATA_LAT = 35.5625
NISHIKAMATA_LON = 139.7158

# WMO Weather Interpretation Codes (WW)
# https://open-meteo.com/en/docs → weathercode
WMO_WEATHER_MAP = {
    0: "快晴 ☀️",
    1: "概ね晴れ 🌤️",
    2: "時々曇り ⛅",
    3: "曇り ☁️",
    45: "霧 🌫️",
    48: "濃霧 🌫️",
    51: "小雨 🌦️",
    53: "雨 🌧️",
    55: "強い雨 🌧️",
    56: "凍雨 🌧️",
    57: "強い凍雨 🌧️",
    61: "小雨 🌧️",
    63: "雨 🌧️",
    65: "大雨 🌧️",
    66: "冷たい雨 🌧️",
    67: "激しい凍雨 🌧️",
    71: "小雪 🌨️",
    73: "雪 🌨️",
    75: "大雪 🌨️",
    77: "雪の粒 🌨️",
    80: "にわか雨 🌦️",
    81: "にわか雨 🌧️",
    82: "激しいにわか雨 🌧️",
    85: "にわか雪 🌨️",
    86: "激しいにわか雪 🌨️",
    95: "雷雨 ⛈️",
    96: "雷雨・雹 ⛈️",
    99: "激しい雷雨・雹 ⛈️",
}


class WeatherService:
    """気象情報自動取得＆キャッシュサービス"""

    def __init__(self, cache_ttl_minutes: int = 20):
        self.cache_ttl = timedelta(minutes=cache_ttl_minutes)
        self._cached_weather: Optional[WeatherInfo] = None
        self._last_fetched_at: Optional[datetime] = None
        self._lock = asyncio.Lock()

    def _parse_api_response(self, data: dict) -> WeatherInfo:
        current = data.get("current", {})
        daily = data.get("daily", {})

        curr_temp = float(current.get("temperature_2m", 20.0))
        apparent_temp = float(current.get("apparent_temperature", curr_temp))
        humidity = int(current.get("relative_humidity_2m", 50))
        code = int(current.get("weather_code", 0))

        max_temps = daily.get("temperature_2m_max", [curr_temp + 3.0])
        min_temps = daily.get("temperature_2m_min", [curr_temp - 3.0])

        max_temp = float(max_temps[0]) if max_temps else curr_temp + 3.0
        min_temp = float(min_temps[0]) if min_temps else curr_temp - 3.0
        weather_text = WMO_WEATHER_MAP.get(code, "晴れ ☀️")

        return WeatherInfo(
            current_temp=curr_temp,
            max_temp=max_temp,
            min_temp=min_temp,
            humidity=humidity,
            apparent_temp=apparent_temp,
            weather_code=code,
            weather_text=weather_text,
            updated_at=get_current_jst_time()
        )

    def get_weather_sync(self) -> WeatherInfo:
        """同期的に気象情報を取得（キャッシュがあればそれを返す）"""
        now = get_current_jst_time()
        if self._cached_weather and self._last_fetched_at:
            if now - self._last_fetched_at < self.cache_ttl:
                return self._cached_weather

        url = (
            f"https://api.open-meteo.com/v1/forecast?latitude={NISHIKAMATA_LAT}&longitude={NISHIKAMATA_LON}"
            f"&current=temperature_2m,relative_humidity_2m,apparent_temperature,weather_code"
            f"&daily=temperature_2m_max,temperature_2m_min&timezone=Asia%2FTokyo"
        )

        try:
            req = urllib.request.Request(url, headers={"User-Agent": "WaterBot2.1/FadeHost"})
            with urllib.request.urlopen(req, timeout=5) as response:
                if response.status == 200:
                    raw_data = response.read().decode("utf-8")
                    data = json.loads(raw_data)
                    weather = self._parse_api_response(data)
                    self._cached_weather = weather
                    self._last_fetched_at = now
                    return weather
        except Exception:
            pass

        if self._cached_weather:
            return self._cached_weather

        fallback = WeatherInfo(
            current_temp=22.0,
            max_temp=25.0,
            min_temp=18.0,
            humidity=55,
            apparent_temp=22.0,
            weather_code=0,
            weather_text="晴れ ☀️",
            updated_at=now
        )
        self._cached_weather = fallback
        self._last_fetched_at = now
        return fallback

    async def get_weather_async(self) -> WeatherInfo:
        """非同期で気象情報を取得"""
        async with self._lock:
            now = get_current_jst_time()
            if self._cached_weather and self._last_fetched_at:
                if now - self._last_fetched_at < self.cache_ttl:
                    return self._cached_weather

            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(None, self.get_weather_sync)


weather_service = WeatherService()