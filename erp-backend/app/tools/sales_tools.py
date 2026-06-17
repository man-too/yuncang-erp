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

    if group_by == "day":
        # Fill missing days with 0 for daily granularity
        sales_map = {}
        for r in rows:
            period_str = str(r.period)
            sales_map[period_str] = {"quantity": float(r.qty or 0), "amount": float(r.amount or 0)}

        items = []
        current = since
        end = date.today()
        while current <= end:
            key = str(current)
            entry = sales_map.get(key, {"quantity": 0.0, "amount": 0.0})
            items.append({"date": key, "quantity": entry["quantity"], "amount": entry["amount"]})
            current += timedelta(days=1)
    else:
        items = [{"date": str(r.period), "quantity": float(r.qty or 0), "amount": float(r.amount or 0)} for r in rows]

    total_qty = sum(it["quantity"] for it in items)
    total_amount = sum(it["amount"] for it in items)

    return {"items": items, "total_quantity": total_qty, "total_amount": total_amount, "days": days}


def _wma_fallback(history: list[dict], days: int = 30, product_name: str | None = None, product_id: int | None = None, db: Session | None = None) -> list[int]:
    """加权移动平均预测，优先使用 ForecastService（Prophet/NaiveSeasonal），不可用时回退经典 WMA"""
    # 优先使用 ForecastService（db + product_id 可用时）
    if db is not None and product_id is not None:
        try:
            from app.services.forecast_service import forecast_product_demand
            result = forecast_product_demand(product_id, db, horizon_days=days)
            if result is not None and result.forecast_mid:
                return [max(0, round(v)) for v in result.forecast_mid]
        except Exception:
            pass

    # 回退：经典 WMA
    weights = [0.20, 0.22, 0.18, 0.15, 0.12, 0.08, 0.05]
    quantities = [h.get("quantity", 0) for h in history]
    recent = quantities[-7:]
    while len(recent) < 7:
        recent.insert(0, recent[0] if recent else 0)
    w = weights[:len(recent)]
    wma = sum(wi * val for wi, val in zip(w, recent)) / sum(w)
    base = max(0, round(wma))

    predictions = []
    for i in range(days):
        decay = 0.98 ** (i // 7)
        predictions.append(max(0, round(base * decay)))
    return predictions


def _forecast_sales(args: dict, db: Session) -> dict:
    """WMA-based sales forecast (deterministic, no LLM)"""

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

    # Fill complete date range with 0 for missing days
    sales_map = {r[0]: float(r[1] or 0) for r in rows}
    history = []
    current = since
    end = date.today()
    while current <= end:
        history.append({"date": str(current), "quantity": sales_map.get(current, 0.0)})
        current += timedelta(days=1)

    # Use ForecastService (Prophet/NaiveSeasonal) with WMA fallback
    predictions = _wma_fallback(history, 30, product_name=prod.name, product_id=prod.id, db=db)

    # Determine trend from recent data
    if len(history) >= 14:
        recent_qty = sum(h["quantity"] for h in history[-7:])
        earlier_qty = sum(h["quantity"] for h in history[:7])
        if earlier_qty > 0:
            change_pct = (recent_qty - earlier_qty) / earlier_qty * 100
            if change_pct > 10:
                trend = "上升"
            elif change_pct < -10:
                trend = "下降"
            else:
                trend = "平稳"
        else:
            trend = "数据不足"
    else:
        trend = "数据不足"

    # Generate prediction dates
    last_date = rows[-1][0] if rows else date.today()
    prediction_dates = [(last_date + timedelta(days=i + 1)).strftime("%Y-%m-%d") for i in range(len(predictions))]

    return {
        "product_id": prod.id,
        "product_name": prod.name,
        "history": history[-30:],
        "forecast_next_30d": sum(predictions) if predictions else 0,
        "predictions": predictions,
        "prediction_dates": prediction_dates,
        "trend": trend,
        "seasonal_factor": "",
        "suggestion": f"基于WMA预测未来30天需求约{sum(predictions)}件，趋势{trend}",
        "confidence": 0.85 if len(history) >= 14 else 0.5,
    }
