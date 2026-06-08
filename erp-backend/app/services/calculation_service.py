"""计算服务 — 纯 Python 计算，不依赖 LLM

包含:
- calc_reorder_point: 再订货点 (ROP) + 安全库存
- calc_inventory_kpi: 库存 KPI (周转天数 / 呆滞库存 / 资金占用)
"""

import math
from datetime import datetime, timedelta, date
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models.product import Product, ProductCategory
from app.models.supplier import Supplier, SupplierEvaluation
from app.models.inventory import Inventory, InventoryRecord
from app.models.purchase import PurchaseOrder, PurchaseOrderItem, PurchaseInbound
from app.models.sale import SaleOrder, SaleOrderItem


# ────────────────────────────────────────────
# 1. 再订货点 (Reorder Point)
# ────────────────────────────────────────────

# ABC 分类 → 服务水平 → z 值
_ABC_Z = {
    "A": 1.65,   # 95% 服务水平
    "B": 1.28,   # 90%
    "C": 1.04,   # 85%
}


def _classify_abc(product_id: int, db: Session) -> str:
    """简单 ABC 分类：按近 90 天出库金额在所有产品中的累计占比。
    A: 前 80%, B: 80-95%, C: 95-100%。
    无出库记录默认 C 类。
    """
    cutoff = date.today() - timedelta(days=90)

    # 按产品聚合出库金额
    rows = (
        db.query(
            SaleOrderItem.product_id,
            func.sum(SaleOrderItem.total_price).label("revenue"),
        )
        .join(SaleOrder, SaleOrderItem.order_id == SaleOrder.id)
        .filter(
            SaleOrder.order_date >= cutoff,
            SaleOrder.status != "cancelled",
        )
        .group_by(SaleOrderItem.product_id)
        .order_by(func.sum(SaleOrderItem.total_price).desc())
        .all()
    )

    if not rows:
        return "C"

    total_revenue = sum(r.revenue or 0 for r in rows)
    if total_revenue == 0:
        return "C"

    cumulative = 0.0
    for r in rows:
        cumulative += (r.revenue or 0)
        if r.product_id == product_id:
            ratio = cumulative / total_revenue
            if ratio <= 0.80:
                return "A"
            elif ratio <= 0.95:
                return "B"
            else:
                return "C"

    # 产品不在出库记录中
    return "C"


def calc_reorder_point(
    product_id: int,
    db: Session,
    supplier_id: int | None = None,
) -> dict:
    """计算再订货点 (ROP)

    ROP = avg_daily_sales × lead_time + safety_stock
    safety_stock = z × σ_daily × √(lead_time)
    """
    product = db.get(Product, product_id)
    if not product:
        return {"error": f"产品 {product_id} 不存在"}

    # ── lead_time ──
    lead_time = 7  # 默认 7 天
    if supplier_id:
        supplier = db.get(Supplier, supplier_id)
        if supplier and supplier.delivery_lead_time:
            lead_time = supplier.delivery_lead_time
    else:
        # 取最近一次采购该产品的供应商的交期
        last_item = (
            db.query(PurchaseOrderItem)
            .join(PurchaseOrder, PurchaseOrderItem.order_id == PurchaseOrder.id)
            .filter(
                PurchaseOrderItem.product_id == product_id,
                PurchaseOrder.status != "cancelled",
            )
            .order_by(PurchaseOrder.order_date.desc())
            .first()
        )
        if last_item:
            po = db.get(PurchaseOrder, last_item.order_id)
            if po:
                sup = db.get(Supplier, po.supplier_id)
                if sup and sup.delivery_lead_time:
                    lead_time = sup.delivery_lead_time

    # ── 近 60 天日销量 ──
    cutoff = date.today() - timedelta(days=60)
    daily_rows = (
        db.query(
            func.date(SaleOrder.order_date).label("d"),
            func.sum(SaleOrderItem.quantity).label("qty"),
        )
        .join(SaleOrderItem, SaleOrderItem.order_id == SaleOrder.id)
        .filter(
            SaleOrder.order_date >= cutoff,
            SaleOrderItem.product_id == product_id,
            SaleOrder.status != "cancelled",
        )
        .group_by(func.date(SaleOrder.order_date))
        .all()
    )

    if not daily_rows:
        # 无销量数据，返回基于 min_stock 的保守估算
        return {
            "product_id": product_id,
            "product_name": product.name,
            "rop": product.min_stock or 0,
            "avg_daily_sales": 0.0,
            "lead_time": lead_time,
            "safety_stock": product.min_stock or 0,
            "service_level": "85%",
            "abc_class": "C",
            "warning": "近60天无销量数据，使用 min_stock 作为保守值",
        }

    quantities = [float(r.qty or 0) for r in daily_rows]

    # 用完整 60 天窗口计算均值和标准差（含零销售日），保证两者一致
    k = len(quantities)
    sum_q = sum(quantities)
    avg_daily = sum_q / 60
    if k >= 2 and avg_daily > 0:
        # variance = (sum(q_i - mean)^2 + (60-k) * mean^2) / 60
        ssd = sum((q - avg_daily) ** 2 for q in quantities)  # 有销售日
        ssd += (60 - k) * (avg_daily ** 2)                     # 零销售日
        std_daily = math.sqrt(ssd / 60)
    else:
        std_daily = avg_daily * 0.3 if avg_daily > 0 else 0.0

    # ── ABC 分类 → z ──
    abc = _classify_abc(product_id, db)
    z = _ABC_Z.get(abc, 1.04)

    safety_stock = z * std_daily * math.sqrt(lead_time)
    rop = avg_daily * lead_time + safety_stock

    return {
        "product_id": product_id,
        "product_name": product.name,
        "rop": round(rop, 2),
        "avg_daily_sales": round(avg_daily, 2),
        "lead_time": lead_time,
        "safety_stock": round(safety_stock, 2),
        "service_level": {"A": "95%", "B": "90%", "C": "85%"}[abc],
        "abc_class": abc,
    }


# ────────────────────────────────────────────
# 2. 库存 KPI
# ────────────────────────────────────────────

def calc_inventory_kpi(db: Session) -> dict:
    """计算全量库存 KPI

    - turnover_days: 加权平均周转天数
    - dead_stock_count: 呆滞 SKU 数（90 天无出库且有库存）
    - dead_stock_pct: 呆滞 SKU 占比
    - capital_occupied: 库存资金占用
    """
    today = date.today()
    cutoff_90 = today - timedelta(days=90)

    # ── 当前库存汇总 ──
    inv_rows = (
        db.query(
            Inventory.product_id,
            func.sum(Inventory.quantity).label("total_qty"),
        )
        .group_by(Inventory.product_id)
        .all()
    )
    inv_map = {r.product_id: float(r.total_qty or 0) for r in inv_rows}

    # ── 近 90 天出库量 ──
    sales_rows = (
        db.query(
            SaleOrderItem.product_id,
            func.sum(SaleOrderItem.quantity).label("sold_qty"),
        )
        .join(SaleOrder, SaleOrderItem.order_id == SaleOrder.id)
        .filter(
            SaleOrder.order_date >= cutoff_90,
            SaleOrder.status != "cancelled",
        )
        .group_by(SaleOrderItem.product_id)
        .all()
    )
    sales_map = {r.product_id: float(r.sold_qty or 0) for r in sales_rows}

    # ── 周转天数 (加权) ──
    total_cost_value = 0.0
    total_daily_cogs = 0.0

    # 批量查 Product，避免 N+1
    product_ids = list(inv_map.keys())
    products_map = {p.id: p for p in db.query(Product).filter(Product.id.in_(product_ids)).all()}

    for pid, qty in inv_map.items():
        product = products_map.get(pid)
        if not product:
            continue
        cost = product.cost_price or product.purchase_price or 0
        total_cost_value += qty * cost

        sold = sales_map.get(pid, 0)
        daily_cogs = (sold * cost) / 90
        total_daily_cogs += daily_cogs

    turnover_days = (total_cost_value / total_daily_cogs) if total_daily_cogs > 0 else 0

    # ── 呆滞库存 ──
    dead_count = 0
    total_sku = len(inv_map)
    for pid, qty in inv_map.items():
        if qty > 0 and sales_map.get(pid, 0) == 0:
            dead_count += 1

    dead_pct = (dead_count / total_sku * 100) if total_sku > 0 else 0

    return {
        "turnover_days": round(turnover_days, 1),
        "dead_stock_count": dead_count,
        "dead_stock_pct": round(dead_pct, 1),
        "capital_occupied": round(total_cost_value, 2),
    }


# ────────────────────────────────────────────
# 工具函数
# ────────────────────────────────────────────

def _std(values: list[float]) -> float:
    """总体标准差"""
    n = len(values)
    if n < 2:
        return 0.0
    mean = sum(values) / n
    return math.sqrt(sum((x - mean) ** 2 for x in values) / n)


def batch_calc_reorder_point(
    product_ids: list[int],
    db: Session,
) -> dict[int, dict]:
    """批量计算再订货点 (ROP)，避免逐个查询的开销"""
    from app.models.product import Product
    from app.models.supplier import Supplier
    from app.models.purchase import PurchaseOrder, PurchaseOrderItem
    from app.models.sale import SaleOrder, SaleOrderItem

    if not product_ids:
        return {}

    products = {p.id: p for p in db.query(Product).filter(Product.id.in_(product_ids)).all()}

    # ── 默认 lead_time ──
    # 取各产品最近采购供应商的交期
    last_po_items = (
        db.query(
            PurchaseOrderItem.product_id,
            PurchaseOrder.supplier_id,
        )
        .join(PurchaseOrder, PurchaseOrderItem.order_id == PurchaseOrder.id)
        .filter(
            PurchaseOrderItem.product_id.in_(product_ids),
            PurchaseOrder.status != "cancelled",
        )
        .order_by(PurchaseOrder.order_date.desc())
        .all()
    )
    supplier_ids = set(s for _, s in last_po_items)
    suppliers = {s.id: s for s in db.query(Supplier).filter(Supplier.id.in_(supplier_ids)).all()}
    lead_time_map: dict[int, int] = {}
    seen_pids: set[int] = set()
    for pid, sid in last_po_items:
        if pid not in seen_pids:
            seen_pids.add(pid)
            sup = suppliers.get(sid)
            lead_time_map[pid] = sup.delivery_lead_time if sup and sup.delivery_lead_time else 7
    # 没找到采购记录的默认7天
    for pid in product_ids:
        lead_time_map.setdefault(pid, 7)

    # ── 近 60 天日销量 ──
    cutoff = date.today() - timedelta(days=60)
    daily_rows = (
        db.query(
            SaleOrderItem.product_id,
            func.date(SaleOrder.order_date).label("d"),
            func.sum(SaleOrderItem.quantity).label("qty"),
        )
        .join(SaleOrderItem, SaleOrderItem.order_id == SaleOrder.id)
        .filter(
            SaleOrder.order_date >= cutoff,
            SaleOrderItem.product_id.in_(product_ids),
            SaleOrder.status != "cancelled",
        )
        .group_by(SaleOrderItem.product_id, func.date(SaleOrder.order_date))
        .all()
    )

    # 按 product_id 聚合销量
    sales_map: dict[int, list[float]] = {}
    for pid, _, qty in daily_rows:
        sales_map.setdefault(pid, []).append(float(qty or 0))

    # ── ABC 分类 ──
    def _abc(pid: int) -> str:
        return "C"  # 简化处理，默认C类

    _ABC_Z_BATCH = {"A": 1.65, "B": 1.28, "C": 1.04}

    result: dict[int, dict] = {}
    for pid in product_ids:
        prod = products.get(pid)
        if not prod:
            continue
        lt = lead_time_map.get(pid, 7)
        quantities = sales_map.get(pid, [])
        if not quantities:
            result[pid] = {
                "product_id": pid,
                "product_name": prod.name,
                "rop": prod.min_stock or 0,
                "avg_daily_sales": 0.0,
                "lead_time": lt,
                "safety_stock": prod.min_stock or 0,
                "abc_class": "C",
            }
            continue

        sum_q = sum(quantities)
        k = len(quantities)
        avg_daily = sum_q / 60
        if k >= 2 and avg_daily > 0:
            ssd = sum((q - avg_daily) ** 2 for q in quantities)
            ssd += (60 - k) * (avg_daily ** 2)
            std_daily = math.sqrt(ssd / 60)
        else:
            std_daily = avg_daily * 0.3 if avg_daily > 0 else 0.0

        abc = _abc(pid)
        z = _ABC_Z_BATCH.get(abc, 1.04)
        safety_stock = z * std_daily * math.sqrt(lt)
        rop = avg_daily * lt + safety_stock

        result[pid] = {
            "product_id": pid,
            "product_name": prod.name,
            "rop": round(rop, 2),
            "avg_daily_sales": round(avg_daily, 2),
            "lead_time": lt,
            "safety_stock": round(safety_stock, 2),
            "abc_class": abc,
        }

    return result
