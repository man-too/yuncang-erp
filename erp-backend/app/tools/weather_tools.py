"""天气查询 LLM 工具注册

注册 query_weather 为 Function Calling 工具，
内部调用 weather_service 的异步方法。

注意：weather_service 是 async 的（httpx），
本模块的 execute() 是同步接口（由 chat_service 调用）。
用独立线程 + 独立 DB session 执行异步调用，避免跨线程共享 Session。
"""

import asyncio
import concurrent.futures
from sqlalchemy.orm import Session

from app.services.weather_service import query_weather as _query_weather_async


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "query_weather",
            "description": "查询指定城市未来7天天气预报，并自动分析受天气影响的产品品类（如冷饮受高温影响、雨具受降雨影响）。当用户询问天气、天气对产品的影响、或需要根据天气做采购决策时调用",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {
                        "type": "string",
                        "description": "城市名称（中文），如：上海、北京、广州",
                    },
                    "days": {
                        "type": "integer",
                        "description": "预报天数，1-16，默认7",
                        "default": 7,
                    },
                },
                "required": ["city"],
            },
        },
    },
]


def _run_async_in_thread(city: str, days: int) -> dict:
    """在独立线程中运行异步查询，每次创建独立 DB session"""
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        return asyncio.run(_query_weather_async(city, days, db))
    finally:
        db.close()


def execute(name: str, args: dict, db: Session) -> dict | None:
    """执行天气工具 — 同步接口

    使用独立线程 + 独立 Session 执行异步 httpx 调用，
    避免将 FastAPI 线程的 Session 传入子线程。
    """
    if name != "query_weather":
        return None

    city = args.get("city", "")
    days = args.get("days", 7)

    try:
        with concurrent.futures.ThreadPoolExecutor() as pool:
            future = pool.submit(_run_async_in_thread, city, days)
            return future.result(timeout=20)
    except concurrent.futures.TimeoutError:
        return {"city": city, "error": "天气查询超时，请稍后重试"}
    except Exception as e:
        return {"city": city, "error": f"天气查询失败: {str(e)}"}