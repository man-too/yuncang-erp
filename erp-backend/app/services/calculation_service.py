"""计算服务 — 纯 Python 计算，不依赖 LLM

包含:
- calc_reorder_point: 再订货点 (ROP) + 安全库存  (→ reorder_service)
- batch_calc_reorder_point: 批量 ROP              (→ reorder_service)
- calc_inventory_kpi: 库存 KPI (周转天数 / 呆滞库存 / 资金占用)
- calc_inventory_health: 库存健康看板 (缺货率/ABC/可供应天数/持有成本/问题产品)
"""

import logging
from datetime import date, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models.product import Product
from app.models.inventory import Inventory, Warehouse
from app.models.sale import SaleOrder, SaleOrderItem, SaleOrderStatus

# ── 从 reorder_service 重新导出，保持向后兼容 ──
from app.services.reorder_service import (  # noqa: F401
    calc_reorder_point,
    batch_calc_reorder_point,
    _ABC_Z,
    _classify_abc,
    _should_use_forecast,
    _blend_forecast_into_rop,
    _std,
)

logger = logging.getLogger(__name__)

# ── 常量 ──
ANNUAL_HOLDING_COST_RATE = 0.15


# ────────────────────────────────────────────
# 库存 KPI
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

    # ── 当前库存汇总（仅活跃产品）──
    inv_rows = (
        db.query(
            Inventory.product_id,
            func.sum(Inventory.quantity).label("total_qty"),
        )
        .join(Product, Inventory.product_id == Product.id)
        .filter(Product.is_active == True)
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
            SaleOrder.status != SaleOrderStatus.CANCELLED,
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
    products_map = (
        {p.id: p for p in db.query(Product).filter(Product.id.in_(product_ids)).all()}
        if product_ids else {}
    )

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
# 库存健康看板
# ────────────────────────────────────────────

def calc_inventory_health(db: Session) -> dict:
    """计算库存健康看板数据

    返回缺货率、ABC 分类分布、可供应天数分布、持有成本、周转天数、
    呆滞品统计、资金占用及问题产品明细。
    """
    today = date.today()
    cutoff_90 = today - timedelta(days=90)

    # ── 基础 KPI（复用）──
    base_kpi = calc_inventory_kpi(db)

    # ── 库存行 + 产品 + 仓库（仅活跃产品）──
    inv_rows = (
        db.query(Inventory, Product, Warehouse)
        .join(Product, Inventory.product_id == Product.id)
        .join(Warehouse, Inventory.warehouse_id == Warehouse.id)
        .filter(Product.is_active == True)
        .all()
    )

    # ── 近 90 天出库量（按产品聚合）──
    sales_rows = (
        db.query(
            SaleOrderItem.product_id,
            func.sum(SaleOrderItem.quantity).label("sold_qty"),
        )
        .join(SaleOrder, SaleOrderItem.order_id == SaleOrder.id)
        .filter(
            SaleOrder.order_date >= cutoff_90,
            SaleOrder.status != SaleOrderStatus.CANCELLED,
        )
        .group_by(SaleOrderItem.product_id)
        .all()
    )
    sales_map = {r.product_id: float(r.sold_qty or 0) for r in sales_rows}

    # ── 1. 缺货率 = 低于 min_stock 的 SKU 数 / 总 SKU 数 ──
    # 按 product_id 聚合库存量；同时建立 product_id → Product 的 dict 索引
    product_qty_map: dict[int, float] = {}
    product_obj_map: dict[int, Product] = {}
    for inv, prod, wh in inv_rows:
        product_qty_map[prod.id] = product_qty_map.get(prod.id, 0) + inv.quantity
        product_obj_map[prod.id] = prod

    total_sku = len(product_qty_map)
    stockout_count = 0
    for pid, qty in product_qty_map.items():
        prod_obj = product_obj_map.get(pid)
        if prod_obj and qty < prod_obj.min_stock:
            stockout_count += 1

    stockout_rate = round(stockout_count / total_sku, 4) if total_sku > 0 else 0

    # ── 2. ABC 分类分布（批量：一次查询算出所有产品分类）──
    abc_dist = {"A": 0, "B": 0, "C": 0}
    product_ids_with_stock = list(product_qty_map.keys())
    revenue_rows = (
        db.query(
            SaleOrderItem.product_id,
            func.sum(SaleOrderItem.total_price).label("rev"),
        )
        .join(SaleOrder, SaleOrderItem.order_id == SaleOrder.id)
        .filter(
            SaleOrder.order_date >= cutoff_90,
            SaleOrder.status != SaleOrderStatus.CANCELLED,
        )
        .group_by(SaleOrderItem.product_id)
        .order_by(func.sum(SaleOrderItem.total_price).desc(), SaleOrderItem.product_id.asc())
        .all()
    )
    total_rev = sum(float(r.rev or 0) for r in revenue_rows)
    abc_map: dict[int, str] = {}
    if total_rev > 0:
        cum = 0.0
        for row in revenue_rows:
            cum += float(row.rev or 0)
            ratio = cum / total_rev
            abc_map[row.product_id] = "A" if ratio <= 0.70 else ("B" if ratio <= 0.90 else "C")
    # 仅统计有库存的产品
    for pid in product_ids_with_stock:
        abc_class = abc_map.get(pid, "C")
        abc_dist[abc_class] = abc_dist.get(abc_class, 0) + 1

    # ── 3. 可供应天数分布 ──
    days_of_supply = {"lt_7": 0, "7_30": 0, "gt_30": 0}
    for pid, qty in product_qty_map.items():
        avg_daily = sales_map.get(pid, 0) / 90.0
        if avg_daily <= 0:
            days_of_supply["gt_30"] += 1
            continue
        dos = qty / avg_daily
        if dos < 7:
            days_of_supply["lt_7"] += 1
        elif dos <= 30:
            days_of_supply["7_30"] += 1
        else:
            days_of_supply["gt_30"] += 1

    # ── 4. 持有成本 = capital_occupied × 年持有成本率 ──
    capital_occupied = base_kpi["capital_occupied"]
    holding_cost = round(capital_occupied * ANNUAL_HOLDING_COST_RATE, 2)

    # ── 5. 问题产品明细 ──
    problem_products = []
    for inv, prod, wh in inv_rows:
        qty = inv.quantity
        issue_type = None
        severity = "low"

        if qty < prod.min_stock:
            issue_type = "stockout"
            if qty == 0:
                severity = "high"
            else:
                ratio = qty / prod.min_stock if prod.min_stock > 0 else 0
                severity = "high" if ratio < 0.3 else "medium"
        elif qty > 0 and sales_map.get(prod.id, 0) == 0:
            issue_type = "dead"
            severity = "medium"
        elif prod.max_stock > 0 and qty > prod.max_stock:
            issue_type = "overstock"
            ratio = (qty - prod.max_stock) / prod.max_stock if prod.max_stock > 0 else 0
            severity = "high" if ratio > 0.5 else "medium"

        if issue_type:
            problem_products.append({
                "product_id": prod.id,
                "product_name": prod.name,
                "product_code": prod.code,
                "warehouse_name": wh.name,
                "current_qty": float(qty),
                "min_stock": float(prod.min_stock),
                "issue_type": issue_type,
                "severity": severity,
            })

    return {
        "stockout_rate": stockout_rate,
        "abc_distribution": abc_dist,
        "days_of_supply": days_of_supply,
        "holding_cost": holding_cost,
        "holding_cost_period": "annual",
        "turnover_days": base_kpi["turnover_days"],
        "dead_stock_count": base_kpi["dead_stock_count"],
        "dead_stock_pct": base_kpi["dead_stock_pct"],
        "capital_occupied": capital_occupied,
        "problem_products": problem_products,
    }
