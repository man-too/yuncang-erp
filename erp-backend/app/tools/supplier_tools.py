"""供应商查询与排名工具"""
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.models.supplier import Supplier, SupplierEvaluation
from app.models.purchase import PurchaseOrder, PurchaseOrderItem

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "query_suppliers",
            "description": "查询供应商信息，包括评分、交期、交易统计等",
            "parameters": {
                "type": "object",
                "properties": {
                    "supplier_id": {"type": "integer", "description": "供应商ID，可选"},
                    "status": {"type": "string", "description": "状态筛选：active/inactive/blacklisted"},
                    "limit": {"type": "integer", "description": "返回条数上限，默认50"},
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "rank_suppliers",
            "description": "AI供应商综合排名。从质量、交付、价格、服务四个维度综合评估所有活跃供应商",
            "parameters": {
                "type": "object",
                "properties": {
                    "product_id": {"type": "integer", "description": "按产品需求评估供应商适配度，可选"},
                },
                "required": []
            }
        }
    },
]


def execute(name: str, args: dict, db: Session) -> dict | None:
    if name == "query_suppliers":
        return _query_suppliers(args, db)
    if name == "rank_suppliers":
        return _rank_suppliers(args, db)
    return None


def _query_suppliers(args: dict, db: Session) -> dict:
    q = db.query(Supplier)
    if args.get("supplier_id"):
        q = q.filter(Supplier.id == args["supplier_id"])
    if args.get("status"):
        q = q.filter(Supplier.status == args["status"])

    suppliers = q.limit(args.get("limit", 50)).all()

    items = []
    for s in suppliers:
        # Average evaluation scores
        evals = db.query(
            func.avg(SupplierEvaluation.quality_score).label("q"),
            func.avg(SupplierEvaluation.delivery_score).label("d"),
            func.avg(SupplierEvaluation.price_score).label("p"),
            func.avg(SupplierEvaluation.service_score).label("s"),
            func.avg(SupplierEvaluation.total_score).label("total_label"),
        ).filter(SupplierEvaluation.supplier_id == s.id).first()

        # Order completion stats
        total_orders = db.query(PurchaseOrder).filter(
            PurchaseOrder.supplier_id == s.id
        ).count()
        completed_orders = db.query(PurchaseOrder).filter(
            PurchaseOrder.supplier_id == s.id,
            PurchaseOrder.status == "completed",
        ).count()

        items.append({
            "id": s.id, "code": s.code, "name": s.name,
            "contact_person": s.contact_person, "phone": s.phone,
            "status": s.status.value if hasattr(s.status, 'value') else s.status,
            "rating": float(s.rating),
            "delivery_lead_time": s.delivery_lead_time,
            "avg_quality_score": round(float(evals.q or 0), 1),
            "avg_delivery_score": round(float(evals.d or 0), 1),
            "avg_price_score": round(float(evals.p or 0), 1),
            "avg_service_score": round(float(evals.s or 0), 1),
            "avg_total_score": round(float(evals.total_label or 0), 1),
            "total_orders": total_orders,
            "completed_orders": completed_orders,
            "completion_rate": round(completed_orders / total_orders * 100, 1) if total_orders > 0 else 0,
        })

    return {"suppliers": items, "total": len(items)}


def _rank_suppliers(args: dict, db: Session) -> dict:
    from app.services.supplier_scoring import calc_supplier_score

    # Use deterministic supplier scoring (no LLM)
    scores = calc_supplier_score(supplier_id=None, db=db)

    # Handle both single (error) and list results
    if isinstance(scores, dict) and "error" in scores:
        return {"rankings": [], "summary": scores["error"], "confidence": 0, "supplier_data": []}

    # Build rankings from calc_supplier_score results
    rankings = []
    supplier_data = []
    for s in scores:
        ranking_entry = {
            "supplier_id": s["supplier_id"],
            "supplier_name": s["supplier_name"],
            "ai_score": s["total_score"],
            "total_score": s["total_score"],
            "strengths": "",
            "weaknesses": "",
            "suggestion": s.get("suggested_share", ""),
        }
        # Add strengths/weaknesses based on score breakdown
        if s["quality"] >= 80:
            ranking_entry["strengths"] += "质量优异 "
        elif s["quality"] < 60:
            ranking_entry["weaknesses"] += "质量偏低 "
        if s["delivery"] >= 80:
            ranking_entry["strengths"] += "交付可靠 "
        elif s["delivery"] < 60:
            ranking_entry["weaknesses"] += "交付不稳 "
        if s["price"] >= 80:
            ranking_entry["strengths"] += "价格优势 "
        elif s["price"] < 60:
            ranking_entry["weaknesses"] += "价格偏高 "
        if s.get("is_single_source"):
            ranking_entry["weaknesses"] += "单源依赖风险 "
        if s.get("risk_penalty", 0) > 0:
            ranking_entry["weaknesses"] += f"风险罚分{s['risk_penalty']:.1f} "

        rankings.append(ranking_entry)
        supplier_data.append({
            "supplier_id": s["supplier_id"],
            "supplier_name": s["supplier_name"],
            "quality_score": s["quality"],
            "delivery_score": s["delivery"],
            "price_score": s["price"],
            "service_score": s["service"],
            "total_score": s["total_score"],
            "lead_time_days": 0,  # not in scoring output
        })

    # Generate summary
    if rankings:
        top = rankings[0]
        summary = f"共评估 {len(rankings)} 家供应商，推荐 {top['supplier_name']}（综合评分 {top['total_score']:.1f}）"
    else:
        summary = "暂无活跃供应商数据"

    return {
        "rankings": rankings,
        "summary": summary,
        "confidence": 0.9,
        "supplier_data": supplier_data,
    }
