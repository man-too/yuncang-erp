"""库存查询与风险分析工具"""
from sqlalchemy.orm import Session
from sqlalchemy import or_
from app.models.inventory import Inventory, Warehouse
from app.models.product import Product
from app.models.sale import SaleOrderItem, SaleOrder


def _warehouse_name(db: Session, wid: int) -> str:
    w = db.query(Warehouse).filter(Warehouse.id == wid).first()
    return w.name if w else f"仓库#{wid}"


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "query_inventory",
            "description": "查询当前库存状态，可按产品ID、仓库ID筛选，支持仅查低库存产品。返回产品名、仓库名、库存量、最低/最高库存警戒线",
            "parameters": {
                "type": "object",
                "properties": {
                    "product_id": {"type": "integer", "description": "产品ID，可选"},
                    "warehouse_id": {"type": "integer", "description": "仓库ID，可选"},
                    "low_stock_only": {"type": "boolean", "description": "仅返回库存≤最低库存线的产品"},
                    "limit": {"type": "integer", "description": "返回条数上限，默认100"},
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_stock_risk",
            "description": "AI库存风险分析。识别缺货/低库存/积压产品，按风险等级排序并给出补货建议",
            "parameters": {
                "type": "object",
                "properties": {
                    "product_ids": {
                        "type": "array", "items": {"type": "integer"},
                        "description": "要分析的产品ID列表，为空则分析全部低库存产品"
                    },
                },
                "required": []
            }
        }
    },
]


def execute(name: str, args: dict, db: Session) -> dict | None:
    if name == "query_inventory":
        return _query_inventory(args, db)
    if name == "analyze_stock_risk":
        return _analyze_stock_risk(args, db)
    return None


def _query_inventory(args: dict, db: Session) -> dict:
    q = db.query(Inventory, Product, Warehouse).join(Product, Inventory.product_id == Product.id).outerjoin(Warehouse, Inventory.warehouse_id == Warehouse.id).filter(Warehouse.is_active == True)

    if args.get("product_id"):
        q = q.filter(Inventory.product_id == args["product_id"])
    if args.get("warehouse_id"):
        q = q.filter(Inventory.warehouse_id == args["warehouse_id"])
    if args.get("low_stock_only"):
        q = q.filter(Inventory.quantity <= Product.min_stock)

    rows = q.limit(args.get("limit", 100)).all()
    items = []
    for inv, prod, wh in rows:
        ratio = inv.quantity / prod.min_stock if prod.min_stock > 0 else 999
        if inv.quantity == 0:
            status = "缺货"
        elif ratio < 0.5:
            status = "严重不足"
        elif ratio <= 1.0:
            status = "偏低"
        elif ratio > 2.0:
            status = "偏高"
        else:
            status = "正常"

        items.append({
            "product_id": prod.id, "product_name": prod.name,
            "product_code": prod.code,
            "warehouse_id": inv.warehouse_id,
            "warehouse_name": _warehouse_name(db, inv.warehouse_id),
            "quantity": float(inv.quantity),
            "min_stock": float(prod.min_stock),
            "max_stock": float(prod.max_stock),
            "unit": prod.unit,
            "status": status,
        })

    return {"items": items, "total": len(items)}


def _analyze_stock_risk(args: dict, db: Session) -> dict:
    from app.services.ai_service import analyze_stock_alert

    # Gather low-stock items
    q = db.query(Inventory, Product).join(Product, Inventory.product_id == Product.id)
    q = q.filter(Inventory.quantity <= Product.min_stock)
    if args.get("product_ids"):
        q = q.filter(Inventory.product_id.in_(args["product_ids"]))

    rows = q.limit(20).all()

    results = []
    for inv, prod in rows:
        # Query recent 30-day sales for this product
        recent = (
            db.query(SaleOrderItem.quantity, SaleOrder.order_date)
            .join(SaleOrder, SaleOrder.id == SaleOrderItem.order_id)
            .filter(SaleOrderItem.product_id == prod.id)
            .order_by(SaleOrder.order_date.desc())
            .limit(30)
            .all()
        )
        recent_sales = [{"date": str(r[1]), "qty": float(r[0] or 0)} for r in recent]

        ai = analyze_stock_alert(
            product_name=prod.name,
            current_qty=float(inv.quantity),
            min_stock=float(prod.min_stock),
            max_stock=float(prod.max_stock),
            recent_sales=recent_sales,
        )
        results.append({
            "product_id": prod.id,
            "product_name": prod.name,
            "warehouse_id": inv.warehouse_id,
            "warehouse_name": _warehouse_name(db, inv.warehouse_id),
            "current_qty": float(inv.quantity),
            "min_stock": float(prod.min_stock),
            "alert_level": ai.get("alert_level", "warning") if ai else "warning",
            "suggested_action": ai.get("suggested_action", "") if ai else "",
            "suggested_order_qty": ai.get("suggested_order_qty", 0) if ai else 0,
            "reason": ai.get("reason", "") if ai else "",
            "confidence": ai.get("confidence", 0) if ai else 0,
        })

    # Sort by alert severity: critical first
    severity = {"critical": 0, "warning": 1, "normal": 2}
    results.sort(key=lambda r: severity.get(r["alert_level"], 9))

    return {"risk_items": results, "total": len(results)}
