"""销售历史与预测工具"""
from datetime import date, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.models.sale import SaleOrder, SaleOrderItem
from app.models.product import Product

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "query_sales_history",
            "description": "查询销售数据，包括销量、销售金额、卖了多少、什么卖得好等。返回按日期聚合的销量和金额，可按产品筛选、设定回溯天数。用户问销量相关数值问题时优先使用此工具，不要用 render_sales_trend",
            "parameters": {
                "type": "object",
                "properties": {
                    "product_id": {"type": "integer", "description": "产品ID，可选"},
                    "days": {"type": "integer", "description": "回溯天数，默认90"},
                    "group_by": {"type": "string", "enum": ["day", "week", "month"], "description": "聚合粒度，默认day"},
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "forecast_sales",
            "description": "基于历史销售数据进行AI销售预测，返回30天预测数量、趋势判断和采购建议",
            "parameters": {
                "type": "object",
                "properties": {
                    "product_id": {"type": "integer", "description": "产品ID"},
                },
                "required": ["product_id"]
            }
        }
    },
]


def execute(name: str, args: dict, db: Session) -> dict | None:
    if name == "query_sales_history":
        return _query_sales_history(args, db)
    if name == "forecast_sales":
        return _forecast_sales(args, db)
    return None


def _query_sales_history(args: dict, db: Session) -> dict:
    days = args.get("days", 90)
    group_by = args.get("group_by", "day")
    since = date.today() - timedelta(days=days)

    q = db.query(
        func.sum(SaleOrderItem.quantity).label("qty"),
        func.sum(SaleOrderItem.total_price).label("amount"),
    ).join(SaleOrderItem, SaleOrderItem.order_id == SaleOrder.id)

    if args.get("product_id"):
        q = q.filter(SaleOrderItem.product_id == args["product_id"])
    q = q.filter(SaleOrder.order_date >= since, SaleOrder.status != "cancelled")

    if group_by == "month":
        date_label = func.date_format(SaleOrder.order_date, "%Y-%m")
    elif group_by == "week":
        date_label = func.date_format(SaleOrder.order_date, "%Y-%U")
    else:
        date_label = SaleOrder.order_date

    q = q.add_columns(date_label.label("period"))
    q = q.group_by(date_label).order_by(date_label)
    rows = q.limit(366).all()

    items = [{"date": str(r.period), "quantity": float(r.qty or 0), "amount": float(r.amount or 0)} for r in rows]

    total_qty = sum(it["quantity"] for it in items)
    total_amount = sum(it["amount"] for it in items)

    return {"items": items, "total_quantity": total_qty, "total_amount": total_amount, "days": days}


def _wma_fallback(history: list[dict], days: int = 30, product_name: str | None = None) -> list[int]:
    """加权移动平均预测：最近7天数据，权重 [0.20, 0.22, 0.18, 0.15, 0.12, 0.08, 0.05]（最近→最远递减），>7天时每7天衰减0.98"""
    weights = [0.20, 0.22, 0.18, 0.15, 0.12, 0.08, 0.05]  # 最近→最远，权重递减
    quantities = [h.get("quantity", 0) for h in history]
    recent = quantities[-7:]
    # Pad with earliest value if fewer than 7 data points
    while len(recent) < 7:
        recent.insert(0, recent[0] if recent else 0)
    w = weights[:len(recent)]  # 取前 len(recent) 个权重（最近数据对应最大权重）
    wma = sum(wi * val for wi, val in zip(w, recent)) / sum(w)
    base = max(0, round(wma))

    predictions = []
    for i in range(days):
        decay = 0.98 ** (i // 7)  # 每7天衰减一次
        predictions.append(max(0, round(base * decay)))
    return predictions


def _forecast_sales(args: dict, db: Session) -> dict:
    from app.services.ai_service import sales_forecast

    prod = db.query(Product).filter(Product.id == args["product_id"]).first()
    if not prod:
        return {"error": f"产品 {args['product_id']} 不存在"}

    days = 90
    since = date.today() - timedelta(days=days)
    rows = (
        db.query(SaleOrder.order_date, func.sum(SaleOrderItem.quantity))
        .join(SaleOrderItem, SaleOrderItem.order_id == SaleOrder.id)
        .filter(SaleOrderItem.product_id == args["product_id"])
        .filter(SaleOrder.order_date >= since)
        .group_by(SaleOrder.order_date)
        .order_by(SaleOrder.order_date)
        .all()
    )
    history = [{"date": str(r[0]), "quantity": float(r[1] or 0)} for r in rows]

    ai = sales_forecast(product_name=prod.name, history_sales=history)

    # Determine predictions: AI first, WMA fallback
    predictions = []
    if ai and ai.get("predictions"):
        predictions = ai["predictions"]
    else:
        predictions = _wma_fallback(history, 30, product_name=prod.name)

    # Generate prediction dates
    last_date = rows[-1][0] if rows else date.today()
    prediction_dates = [(last_date + timedelta(days=i + 1)).strftime("%Y-%m-%d") for i in range(len(predictions))]

    if ai is None:
        ai = {}

    return {
        "product_id": prod.id,
        "product_name": prod.name,
        "history": history[-30:],
        "forecast_next_30d": ai.get("forecast_next_30d", sum(predictions) if predictions else 0),
        "predictions": predictions,
        "prediction_dates": prediction_dates,
        "trend": ai.get("trend", "未知"),
        "seasonal_factor": ai.get("seasonal_factor", ""),
        "suggestion": ai.get("suggestion", ""),
        "confidence": ai.get("confidence", 0),
    }
