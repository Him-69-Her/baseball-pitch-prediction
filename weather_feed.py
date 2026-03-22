"""
TINY-HUB-NETWORK — Real-Time Weather Feed
Pulls live cloud cover, temperature, and Direct Normal Irradiance
from Open-Meteo API (free, no API key required).

Usage:
    from weather_feed import get_weather

    w = get_weather(40.65, -89.50)  # D91 Peoria
    # w = {"cloud_cover": 45, "temperature": 22.3, "dni": 512.0, "source": "open-meteo"}

Caches results for 10 minutes per location (rounded to 0.1° grid).
Falls back to simulation if API is unreachable.
"""

import time
import random
import threading

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

# ── Cache ───────────────────────────────────────────────────
_cache = {}
_cache_lock = threading.Lock()
CACHE_TTL = 600  # 10 minutes

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"


def _cache_key(lat, lng):
    """Round to 0.1° grid for caching."""
    return (round(lat, 1), round(lng, 1))


def _fetch_weather(lat, lng):
    """Fetch current weather from Open-Meteo."""
    if not HAS_REQUESTS:
        return None

    try:
        params = {
            "latitude": round(lat, 4),
            "longitude": round(lng, 4),
            "current": "cloud_cover,temperature_2m,direct_normal_irradiance",
            "timezone": "UTC",
        }
        r = requests.get(OPEN_METEO_URL, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
        current = data.get("current", {})

        result = {
            "cloud_cover": current.get("cloud_cover", 50),       # 0-100%
            "temperature": current.get("temperature_2m", 20.0),   # °C
            "dni": current.get("direct_normal_irradiance", 0.0),  # W/m²
            "source": "open-meteo",
            "fetched_at": time.time(),
        }
        return result

    except Exception as e:
        return None


def get_weather(lat, lng):
    """
    Get current weather for a location.
    Returns dict with cloud_cover (0-100), temperature (°C), dni (W/m²), source.
    Caches per 0.1° grid cell for 10 minutes.
    Falls back to simulated weather if API unreachable.
    """
    key = _cache_key(lat, lng)

    with _cache_lock:
        if key in _cache:
            cached = _cache[key]
            age = time.time() - cached["fetched_at"]
            if age < CACHE_TTL:
                return cached

    # Fetch fresh
    result = _fetch_weather(lat, lng)
    if result:
        with _cache_lock:
            _cache[key] = result
        return result

    # Fallback: simulated weather
    return {
        "cloud_cover": random.choices(
            [random.uniform(5, 20), random.uniform(30, 60), random.uniform(70, 95)],
            weights=[0.5, 0.35, 0.15]
        )[0],
        "temperature": random.uniform(10, 30),
        "dni": random.uniform(0, 800),
        "source": "simulated",
        "fetched_at": time.time(),
    }


def cloud_factor(cloud_cover_pct):
    """
    Convert cloud cover percentage (0-100) to a solar output multiplier (0-1).
    0% cloud = 0.95 factor, 100% cloud = 0.10 factor.
    """
    return max(0.10, 1.0 - (cloud_cover_pct / 100) * 0.90)


def print_weather_status(lat, lng, label=""):
    """Print current weather for debugging."""
    w = get_weather(lat, lng)
    src = "🛰️" if w["source"] == "open-meteo" else "📊"
    prefix = f"  [{label}] " if label else "  "
    print(f"{prefix}{src} Weather: {w['cloud_cover']:.0f}% cloud, {w['temperature']:.1f}°C, DNI {w['dni']:.0f} W/m² ({w['source']})")
    return w
