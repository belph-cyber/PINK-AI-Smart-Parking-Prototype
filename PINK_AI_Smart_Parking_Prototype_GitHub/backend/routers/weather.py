# -*- coding: utf-8 -*-
"""
PINK AI: Weather API Router
Provides cached real live weather data from Open-Meteo
"""

from fastapi import APIRouter, Query
from backend.services.weather_service import get_live_weather

router = APIRouter(prefix="/api/weather", tags=["Weather"])

@router.get("/current")
def current_weather(refresh: bool = Query(False, description="Force refresh cache")):
    """Get current campus weather and 3-day forecast with caching"""
    data = get_live_weather(force_refresh=refresh)
    return {"status": "ok", "weather": data}

