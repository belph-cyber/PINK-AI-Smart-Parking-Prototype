# -*- coding: utf-8 -*-
"""
PINK AI: Weather Service
- Connects to Open-Meteo API for real live weather data
- In-memory cache with configurable TTL (default 20 minutes)
- Graceful offline fallback to last cached data
- Standalone service architecture
"""

import time
import json
import logging
import urllib.request
from typing import Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger("weather_service")

# University campus reference coordinates (Bangkok campus)
CAMPUS_LATITUDE = 13.7563
CAMPUS_LONGITUDE = 100.5018
CACHE_TTL_SECONDS = 20 * 60  # 20 minutes cache

# In-memory weather cache
_weather_cache: Dict[str, Any] = {
    "data": None,
    "last_fetched": 0.0
}

WMO_WEATHER_MAP = {
    0: ("ท้องฟ้าแจ่มใส", "Clear Sky", "fa-sun", "#F59E0B"),
    1: ("แดดออก มีเมฆบางส่วน", "Mainly Clear", "fa-cloud-sun", "#F59E0B"),
    2: ("มีเมฆเป็นส่วนมาก", "Partly Cloudy", "fa-cloud-sun", "#F59E0B"),
    3: ("มีเมฆมาก", "Overcast", "fa-cloud", "#94A3B8"),
    45: ("หมอกลง", "Fog", "fa-smog", "#94A3B8"),
    48: ("หมอกหนา", "Depositing Rime Fog", "fa-smog", "#94A3B8"),
    51: ("ฝนปรอยเบาบาง", "Light Drizzle", "fa-cloud-rain", "#38BDF8"),
    53: ("ฝนปรอยปานกลาง", "Moderate Drizzle", "fa-cloud-rain", "#38BDF8"),
    55: ("ฝนปรอยหนาแน่น", "Dense Drizzle", "fa-cloud-showers-heavy", "#38BDF8"),
    61: ("ฝนตกเล็กน้อย", "Slight Rain", "fa-cloud-rain", "#38BDF8"),
    63: ("ฝนตกปานกลาง", "Moderate Rain", "fa-cloud-showers-heavy", "#38BDF8"),
    65: ("ฝนตกหนัก", "Heavy Rain", "fa-cloud-showers-heavy", "#38BDF8"),
    80: ("ฝนฟ้าคะนองกระจาย", "Slight Rain Showers", "fa-cloud-showers-water", "#38BDF8"),
    81: ("ฝนตกชุก", "Moderate Rain Showers", "fa-cloud-showers-water", "#38BDF8"),
    82: ("ฝนตกหนักมาก", "Violent Rain Showers", "fa-cloud-showers-water", "#38BDF8"),
    95: ("พายุฝนฟ้าคะนอง", "Thunderstorm", "fa-cloud-bolt", "#8B5CF6")
}

def get_live_weather(force_refresh: bool = False) -> Dict[str, Any]:
    """Retrieve weather data with caching mechanism"""
    now = time.time()
    cached = _weather_cache.get("data")
    last_fetched = _weather_cache.get("last_fetched", 0.0)

    # Return cached data if still fresh
    if not force_refresh and cached and (now - last_fetched < CACHE_TTL_SECONDS):
        cached["is_cached"] = True
        cached["cache_age_min"] = round((now - last_fetched) / 60, 1)
        return cached

    # Fetch fresh data from Open-Meteo
    url = (
        f"https://api.open-meteo.com/v1/forecast?"
        f"latitude={CAMPUS_LATITUDE}&longitude={CAMPUS_LONGITUDE}"
        f"&current=temperature_2m,relative_humidity_2m,apparent_temperature,precipitation,weather_code,wind_speed_10m"
        f"&daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max"
        f"&timezone=Asia%2FBangkok"
    )

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "PinkAISmartParking/2.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        current = data.get("current", {})
        daily = data.get("daily", {})

        wcode = current.get("weather_code", 1)
        wdesc_th, wdesc_en, wicon, wcolor = WMO_WEATHER_MAP.get(wcode, ("สภาพอากาศปกติ", "Clear", "fa-cloud-sun", "#F59E0B"))

        # Daily forecast (3 days)
        forecast_days = []
        dates = daily.get("time", [])[:4]
        max_temps = daily.get("temperature_2m_max", [])[:4]
        min_temps = daily.get("temperature_2m_min", [])[:4]
        precips = daily.get("precipitation_probability_max", [])[:4]
        daily_codes = daily.get("weather_code", [])[:4]

        day_names_th = ["อา.", "จ.", "อ.", "พ.", "พฤ.", "ศ.", "ส."]
        for i in range(1, min(4, len(dates))):
            dt = datetime.strptime(dates[i], "%Y-%m-%d")
            day_str = day_names_th[dt.weekday()]
            dc = daily_codes[i] if i < len(daily_codes) else 1
            _, _, dicon, _ = WMO_WEATHER_MAP.get(dc, ("แจ่มใส", "Clear", "fa-sun", "#F59E0B"))
            forecast_days.append({
                "date": dates[i],
                "day_label": day_str,
                "max_temp": round(max_temps[i]) if i < len(max_temps) else 30,
                "min_temp": round(min_temps[i]) if i < len(min_temps) else 24,
                "precip_prob": precips[i] if i < len(precips) else 0,
                "icon": dicon
            })

        today_max = round(max_temps[0]) if max_temps else round(current.get("temperature_2m", 28) + 4)
        today_min = round(min_temps[0]) if min_temps else round(current.get("temperature_2m", 28) - 4)

        result = {
            "status": "ONLINE",
            "is_cached": False,
            "cache_age_min": 0.0,
            "location": "มหาวิทยาลัย (พิกัดวิทยาเขต)",
            "temperature": round(current.get("temperature_2m", 28.0), 1),
            "feels_like": round(current.get("apparent_temperature", 30.0), 1),
            "humidity": current.get("relative_humidity_2m", 65),
            "wind_speed": round(current.get("wind_speed_10m", 5.0), 1),
            "weather_code": wcode,
            "weather_desc": wdesc_th,
            "weather_desc_en": wdesc_en,
            "weather_icon": wicon,
            "weather_color": wcolor,
            "today_max": today_max,
            "today_min": today_min,
            "rain_probability": precips[0] if precips else 10,
            "forecast": forecast_days,
            "updated_at": datetime.now().strftime("%H:%M น.")
        }

        _weather_cache["data"] = result
        _weather_cache["last_fetched"] = now
        logger.info("[WEATHER] Successfully refreshed Open-Meteo cache (temp=%.1f°C)", result["temperature"])
        return result

    except Exception as e:
        logger.warning("[WEATHER] Could not connect to Open-Meteo API: %s", e)
        if cached:
            cached["is_cached"] = True
            cached["cache_age_min"] = round((now - last_fetched) / 60, 1)
            cached["status"] = "CACHED_FALLBACK"
            return cached
        else:
            return {
                "status": "OFFLINE",
                "is_cached": False,
                "location": "มหาวิทยาลัย",
                "temperature": 28.0,
                "humidity": 60,
                "wind_speed": 4.5,
                "weather_desc": "Not Connected (Weather Unavailable)",
                "weather_desc_en": "Weather Unavailable",
                "weather_icon": "fa-cloud",
                "today_max": 32,
                "today_min": 25,
                "rain_probability": 0,
                "forecast": [],
                "updated_at": "ยังไม่ได้เชื่อมต่อ"
            }

