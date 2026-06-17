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


def _deterministic_stock_alert(product_name: str, current_qty: float,
                                min_stock: float, max_stock: float,
                                recent_sales: list[dict], product_id: int = 0,
                                db: Session = None) -> dict:
    """Deterministic stock alert analysis using ROP (no LLM)"""
    from app.services.calculation_service import calc_reorder_point

    # Calculate daily sales rate
    daily_sales = 0.0
    if recent_sales:
        total_qty = sum(s.get("qty", 0) for s in recent_sales)
        daily_sales = total_qty / 30.0

    # Get ROP if db is available
    rop = min_stock
    safety_stock = 0.0
    if db and product_id:
        try:
            rop_result = calc_reorder_point(product_id, db)
            rop = rop_result.get("rop", min_stock)
            safety_stock = rop_result.get("safety_stock", 0)
        except Exception:
            pass

    # Determine alert level
    if current_qty == 0:
        alert_level = "critical"
        suggested_action = "立即补货"
        suggested_order_qty = max(int(rop), int(max_stock))
        reason = f"库存为零，ROP={rop:.1f}，需紧急补货"
    elif safety_stock > 0 and current_qty < safety_stock:
        alert_level = "critical"
        suggested_order_qty = max(int(rop - current_qty), int(max_stock - current_qty))
        suggested_action = "紧急补货"
        reason = f"库存({current_qty})低于安全库存({safety_stock:.1f})，ROP={rop:.1f}"
    elif current_qty <= rop:
        alert_level = "warning"
        suggested_order_qty = max(int(rop - current_qty), int(max_stock - current_qty))
        suggested_action = "建议补货"
        reason = f"库存({current_qty})接近再订货点({rop:.1f})，建议补充至最大库存"
    elif current_qty <= min_stock:
        alert_level = "warning"
        suggested_order_qty = int(max_stock - current_qty)
        suggested_action = "建议补货"
        reason = f"库存({current_qty})低于最低库存线({min_stock})，建议补充"
    else:
        alert_level = "normal"
        suggested_action = "维持现有库存"
        suggested_order_qty = 0
        reason = f"库存({current_qty})高于再订货点({rop:.1f})，库存充足"

    confidence = 0.9 if daily_sales > 0 else 0.5

    return {
        "alert_level": alert_level,
        "suggested_action": suggested_action,
        "suggested_order_qty": suggested_order_qty,
        "reason": reason,
        "confidence": confidence,
    }


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

    result = _deterministic_stock_alert(
        product_name=product.name,
        current_qty=current_qty,
        min_stock=product.min_stock,
        max_stock=product.max_stock,
        recent_sales=sales_data,
        product_id=product_id,
        db=db,
    )

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

            result = _deterministic_stock_alert(
                product_name=product.name,
                current_qty=current_qty,
                min_stock=product.min_stock,
                max_stock=product.max_stock,
                recent_sales=sales_data,
                product_id=product_id,
                db=db,
            )

            results.append({
                "product_id": product_id,
                "product_name": product.name,
                "current_qty": current_qty,
                "risk_level": result.get("alert_level", "unknown"),
                "suggestion": result.get("suggested_action", ""),
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
    """供应商推荐（基于确定性评分算法）"""
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="产品不存在")

    from app.services.supplier_scoring import calc_supplier_score
    scores = calc_supplier_score(supplier_id=None, db=db)
    if isinstance(scores, dict) and "error" in scores:
        raise HTTPException(status_code=503, detail=scores.get("error", "供应商评分服务不可用"))

    # Build recommendations from scoring results
    recommendations = []
    for s in scores:
        recommendations.append({
            "supplier_id": s["supplier_id"],
            "supplier_name": s["supplier_name"],
            "score": s["total_score"],
            "reason": f"质量{s['quality']:.0f}/交付{s['delivery']:.0f}/价格{s['price']:.0f}/服务{s['service']:.0f}"
                      + (f"，风险罚分{s.get('risk_penalty', 0):.1f}" if s.get("risk_penalty", 0) > 0 else ""),
        })

    result = {
        "recommendations": recommendations,
        "summary": f"共评估 {len(recommendations)} 家供应商，推荐 {recommendations[0]['supplier_name']}" if recommendations else "无可用供应商",
        "confidence": 0.9,
    }

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
    """供应商智能排名（基于确定性评分算法）"""
    from app.services.supplier_scoring import calc_supplier_score

    scores = calc_supplier_score(supplier_id=None, db=db)
    if isinstance(scores, dict) and "error" in scores:
        raise HTTPException(status_code=503, detail=scores.get("error", "供应商评分服务不可用"))

    # Build supplier_data in original format for backward compatibility
    suppliers = db.query(Supplier).filter(Supplier.status == "active").all()
    score_map = {s["supplier_id"]: s for s in scores}

    supplier_data = []
    ai_rankings = []
    for s in suppliers:
        sc = score_map.get(s.id, {})
        supplier_data.append({
            "id": s.id,
            "name": s.name,
            "rating": s.rating,
            "delivery_lead_time": s.delivery_lead_time,
            "avg_evaluation": sc.get("total_score", 0),
            "delivery_rate": None,
        })
        strengths_parts = []
        weaknesses_parts = []
        if sc.get("quality", 0) >= 80:
            strengths_parts.append("质量优异")
        elif sc.get("quality", 0) < 60:
            weaknesses_parts.append("质量偏低")
        if sc.get("delivery", 0) >= 80:
            strengths_parts.append("交付可靠")
        elif sc.get("delivery", 0) < 60:
            weaknesses_parts.append("交付不稳")
        if sc.get("price", 0) >= 80:
            strengths_parts.append("价格优势")
        elif sc.get("price", 0) < 60:
            weaknesses_parts.append("价格偏高")
        if sc.get("is_single_source"):
            weaknesses_parts.append("单源依赖风险")
        if sc.get("risk_penalty", 0) > 0:
            weaknesses_parts.append(f"风险罚分{sc['risk_penalty']:.1f}")
        ai_rankings.append({
            "supplier_id": s.id,
            "supplier_name": s.name,
            "ai_score": sc.get("total_score", 0),
            "strengths": " ".join(strengths_parts),
            "weaknesses": " ".join(weaknesses_parts),
            "suggestion": sc.get("suggested_share", ""),
        })

    # Build ai_analysis in original format
    top = ai_rankings[0] if ai_rankings else None
    ai_result = {
        "rankings": ai_rankings,
        "summary": f"共评估 {len(ai_rankings)} 家供应商，推荐 {top['supplier_name']}（综合评分 {top['ai_score']:.1f}）" if top else "暂无供应商数据",
        "confidence": 0.9,
    }
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

    # 产品模式：返回日度数据（填补无销售日期为0）
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

    # Build a lookup dict from DB results
    sales_map = {r.order_date: (float(r.total_qty or 0), float(r.total_amount or 0)) for r in rows}

    # Generate complete date range, filling missing days with 0
    result = []
    current = start
    end = date.today()
    while current <= end:
        qty, amount = sales_map.get(current, (0.0, 0.0))
        result.append({"date": str(current), "total_qty": qty, "total_amount": amount})
        current += timedelta(days=1)

    return result


@router.post("/sales-prediction")
def ai_sales_prediction(
    product_id: int = Query(...),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """销售预测（基于WMA确定性算法）"""
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="产品不存在")

    history_data = (
        db.query(SaleOrder.order_date, func.sum(SaleOrderItem.quantity).label("total_qty"))
        .join(SaleOrder, SaleOrder.id == SaleOrderItem.order_id)
        .filter(SaleOrderItem.product_id == product_id)
        .filter(SaleOrder.order_date >= date.today() - timedelta(days=90))
        .group_by(SaleOrder.order_date)
        .order_by(SaleOrder.order_date)
        .all()
    )

    # Fill complete date range with 0 for missing days
    sales_map = {h.order_date: float(h.total_qty or 0) for h in history_data}
    sales_data = []
    current = date.today() - timedelta(days=90)
    end = date.today()
    while current <= end:
        sales_data.append({"date": str(current), "qty": sales_map.get(current, 0.0)})
        current += timedelta(days=1)

    # Use ForecastService (Prophet/NaiveSeasonal) with WMA fallback
    from app.tools.sales_tools import _wma_fallback
    hist_for_wma = [{"date": d["date"], "quantity": d["qty"]} for d in sales_data]
    predictions = _wma_fallback(hist_for_wma, 30, product_id=product_id, db=db)

    # Determine trend from recent data
    if len(hist_for_wma) >= 14:
        recent_qty = sum(h["quantity"] for h in hist_for_wma[-7:])
        earlier_qty = sum(h["quantity"] for h in hist_for_wma[:7])
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
    last_date = date.today()
    prediction_dates = [(last_date + timedelta(days=i + 1)).strftime("%Y-%m-%d") for i in range(len(predictions))]

    confidence = 0.85 if len(hist_for_wma) >= 14 else 0.5

    prediction_payload = {
        "product_id": product.id,
        "product_name": product.name,
        "history": sales_data[-30:],
        "predictions": predictions,
        "prediction_dates": prediction_dates,
        "trend": trend,
        "seasonal_factor": "",
        "suggestion": f"预测未来30天需求约{sum(predictions)}件，趋势{trend}",
        "confidence": confidence,
    }

    return {
        "output_data": prediction_payload,
        "summary": prediction_payload["suggestion"],
        "confidence": confidence,
    }