"""天气查询工具 — 调用 Open-Meteo 免费 API

功能:
- query_weather: 查询指定城市未来 N 天天气预报
- 自动反向查询 weather_sensitive 产品，输出受影响品类
"""

import json
import httpx
from datetime import date
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models.product import Product, ProductCategory


# ────────────────────────────────────────────
# 城市名 → 经纬度 (常用中国城市)
# ────────────────────────────────────────────
CITY_COORDS = {
    "北京": (39.9042, 116.4074),
    "上海": (31.2304, 121.4737),
    "广州": (23.1291, 113.2644),
    "深圳": (22.5431, 114.0579),
    "杭州": (30.2741, 120.1551),
    "成都": (30.5728, 104.0668),
    "武汉": (30.5928, 114.3055),
    "南京": (32.0603, 118.7969),
    "重庆": (29.4316, 106.9123),
    "天津": (39.3434, 117.3616),
    "苏州": (31.2990, 120.5853),
    "西安": (34.3416, 108.9398),
    "长沙": (28.2282, 112.9388),
    "郑州": (34.7466, 113.6254),
    "青岛": (36.0671, 120.3826),
    "大连": (38.9140, 121.6147),
    "厦门": (24.4798, 118.0894),
    "昆明": (25.0389, 102.7183),
    "哈尔滨": (45.8038, 126.5350),
    "沈阳": (41.8057, 123.4315),
    "济南": (36.6512, 116.9972),
    "福州": (26.0745, 119.2965),
    "合肥": (31.8206, 117.2272),
    "南宁": (22.8170, 108.3665),
    "贵阳": (26.6470, 106.6302),
    "太原": (37.8706, 112.5489),
    "石家庄": (38.0428, 114.5149),
    "兰州": (36.0611, 103.8343),
    "海口": (20.0174, 110.3492),
    "三亚": (18.2528, 109.5120),
    "拉萨": (29.6500, 91.1000),
    "乌鲁木齐": (43.8256, 87.6168),
    "呼和浩特": (40.8424, 111.7490),
}

# 天气编码 → 中文 (WMO weather_code)
WEATHER_CODE_MAP = {
    0: "晴", 1: "大部晴", 2: "多云", 3: "阴",
    45: "雾", 48: "雾凇",
    51: "小毛毛雨", 53: "毛毛雨", 55: "大毛毛雨",
    56: "冻毛毛雨", 57: "强冻毛毛雨",
    61: "小雨", 63: "中雨", 65: "大雨",
    66: "冻雨", 67: "强冻雨",
    71: "小雪", 73: "中雪", 75: "大雪",
    77: "冰粒",
    80: "阵雨", 81: "中阵雨", 82: "强阵雨",
    85: "小阵雪", 86: "大阵雪",
    95: "雷暴", 96: "雷暴+冰雹", 99: "强雷暴+冰雹",
}

# 天气关键词 → weather_type 映射
WEATHER_TYPE_MAP = {
    "hot": [],  # 高温仅由温度判断（≥35°C），不通过天气描述匹配
    "rain": ["小雨", "中雨", "大雨", "阵雨", "中阵雨", "强阵雨",
             "小毛毛雨", "毛毛雨", "大毛毛雨",
             "冻毛毛雨", "强冻毛毛雨", "冻雨", "强冻雨",
             "雷暴", "雷暴+冰雹", "强雷暴+冰雹"],
    "cold": ["小雪", "中雪", "大雪", "冰粒", "小阵雪", "大阵雪",
             "冻毛毛雨", "强冻毛毛雨", "冻雨", "强冻雨"],
}


async def query_weather(city: str, days: int = 7, db: Session | None = None) -> dict:
    """查询天气并返回受影响产品

    Args:
        city: 城市名（中文）
        days: 预报天数 (1-16)
        db: 数据库会话，用于查询受影响产品
    """
    coords = CITY_COORDS.get(city)
    if not coords:
        return {
            "city": city,
            "error": f"未找到城市「{city}」的坐标，支持的城市：{', '.join(list(CITY_COORDS.keys())[:10])}等"
        }

    lat, lon = coords
    days = min(max(days, 1), 16)

    try:
        async with httpx.AsyncClient(timeout=10) as http_client:
            resp = await http_client.get(
                "https://api.open-meteo.com/v1/forecast",
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
                    "timezone": "Asia/Shanghai",
                    "forecast_days": days,
                },
            )
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError as e:
        return {"city": city, "error": f"天气 API 请求失败: {e}"}
    except (json.JSONDecodeError, KeyError, ValueError) as e:
        return {"city": city, "error": f"天气数据解析失败: {e}"}
    except Exception as e:
        return {"city": city, "error": f"天气查询异常: {e}"}

    daily = data.get("daily", {})
    dates = daily.get("time", [])
    weather_codes = daily.get("weather_code", [])
    temp_maxs = daily.get("temperature_2m_max", [])
    temp_mins = daily.get("temperature_2m_min", [])
    precip_probs = daily.get("precipitation_probability_max", [])

    forecast = []
    for i in range(len(dates)):
        code = weather_codes[i] if i < len(weather_codes) else 0
        weather_desc = WEATHER_CODE_MAP.get(code, "未知")
        forecast.append({
            "date": dates[i],
            "temp_high": temp_maxs[i] if i < len(temp_maxs) else None,
            "temp_low": temp_mins[i] if i < len(temp_mins) else None,
            "weather": weather_desc,
            "weather_code": code,
            "precip_prob": precip_probs[i] if i < len(precip_probs) else None,
        })

    # ── 自动生成摘要 ──
    summary = _generate_summary(forecast)

    result = {
        "city": city,
        "forecast": forecast,
        "summary": summary,
    }

    # ── 查询受影响产品 ──
    if db:
        affected = _find_affected_products(forecast, db)
        if affected:
            result["affected_products"] = affected

    return result


def _generate_summary(forecast: list[dict]) -> str:
    """生成天气预报摘要"""
    if not forecast:
        return "无预报数据"

    # 检测高温
    hot_days = [f for f in forecast if (f.get("temp_high") or 0) >= 35]
    # 检测降雨
    rain_days = [f for f in forecast if f.get("precip_prob", 0) >= 60]
    # 检测低温
    cold_days = [f for f in forecast if (f.get("temp_low") or 99) <= 0]

    parts = []
    if hot_days:
        parts.append(f"未来{len(forecast)}天内有{len(hot_days)}天高温(≥35°C)")
    if rain_days:
        parts.append(f"有{len(rain_days)}天降雨概率≥60%")
    if cold_days:
        parts.append(f"有{len(cold_days)}天低温(≤0°C)")

    if not parts:
        parts.append("未来天气平稳，无极端天气")

    return "；".join(parts)


def _find_affected_products(forecast: list[dict], db: Session) -> list[dict]:
    """根据天气预报反向查询受影响的产品"""
    # 从预报中提取出现的天气类型
    active_weather_types = set()
    for f in forecast:
        desc = f.get("weather", "")
        for wtype, keywords in WEATHER_TYPE_MAP.items():
            if any(kw in desc for kw in keywords):
                active_weather_types.add(wtype)

    # 检测高温
    for f in forecast:
        if (f.get("temp_high") or 0) >= 35:
            active_weather_types.add("hot")

    # 检测低温
    for f in forecast:
        if (f.get("temp_low") or 99) <= 0:
            active_weather_types.add("cold")

    if not active_weather_types:
        return []

    # 查询受影响产品 — 用 JOIN 避免 N+1
    rows = (
        db.query(Product, ProductCategory.name.label("cat_name"))
        .outerjoin(ProductCategory, Product.category_id == ProductCategory.id)
        .filter(
            Product.weather_sensitive == True,
            Product.is_active == True,
        )
        .all()
    )

    affected = []
    for p, cat_name in rows:
        # 防御：weather_type 可能是 list、str 或 dict
        wt = p.weather_type
        if wt is None:
            continue
        if isinstance(wt, list):
            matched_types = set(wt) & active_weather_types
        elif isinstance(wt, str):
            matched_types = {wt} & active_weather_types
        elif isinstance(wt, dict):
            matched_types = set(wt.keys()) & active_weather_types
        else:
            continue

        if matched_types:
            affected.append({
                "product_id": p.id,
                "product_name": p.name,
                "category": cat_name or "未分类",
                "matched_weather_types": list(matched_types),
                "suggestion": _product_suggestion(list(matched_types)),
            })

    return affected


def _product_suggestion(weather_types: list[str]) -> str:
    """根据匹配的天气类型给出补货建议"""
    suggestions = []
    if "hot" in weather_types:
        suggestions.append("高温天气，需求可能上升，建议增加库存")
    if "rain" in weather_types:
        suggestions.append("降雨天气，需求可能上升，建议增加库存")
    if "cold" in weather_types:
        suggestions.append("低温天气，需求可能上升，建议增加库存")
    return "；".join(suggestions)
