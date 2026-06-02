"""AI 智能决策服务（接入大模型 API）"""
import json
import logging
from openai import OpenAI

from app.config import settings

logger = logging.getLogger(__name__)

client = None
if settings.OPENAI_API_KEY:
    client = OpenAI(api_key=settings.OPENAI_API_KEY, base_url=settings.AI_BASE_URL)


def _call_llm(system_prompt: str, user_prompt: str) -> dict | None:
    """调用大模型 API"""
    if not client:
        return {
            "status": "error",
            "error": "AI 服务未配置，请在 .env 中设置 OPENAI_API_KEY",
            "suggestion": None,
            "confidence": 0,
        }
    try:
        try:
            resp = client.chat.completions.create(
                model=settings.OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.3,
                response_format={"type": "json_object"},
            )
        except Exception as e:
            if "response_format" in str(e).lower() or "json_object" in str(e).lower():
                resp = client.chat.completions.create(
                    model=settings.OPENAI_MODEL,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=0.3,
                )
            else:
                raise
        text = resp.choices[0].message.content
        return json.loads(text)
    except Exception as e:
        logger.error(f"AI 调用失败: {e}")
        return {"status": "error", "error": str(e), "suggestion": None, "confidence": 0}


def analyze_stock_alert(product_name: str, current_qty: float, min_stock: float,
                        max_stock: float, recent_sales: list[dict]) -> dict:
    """AI 库存预警分析：判断是否要补货"""
    system_prompt = """你是一个供应链库存管理专家。分析库存数据并给出建议。
请返回 JSON 格式：{
  "alert_level": "normal/warning/critical",
  "suggested_action": "建议操作",
  "suggested_order_qty": 数量,
  "reason": "分析理由",
  "confidence": 0.0-1.0
}"""
    user_prompt = json.dumps({
        "product": product_name,
        "current_stock": current_qty,
        "min_stock": min_stock,
        "max_stock": max_stock,
        "recent_sales_30d": recent_sales,
    }, ensure_ascii=False)
    return _call_llm(system_prompt, user_prompt)


def sales_forecast(product_name: str, history_sales: list[dict]) -> dict:
    """AI 销售预测"""
    system_prompt = """你是供应链销售预测专家。根据历史销售数据预测未来需求。
请返回 JSON 格式：{
  "forecast_next_30d": 预测数量,
  "trend": "上升/下降/平稳",
  "seasonal_factor": "季节性因素说明",
  "suggestion": "采购/库存建议",
  "confidence": 0.0-1.0
}"""
    user_prompt = json.dumps({
        "product": product_name,
        "sales_history": history_sales,
    }, ensure_ascii=False)
    return _call_llm(system_prompt, user_prompt)


def recommend_supplier(products: list[dict], suppliers: list[dict]) -> dict:
    """AI 供应商推荐"""
    system_prompt = """你是供应链采购专家。根据产品需求和供应商信息推荐最佳供应商。
请返回 JSON 格式：{
  "recommendations": [
    {"supplier_id": 1, "supplier_name": "", "score": 0-100, "reason": ""}
  ],
  "summary": "总体建议",
  "confidence": 0.0-1.0
}"""
    user_prompt = json.dumps({
        "products": products,
        "available_suppliers": suppliers,
    }, ensure_ascii=False)
    return _call_llm(system_prompt, user_prompt)


def supplier_ranking_ai(suppliers: list[dict]) -> dict:
    """AI 供应商综合排名评估"""
    system_prompt = """你是供应链管理专家。根据供应商的评分、交付表现等信息，给出智能排名分析。
请返回 JSON 格式：{
  "rankings": [
    {"supplier_id": 1, "supplier_name": "", "ai_score": 0-100, "strengths": "", "weaknesses": "", "suggestion": ""}
  ],
  "summary": "综合评估总结",
  "confidence": 0.0-1.0
}"""
    user_prompt = json.dumps({"suppliers": suppliers}, ensure_ascii=False)
    return _call_llm(system_prompt, user_prompt)
