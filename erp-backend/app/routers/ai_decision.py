"""AI 智能决策路由"""
import json
from datetime import datetime, timezone, timedelta, date
from collections import defaultdict
from typing import Optional

from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import get_db
from app.models.product import Product
from app.models.supplier import Supplier, SupplierEvaluation
from app.models.purchase import PurchaseOrder, PurchaseOrderItem
from app.models.inventory import Inventory
from app.models.sale import SaleOrder, SaleOrderItem
from app.models.ai_analysis import AIDecisionRecord
from app.services.ai_service import (
    analyze_stock_alert,
    sales_forecast,
    recommend_supplier,
    supplier_ranking_ai,
)
from app.routers.auth import get_current_user
from app.models.user import User

router = APIRouter(prefix="/api/ai", tags=["AI 智能决策"])


class StockAlertBatchRequest(BaseModel):
    product_ids: list[int]


def save_decision(db: Session, decision_type: str, title: str,
                  input_data: dict, output_data: dict, related_id: int = 0) -> AIDecisionRecord:
    record = AIDecisionRecord(
        decision_type=decision_type,
        title=title,
        input_data=json.dumps(input_data, ensure_ascii=False),
        output_data=json.dumps(output_data, ensure_ascii=False),
        summary=output_data.get("suggestion") or output_data.get("summary") or output_data.get("reason") or output_data.get("error") or "AI分析完成",
        confidence=output_data.get("confidence", 0),
        related_id=related_id,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


@router.post("/stock-alert")
def ai_stock_alert(
    product_id: int = Query(...),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """AI 库存预警分析"""
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="产品不存在")

    inv = db.query(Inventory).filter(Inventory.product_id == product_id).first()
    current_qty = inv.quantity if inv else 0

    # 获取近期销售数据（简化：直接从数据库取）
    from app.models.sale import SaleOrderItem, SaleOrder
    recent_sales = (
        db.query(SaleOrderItem, SaleOrder.order_date)
        .join(SaleOrder, SaleOrder.id == SaleOrderItem.order_id)
        .filter(SaleOrderItem.product_id == product_id)
        .order_by(SaleOrder.order_date.desc())
        .limit(30)
        .all()
    )
    sales_data = [
        {"date": str(order_date), "qty": soi.quantity}
        for soi, order_date in recent_sales
    ]

    result = analyze_stock_alert(
        product_name=product.name,
        current_qty=current_qty,
        min_stock=product.min_stock,
        max_stock=product.max_stock,
        recent_sales=sales_data,
    )
    if result and result.get("status") == "error":
        raise HTTPException(status_code=503, detail=result.get("error", "AI 服务不可用"))

    record = save_decision(
        db, "stock_alert",
        f"{product.name} 库存预警分析",
        {"product_id": product_id, "current_qty": current_qty},
        result,
        product_id,
    )
    try:
        parsed_output = json.loads(record.output_data) if isinstance(record.output_data, str) else record.output_data
    except (json.JSONDecodeError, TypeError):
        parsed_output = record.output_data
    return {
        "id": record.id,
        "decision_type": record.decision_type,
        "title": record.title,
        "input_data": record.input_data,
        "output_data": parsed_output,
        "summary": record.summary,
        "confidence": record.confidence,
        "related_id": record.related_id,
        "is_applied": record.is_applied,
        "created_at": str(record.created_at) if record.created_at else None,
    }


@router.post("/stock-alert-batch")
def ai_stock_alert_batch(
    body: StockAlertBatchRequest,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """批量库存风险分析"""
    results = []

    for product_id in body.product_ids:
        try:
            product = db.query(Product).filter(Product.id == product_id).first()
            if not product:
                results.append({
                    "product_id": product_id,
                    "product_name": f"#{product_id}",
                    "status": "error",
                    "error": "产品不存在",
                })
                continue

            inv = db.query(Inventory).filter(Inventory.product_id == product_id).first()
            current_qty = inv.quantity if inv else 0

            recent_sales = (
                db.query(SaleOrderItem, SaleOrder.order_date)
                .join(SaleOrder, SaleOrder.id == SaleOrderItem.order_id)
                .filter(SaleOrderItem.product_id == product_id)
                .order_by(SaleOrder.order_date.desc())
                .limit(30)
                .all()
            )
            sales_data = [
                {"date": str(order_date), "qty": soi.quantity}
                for soi, order_date in recent_sales
            ]

            result = analyze_stock_alert(
                product_name=product.name,
                current_qty=current_qty,
                min_stock=product.min_stock,
                max_stock=product.max_stock,
                recent_sales=sales_data,
            )

            if result and result.get("status") == "error":
                results.append({
                    "product_id": product_id,
                    "product_name": product.name,
                    "current_qty": current_qty,
                    "risk_level": "unknown",
                    "suggestion": result.get("error", "AI 服务不可用"),
                    "ai_analysis": None,
                })
            else:
                results.append({
                    "product_id": product_id,
                    "product_name": product.name,
                    "current_qty": current_qty,
                    "risk_level": result.get("alert_level", "unknown") if result else "unknown",
                    "suggestion": result.get("suggestion", "") if result else "",
                    "ai_analysis": result,
                })
        except Exception:
            results.append({
                "product_id": product_id,
                "product_name": f"#{product_id}",
                "status": "error",
                "error": "AI 分析失败",
            })

    return {"results": results}


@router.post("/supplier-recommend")
def ai_supplier_recommend(
    product_id: int = Query(...),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """AI 供应商推荐"""
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="产品不存在")

    suppliers = db.query(Supplier).filter(Supplier.status == "active").all()
    supplier_data = [
        {
            "id": s.id,
            "name": s.name,
            "rating": s.rating,
            "delivery_lead_time": s.delivery_lead_time,
        }
        for s in suppliers
    ]

    result = recommend_supplier(
        [{"id": product.id, "name": product.name, "price": product.purchase_price}],
        supplier_data,
    )
    if result and result.get("status") == "error":
        raise HTTPException(status_code=503, detail=result.get("error", "AI 服务不可用"))

    record = save_decision(
        db, "supplier_recommend",
        f"{product.name} 供应商推荐",
        {"product_id": product_id},
        result,
        product_id,
    )
    try:
        parsed_output = json.loads(record.output_data) if isinstance(record.output_data, str) else record.output_data
    except (json.JSONDecodeError, TypeError):
        parsed_output = record.output_data
    return {
        "id": record.id,
        "decision_type": record.decision_type,
        "title": record.title,
        "input_data": record.input_data,
        "output_data": parsed_output,
        "summary": record.summary,
        "confidence": record.confidence,
        "related_id": record.related_id,
        "is_applied": record.is_applied,
        "created_at": str(record.created_at) if record.created_at else None,
    }


@router.get("/history")
def list_ai_history(
    decision_type: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """查看 AI 决策历史"""
    query = db.query(AIDecisionRecord)
    if decision_type:
        query = query.filter(AIDecisionRecord.decision_type == decision_type)
    return query.order_by(AIDecisionRecord.id.desc()).limit(limit).all()


@router.get("/dashboard")
def ai_dashboard(db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    """AI 决策看板：汇总信息"""
    # 低库存产品
    low_stock_products = (
        db.query(Inventory, Product)
        .join(Product, Inventory.product_id == Product.id)
        .filter(Inventory.quantity <= Product.min_stock, Product.is_active == True)
        .count()
    )
    # AI 建议统计
    total_decisions = db.query(AIDecisionRecord).count()
    high_confidence = db.query(AIDecisionRecord).filter(
        AIDecisionRecord.confidence >= 0.7
    ).count()
    # 总库存数
    total_products = db.query(Inventory).count()

    return {
        "low_stock_count": low_stock_products,
        "total_decisions": total_decisions,
        "high_confidence_decisions": high_confidence,
        "total_inventory_items": total_products,
    }


@router.get("/supplier-analysis")
def ai_supplier_analysis(
    supplier_id: Optional[int] = Query(None, description="供应商ID"),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """供应商多维度分析数据"""
    eval_query = db.query(SupplierEvaluation)
    if supplier_id:
        eval_query = eval_query.filter(SupplierEvaluation.supplier_id == supplier_id)

    evaluations = eval_query.all()
    agg = defaultdict(lambda: {"quality": [], "delivery": [], "price": [], "service": [], "total": []})
    for e in evaluations:
        agg[e.supplier_id]["quality"].append(e.quality_score)
        agg[e.supplier_id]["delivery"].append(e.delivery_score)
        agg[e.supplier_id]["price"].append(e.price_score)
        agg[e.supplier_id]["service"].append(e.service_score)
        agg[e.supplier_id]["total"].append(e.total_score)

    suppliers = db.query(Supplier).all()
    sup_map = {s.id: s for s in suppliers}

    # Compute purchase-order derived metrics
    po_stats = defaultdict(lambda: {"total_orders": 0, "completed_orders": 0, "total_qty": 0, "received_qty": 0})
    pos = db.query(PurchaseOrder).all()
    order_supplier = {}
    for po in pos:
        po_stats[po.supplier_id]["total_orders"] += 1
        if po.status == "completed":
            po_stats[po.supplier_id]["completed_orders"] += 1
        order_supplier[po.id] = po.supplier_id

    po_items = db.query(PurchaseOrderItem).all()
    item_by_order = defaultdict(lambda: {"total_qty": 0, "received_qty": 0})
    for item in po_items:
        item_by_order[item.order_id]["total_qty"] += item.quantity
        item_by_order[item.order_id]["received_qty"] += item.received_quantity

    for order_id, qtys in item_by_order.items():
        sid = order_supplier.get(order_id)
        if sid:
            po_stats[sid]["total_qty"] += qtys["total_qty"]
            po_stats[sid]["received_qty"] += qtys["received_qty"]

    result = []
    for sid, scores in agg.items():
        s = sup_map.get(sid)
        stats = po_stats[sid]
        delivery_rate = round(stats["completed_orders"] / stats["total_orders"] * 100, 1) if stats["total_orders"] > 0 else 0
        receive_rate = round(stats["received_qty"] / stats["total_qty"] * 100, 1) if stats["total_qty"] > 0 else 0
        result.append({
            "supplier_id": sid,
            "supplier_name": s.name if s else f"#{sid}",
            "quality_score": round(sum(scores["quality"]) / len(scores["quality"]), 2) if scores["quality"] else 0,
            "delivery_score": round(sum(scores["delivery"]) / len(scores["delivery"]), 2) if scores["delivery"] else 0,
            "price_score": round(sum(scores["price"]) / len(scores["price"]), 2) if scores["price"] else 0,
            "service_score": round(sum(scores["service"]) / len(scores["service"]), 2) if scores["service"] else 0,
            "total_score": round(sum(scores["total"]) / len(scores["total"]), 2) if scores["total"] else 0,
            "delivery_rate": delivery_rate,
            "receive_rate": receive_rate,
        })
    return result


@router.get("/supplier-ranking")
def ai_supplier_ranking(
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """AI 供应商智能排名"""
    suppliers = db.query(Supplier).filter(Supplier.status == "active").all()

    # Compute evaluation averages
    eval_agg = defaultdict(lambda: {"quality": [], "delivery": [], "price": [], "service": [], "total": []})
    for e in db.query(SupplierEvaluation).all():
        eval_agg[e.supplier_id]["quality"].append(e.quality_score)
        eval_agg[e.supplier_id]["delivery"].append(e.delivery_score)
        eval_agg[e.supplier_id]["price"].append(e.price_score)
        eval_agg[e.supplier_id]["service"].append(e.service_score)
        eval_agg[e.supplier_id]["total"].append(e.total_score)

    po_stats = defaultdict(lambda: {"total": 0, "completed": 0})
    for po in db.query(PurchaseOrder).all():
        po_stats[po.supplier_id]["total"] += 1
        if po.status == "completed":
            po_stats[po.supplier_id]["completed"] += 1

    supplier_data = []
    for s in suppliers:
        ev = eval_agg.get(s.id, {})
        avg_total = round(sum(ev["total"]) / len(ev["total"]), 2) if ev["total"] else 0
        stats = po_stats[s.id]
        delivery_rate_val = round(stats["completed"] / stats["total"] * 100, 1) if stats["total"] > 0 else None
        supplier_data.append({
            "id": s.id,
            "name": s.name,
            "rating": s.rating,
            "delivery_lead_time": s.delivery_lead_time,
            "avg_evaluation": avg_total,
            "delivery_rate": delivery_rate_val,
        })

    # Call AI for intelligent ranking
    ai_result = supplier_ranking_ai(supplier_data)
    if ai_result and ai_result.get("status") == "error":
        raise HTTPException(status_code=503, detail=ai_result.get("error", "AI 服务不可用"))
    return {"suppliers": supplier_data, "ai_analysis": ai_result}


@router.get("/sales-history")
def ai_sales_history(
    product_id: Optional[int] = Query(None),
    days: int = Query(90, ge=1, le=365),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """销售历史与预测数据

    - 无 product_id: 返回聚合月度数据（最近6个月）+ TOP 5 产品
    - 有 product_id: 返回该产品的日度数据
    """
    if product_id is None:
        # 聚合模式：返回月度汇总 + TOP 5 产品
        months = 6
        start = date.today() - timedelta(days=months * 31)

        # 月度聚合数据
        month_expr = func.date_format(SaleOrder.order_date, "%Y-%m")
        monthly_query = db.query(
            month_expr.label("month"),
            func.sum(SaleOrderItem.quantity).label("total_qty"),
            func.sum(SaleOrderItem.total_price).label("total_amount"),
        ).join(SaleOrderItem, SaleOrderItem.order_id == SaleOrder.id)
        monthly_query = monthly_query.filter(SaleOrder.order_date >= start)
        monthly_query = monthly_query.group_by(month_expr).order_by(month_expr)
        monthly_rows = monthly_query.all()

        monthly_data = [
            {"month": r.month, "total_qty": float(r.total_qty or 0), "total_amount": float(r.total_amount or 0)}
            for r in monthly_rows
        ]

        # TOP 5 产品（按销售金额）
        top_query = db.query(
            SaleOrderItem.product_id,
            func.sum(SaleOrderItem.quantity).label("total_qty"),
            func.sum(SaleOrderItem.total_price).label("total_amount"),
        ).join(SaleOrder, SaleOrder.id == SaleOrderItem.order_id)
        top_query = top_query.filter(SaleOrder.order_date >= start)
        top_query = top_query.group_by(SaleOrderItem.product_id).order_by(func.sum(SaleOrderItem.total_price).desc())
        top_rows = top_query.limit(5).all()

        # 获取产品名称
        product_ids = [r.product_id for r in top_rows]
        products = db.query(Product).filter(Product.id.in_(product_ids)).all() if product_ids else []
        product_map = {p.id: p.name for p in products}

        top_products = [
            {
                "product_id": r.product_id,
                "name": product_map.get(r.product_id, f"#{r.product_id}"),
                "total_qty": float(r.total_qty or 0),
                "total_amount": float(r.total_amount or 0),
            }
            for r in top_rows
        ]

        return {"monthly_data": monthly_data, "top_products": top_products}

    # 产品模式：返回日度数据
    query = db.query(
        SaleOrder.order_date,
        func.sum(SaleOrderItem.quantity).label("total_qty"),
        func.sum(SaleOrderItem.total_price).label("total_amount"),
    ).join(SaleOrderItem, SaleOrderItem.order_id == SaleOrder.id)

    query = query.filter(SaleOrderItem.product_id == product_id)

    start = date.today() - timedelta(days=days)
    query = query.filter(SaleOrder.order_date >= start)
    query = query.group_by(SaleOrder.order_date).order_by(SaleOrder.order_date)

    rows = query.all()
    return [
        {"date": str(r.order_date), "total_qty": float(r.total_qty or 0), "total_amount": float(r.total_amount or 0)}
        for r in rows
    ]


@router.post("/sales-prediction")
def ai_sales_prediction(
    product_id: int = Query(...),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """AI 销售预测"""
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="产品不存在")

    history_data = (
        db.query(SaleOrderItem.quantity, SaleOrder.order_date)
        .join(SaleOrder, SaleOrder.id == SaleOrderItem.order_id)
        .filter(SaleOrderItem.product_id == product_id)
        .order_by(SaleOrder.order_date.desc())
        .limit(90)
        .all()
    )
    sales_data = [{"date": str(h.order_date), "qty": h.quantity} for h in history_data]

    result = sales_forecast(product.name, sales_data)
    if result and result.get("status") == "error":
        raise HTTPException(status_code=503, detail=result.get("error", "AI 服务不可用"))
    record = save_decision(
        db, "sales_forecast",
        f"{product.name} 销售预测",
        {"product_id": product_id},
        result,
        product_id,
    )
    try:
        parsed_output = json.loads(record.output_data) if isinstance(record.output_data, str) else record.output_data
    except (json.JSONDecodeError, TypeError):
        parsed_output = record.output_data
    return {
        "id": record.id,
        "decision_type": record.decision_type,
        "title": record.title,
        "input_data": record.input_data,
        "output_data": parsed_output,
        "summary": record.summary,
        "confidence": record.confidence,
        "related_id": record.related_id,
        "is_applied": record.is_applied,
        "created_at": str(record.created_at) if record.created_at else None,
    }
