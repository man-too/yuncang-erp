"""供应商评分 + 风险评估 — 纯 Python 计算，不依赖 LLM

计算:
- 质量(30%) + 交付(25%) + 价格(20%) + 服务(15%) - 风险惩罚(10%)
- 风险惩罚 = 单源依赖罚分 + 交付波动罚分
"""

from datetime import date, timedelta
import math

from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models.supplier import Supplier, SupplierEvaluation, SupplierMetrics
from app.models.purchase import PurchaseOrder, PurchaseOrderItem, PurchaseInbound
from app.models.product import Product


# ────────────────────────────────────────────
# 权重配置
# ────────────────────────────────────────────
WEIGHTS = {
    "quality": 0.30,
    "delivery": 0.25,
    "price": 0.20,
    "service": 0.15,
}
RISK_PENALTY_WEIGHT = 0.10  # 风险惩罚上限占比

# 单源依赖：如果某产品只有一家供应商，该供应商扣分
SINGLE_SOURCE_PENALTY = 5.0

# 交付波动：delay_std 超过阈值则扣分
DELAY_STD_THRESHOLD = 3.0  # 标准差超过 3 天开始罚
DELAY_STD_PENALTY_PER_STD = 2.0  # 每超 1 个标准差扣 2 分


def calc_supplier_score(
    supplier_id: int | None = None,
    db: Session | None = None,
) -> dict | list[dict]:
    """计算供应商评分

    传入 supplier_id 计算单个；不传则计算全部。
    """
    if db is None:
        return {"error": "db session required"}

    if supplier_id:
        return _score_one(supplier_id, db)

    # 批量计算
    suppliers = db.query(Supplier).filter(Supplier.status == "active").all()
    results = []
    for s in suppliers:
        try:
            results.append(_score_one(s.id, db))
        except Exception:
            continue
    results.sort(key=lambda x: x.get("total_score", 0), reverse=True)
    return results


def _score_one(supplier_id: int, db: Session) -> dict:
    supplier = db.get(Supplier, supplier_id)
    if not supplier:
        return {"error": f"供应商 {supplier_id} 不存在"}

    # ── 最近一次评估 ──
    latest_eval = (
        db.query(SupplierEvaluation)
        .filter(SupplierEvaluation.supplier_id == supplier_id)
        .order_by(SupplierEvaluation.created_at.desc())
        .first()
    )

    if latest_eval:
        quality = latest_eval.quality_score or 0
        delivery = latest_eval.delivery_score or 0
        price = latest_eval.price_score or 0
        service = latest_eval.service_score or 0
    else:
        quality = delivery = price = service = 0

    base_score = (
        quality * WEIGHTS["quality"]
        + delivery * WEIGHTS["delivery"]
        + price * WEIGHTS["price"]
        + service * WEIGHTS["service"]
    )

    # ── 风险惩罚 ──
    single_source_penalty = _calc_single_source_penalty(supplier_id, db)
    delay_std_penalty = _calc_delay_std_penalty(supplier_id, db)

    total_penalty = single_source_penalty + delay_std_penalty
    max_penalty = 100 * RISK_PENALTY_WEIGHT
    total_penalty = min(total_penalty, max_penalty)

    total_score = max(base_score - total_penalty, 0)

    # ── 单源依赖信息 ──
    is_single_source = _is_single_source(supplier_id, db)

    # ── 建议份额 ──
    suggested_share = _suggest_share(is_single_source, total_score)

    return {
        "supplier_id": supplier_id,
        "supplier_name": supplier.name,
        "quality": quality,
        "delivery": delivery,
        "price": price,
        "service": service,
        "base_score": round(base_score, 2),
        "risk_penalty": round(total_penalty, 2),
        "single_source_penalty": round(single_source_penalty, 2),
        "delay_std_penalty": round(delay_std_penalty, 2),
        "total_score": round(total_score, 2),
        "is_single_source": is_single_source,
        "suggested_share": suggested_share,
    }


# ────────────────────────────────────────────
# 风险子项
# ────────────────────────────────────────────

def _is_single_source(supplier_id: int, db: Session) -> bool:
    """判断该供应商是否有「独家供应」的产品"""
    # 找出该供应商供应的产品
    product_ids = (
        db.query(PurchaseOrderItem.product_id)
        .join(PurchaseOrder, PurchaseOrderItem.order_id == PurchaseOrder.id)
        .filter(
            PurchaseOrder.supplier_id == supplier_id,
            PurchaseOrder.status != "cancelled",
        )
        .distinct()
        .subquery()
    )

    # 对每个产品，检查是否有其他供应商
    for row in db.query(product_ids).all():
        pid = row[0]
        other_suppliers = (
            db.query(PurchaseOrder.supplier_id)
            .join(PurchaseOrderItem, PurchaseOrderItem.order_id == PurchaseOrder.id)
            .filter(
                PurchaseOrderItem.product_id == pid,
                PurchaseOrder.supplier_id != supplier_id,
                PurchaseOrder.status != "cancelled",
            )
            .distinct()
            .count()
        )
        if other_suppliers == 0:
            return True

    return False


def _calc_single_source_penalty(supplier_id: int, db: Session) -> float:
    if _is_single_source(supplier_id, db):
        return SINGLE_SOURCE_PENALTY
    return 0.0


def _calc_delay_std_penalty(supplier_id: int, db: Session) -> float:
    """从 supplier_metrics 取最近一条 delay_std 计算罚分"""
    metric = (
        db.query(SupplierMetrics)
        .filter(SupplierMetrics.supplier_id == supplier_id)
        .order_by(SupplierMetrics.metric_date.desc())
        .first()
    )
    if not metric or metric.delivery_delay_std is None:
        return 0.0

    if metric.delivery_delay_std > DELAY_STD_THRESHOLD:
        excess = metric.delivery_delay_std - DELAY_STD_THRESHOLD
        return excess * DELAY_STD_PENALTY_PER_STD

    return 0.0


def _suggest_share(is_single_source: bool, total_score: float) -> str:
    """建议采购份额"""
    if is_single_source:
        # 单源供应商，建议 100%（无替代）
        return "100% (单源依赖，建议开发备选)"

    if total_score >= 85:
        return "60%"
    elif total_score >= 70:
        return "40%"
    elif total_score >= 50:
        return "20%"
    else:
        return "10%"


# ────────────────────────────────────────────
# SupplierMetrics 更新
# ────────────────────────────────────────────

def update_supplier_metrics(supplier_id: int, db: Session) -> None:
    """重新计算并写入该供应商的 SupplierMetrics"""
    cutoff = date.today() - timedelta(days=180)

    # 近 6 个月的采购单 → 计算实际交期偏差
    orders = (
        db.query(PurchaseOrder)
        .filter(
            PurchaseOrder.supplier_id == supplier_id,
            PurchaseOrder.order_date >= cutoff,
            PurchaseOrder.status != "cancelled",
            PurchaseOrder.expected_delivery_date.isnot(None),
        )
        .all()
    )

    delays = []
    on_time_count = 0
    for po in orders:
        if po.expected_delivery_date is None:
            continue
        # 找到最早的入库日期
        inbound = (
            db.query(PurchaseInbound)
            .filter(PurchaseInbound.order_id == po.id)
            .order_by(PurchaseInbound.inbound_date)
            .first()
        )
        if inbound:
            actual = inbound.inbound_date
            delay = (actual - po.expected_delivery_date).days
            delays.append(delay)
            if delay <= 0:
                on_time_count += 1

    delay_std = _std(delays) if len(delays) >= 2 else None
    on_time_rate = (on_time_count / len(delays) * 100) if delays else None

    # 写入最新 metric
    metric = SupplierMetrics(
        supplier_id=supplier_id,
        delivery_delay_std=delay_std,
        on_time_rate=on_time_rate,
    )
    db.add(metric)
    db.commit()


def _std(values: list[float]) -> float:
    n = len(values)
    if n < 2:
        return 0.0
    mean = sum(values) / n
    return math.sqrt(sum((x - mean) ** 2 for x in values) / n)
