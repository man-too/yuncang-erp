"""促销活动查询工具"""
from datetime import date
from sqlalchemy.orm import Session
from app.models.promotion import Promotion


def execute(name: str, args: dict, db: Session) -> dict | None:
    if name != "query_promotions":
        return None
    return _query_promotions(args, db)


def _query_promotions(args: dict, db: Session) -> dict:
    product_id = args.get("product_id")
    active_only = args.get("active_only", True)

    q = db.query(Promotion)

    if active_only:
        today = date.today()
        q = q.filter(
            Promotion.is_active == True,
            Promotion.start_date <= today,
            Promotion.end_date >= today,
        )

    promotions = q.order_by(Promotion.start_date.desc()).limit(50).all()

    results = []
    for p in promotions:
        # 按产品筛选
        if product_id:
            pids = p.product_ids or []
            if product_id not in pids:
                continue

        results.append({
            "id": p.id,
            "name": p.name,
            "start_date": str(p.start_date),
            "end_date": str(p.end_date),
            "promotion_type": p.promotion_type,
            "discount_pct": p.discount_pct,
            "product_ids": p.product_ids or [],
            "expected_lift_pct": p.expected_lift_pct,
            "is_active": p.is_active,
        })

    return {"promotions": results, "total": len(results)}
