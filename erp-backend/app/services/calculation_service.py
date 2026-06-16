"""计算服务 — 纯 Python 计算，不依赖 LLM

包含:
- calc_reorder_point: 再订货点 (ROP) + 安全库存
- calc_inventory_kpi: 库存 KPI (周转天数 / 呆滞库存 / 资金占用)
"""

import math
import logging
from datetime import datetime, timedelta, date
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models.product import Product, ProductCategory
from app.models.supplier import Supplier, SupplierEvaluation
from app.models.inventory import Inventory, InventoryRecord
from app.models.purchase import PurchaseOrder, PurchaseOrderItem, PurchaseInbound, PurchaseOrderStatus
from app.models.sale import SaleOrder, SaleOrderItem, SaleOrderStatus

logger = logging.getLogger(__name__)


# ────────────────────────────────────────────
# 1. 再订货点 (Reorder Point)
# ────────────────────────────────────────────

# ABC 分类 → 服务水平 → z 值
_ABC_Z = {
    "A": 1.65,   # 95% 服务水平
    "B": 1.28,   # 90%
    "C": 1.04,   # 85%
}


def _should_use_forecast(override: bool | None = None) -> bool:
    from app.config import settings
    if override is not None:
        return override
    return settings.FORECAST_ENABLED


def _classify_abc(product_id: int, db: Session) -> str:
    """简单 ABC 分类：按近 90 天出库金额在所有产品中的累计占比。
    A: 前 70%, B: 70-90%, C: 90-100%（与 batch_calc_reorder_point 保持一致）。
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
        .order_by(func.sum(SaleOrderItem.total_price).desc(), SaleOrderItem.product_id.asc())
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
            if ratio <= 0.70:
                return "A"
            elif ratio <= 0.90:
                return "B"
            else:
                return "C"

    # 产品不在出库记录中
    return "C"


def calc_reorder_point(
    product_id: int,
    db: Session,
    supplier_id: int | None = None,
    use_forecast: bool | None = None,
) -> dict:
    """计算再订货点 (ROP)

    ROP = avg_daily_sales × lead_time + safety_stock
    safety_stock = z × σ_daily × √(lead_time)

    当 use_forecast=True 时，用 Darts/Prophet 预测替换简单均值，
    加权融合：w × forecast + (1-w) × formula
    """
    product = db.get(Product, product_id)
    if not product:
        return {"error": f"产品 {product_id} 不存在"}

    # ── 产品级交期覆盖 ──
    lead_time = 7  # 默认 7 天
    if product.lead_time_override is not None:
        lead_time = product.lead_time_override
    elif supplier_id:
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

    # ── 当前库存（所有仓库总量）──
    current_qty = float(
        db.query(func.sum(Inventory.quantity))
        .filter(Inventory.product_id == product_id)
        .scalar() or 0
    )

    # ── 在途采购量 ──
    in_transit_qty = float(
        db.query(func.sum(PurchaseOrderItem.quantity - PurchaseOrderItem.received_quantity))
        .join(PurchaseOrder, PurchaseOrderItem.order_id == PurchaseOrder.id)
        .filter(
            PurchaseOrderItem.product_id == product_id,
            PurchaseOrder.status.in_([
                PurchaseOrderStatus.APPROVED,
                PurchaseOrderStatus.PARTIALLY_RECEIVED,
            ]),
        )
        .scalar() or 0
    )

    # ── 缺货积压量（已下销售单未发货）──
    backlog_qty = float(
        db.query(func.sum(SaleOrderItem.quantity - SaleOrderItem.shipped_quantity))
        .join(SaleOrder, SaleOrderItem.order_id == SaleOrder.id)
        .filter(
            SaleOrderItem.product_id == product_id,
            SaleOrder.status.in_([
                SaleOrderStatus.APPROVED,
                SaleOrderStatus.PARTIALLY_SHIPPED,
            ]),
            SaleOrderItem.quantity > SaleOrderItem.shipped_quantity,
        )
        .scalar() or 0
    )

    # ── 近 60 天日销量 ──
    today = date.today()
    cutoff = today - timedelta(days=60)
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

    # ── 7天/30天均值 + 趋势 ──
    seven_days_ago = today - timedelta(days=7)
    thirty_days_ago = today - timedelta(days=30)
    sales_7d = 0.0
    sales_30d = 0.0
    for r in daily_rows:
        d = r.d
        if isinstance(d, str):
            try:
                d = datetime.strptime(d, "%Y-%m-%d").date()
            except Exception:
                try:
                    d = datetime.fromisoformat(d).date()
                except Exception:
                    continue
        elif isinstance(d, datetime):
            d = d.date()
        qty = float(r.qty or 0)
        if d >= seven_days_ago:
            sales_7d += qty
        if d >= thirty_days_ago:
            sales_30d += qty
    avg_7d = sales_7d / 7.0
    avg_30d = sales_30d / 30.0

    if avg_30d > 0:
        change_pct = (avg_7d - avg_30d) / avg_30d * 100
        if change_pct > 20:
            trend = "上升"
        elif change_pct < -20:
            trend = "下降"
        else:
            trend = "平稳"
    else:
        change_pct = 0.0
        trend = "平稳"

    sign = "+" if change_pct >= 0 else ""
    demand_desc = (
        f"近30天日均{round(avg_30d, 2)}件，"
        f"近7天日均{round(avg_7d, 2)}件，"
        f"趋势：{trend}({sign}{round(change_pct, 1)}%)"
    )

    if not daily_rows:
        # 无销量数据，返回基于 min_stock 的保守估算
        rop_value = product.min_stock or 0
        suggested_qty_no_sales = max(round(rop_value) - int(current_qty) - int(in_transit_qty), 0)
        return {
            "product_id": product_id,
            "product_name": product.name,
            "rop": rop_value,
            "avg_daily_sales": 0.0,
            "lead_time": lead_time,
            "safety_stock": product.min_stock or 0,
            "service_level": "85%",
            "abc_class": "C",
            "warning": "近60天无销量数据，使用 min_stock 作为保守值",
            # 新增字段（P0 状态快照）
            "current_qty": current_qty,
            "in_transit_qty": in_transit_qty,
            "backlog_qty": backlog_qty,
            "avg_daily_sales_30d": round(avg_30d, 2),
            "avg_daily_sales_7d": round(avg_7d, 2),
            "trend": trend,
            "trend_change_pct": round(change_pct, 1),
            "demand_desc": demand_desc,
            "suggested_qty": suggested_qty_no_sales,
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

    # ── 预测融合 ──
    forecast_result = None
    if _should_use_forecast(use_forecast):
        try:
            from app.services.forecast_service import forecast_product_demand
            forecast_result = forecast_product_demand(product_id, db, horizon_days=int(lead_time))
        except Exception as e:
            logger.warning(f"Forecast failed for product {product_id}: {e}")

    avg_daily, safety_stock, forecast_fields = _blend_forecast_into_rop(
        avg_daily, safety_stock, forecast_result, z
    )

    rop = avg_daily * lead_time + safety_stock
    # ROP 驱动的建议量；若库存低于 min_stock 则至少补到 min_stock
    rop_based = max(round(rop) - int(current_qty) - int(in_transit_qty), 0)
    min_stock_gap = max(round(product.min_stock or 0) - int(current_qty) - int(in_transit_qty), 0)
    raw_suggested = max(rop_based, min_stock_gap)
    box_qty = product.box_qty or 1
    suggested_qty = math.ceil(raw_suggested / box_qty) * box_qty if raw_suggested > 0 else 0

    return {
        "product_id": product_id,
        "product_name": product.name,
        "rop": int(round(rop)),
        "avg_daily_sales": round(avg_daily, 2),
        "lead_time": lead_time,
        "safety_stock": int(round(safety_stock)),
        "service_level": {"A": "95%", "B": "90%", "C": "85%"}[abc],
        "abc_class": abc,
        # 新增字段（P0 状态快照）
        "current_qty": current_qty,
        "in_transit_qty": in_transit_qty,
        "backlog_qty": backlog_qty,
        "avg_daily_sales_30d": round(avg_30d, 2),
        "avg_daily_sales_7d": round(avg_7d, 2),
        "trend": trend,
        "trend_change_pct": round(change_pct, 1),
        "demand_desc": demand_desc,
        "suggested_qty": suggested_qty,
        **forecast_fields,
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


def _blend_forecast_into_rop(
    avg_daily: float,
    safety_stock: float,
    forecast_result: "ForecastResult | None",
    z: float,
) -> tuple[float, float, dict]:
    """预测融合：用置信度加权混合预测值和公式值

    Returns: (blended_avg_daily, blended_safety_stock, forecast_fields)
    """
    if forecast_result is None or forecast_result.confidence_score < 0.3:
        return avg_daily, safety_stock, {}

    w = forecast_result.confidence_score
    f_avg = forecast_result.avg_daily_forecast
    f_ss = z * (forecast_result.avg_daily_high - forecast_result.avg_daily_low) / 2
    blended_avg = w * f_avg + (1 - w) * avg_daily
    blended_ss = w * f_ss + (1 - w) * safety_stock
    fields = {
        "forecast_avg_daily": round(forecast_result.avg_daily_forecast, 2),
        "forecast_model": forecast_result.model_used,
        "forecast_confidence_low": round(forecast_result.avg_daily_low, 2),
        "forecast_confidence_mid": round(forecast_result.avg_daily_forecast, 2),
        "forecast_confidence_high": round(forecast_result.avg_daily_high, 2),
        "forecast_seasonality": forecast_result.seasonality_type,
        "forecast_confidence_score": forecast_result.confidence_score,
    }
    return blended_avg, blended_ss, fields


def batch_calc_reorder_point(
    product_ids: list[int],
    db: Session,
    use_forecast: bool | None = None,
) -> dict[int, dict]:
    """批量计算再订货点 (ROP)，避免逐个查询的开销"""
    from app.models.product import Product
    from app.models.supplier import Supplier
    from app.models.purchase import PurchaseOrder, PurchaseOrderItem, PurchaseOrderStatus
    from app.models.sale import SaleOrder, SaleOrderItem, SaleOrderStatus
    from app.models.inventory import Inventory

    if not product_ids:
        return {}

    # ── 批量预测（可选）──
    forecast_map: dict[int, "ForecastResult"] = {}
    if _should_use_forecast(use_forecast):
        try:
            from app.services.forecast_service import forecast_batch_demand
            forecast_map = forecast_batch_demand(product_ids, db, horizon_days=30)
        except Exception as e:
            logger.warning(f"Batch forecast failed: {e}")

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

    # 产品级交期覆盖
    for pid, prod in products.items():
        if prod.lead_time_override is not None:
            lead_time_map[pid] = prod.lead_time_override

    # ── 当前库存（按产品聚合所有仓库）──
    inv_rows = (
        db.query(
            Inventory.product_id,
            func.sum(Inventory.quantity).label("total"),
        )
        .filter(Inventory.product_id.in_(product_ids))
        .group_by(Inventory.product_id)
        .all()
    )
    inv_map: dict[int, float] = {pid: float(total or 0) for pid, total in inv_rows}

    # ── 在途采购量（批量）──
    in_transit_rows = (
        db.query(
            PurchaseOrderItem.product_id,
            func.sum(PurchaseOrderItem.quantity - PurchaseOrderItem.received_quantity).label("qty"),
        )
        .join(PurchaseOrder, PurchaseOrderItem.order_id == PurchaseOrder.id)
        .filter(
            PurchaseOrderItem.product_id.in_(product_ids),
            PurchaseOrder.status.in_([
                PurchaseOrderStatus.APPROVED,
                PurchaseOrderStatus.PARTIALLY_RECEIVED,
            ]),
        )
        .group_by(PurchaseOrderItem.product_id)
        .all()
    )
    in_transit_map: dict[int, float] = {pid: float(qty or 0) for pid, qty in in_transit_rows}

    # ── 缺货积压量（批量）──
    backlog_rows = (
        db.query(
            SaleOrderItem.product_id,
            func.sum(SaleOrderItem.quantity - SaleOrderItem.shipped_quantity).label("qty"),
        )
        .join(SaleOrder, SaleOrderItem.order_id == SaleOrder.id)
        .filter(
            SaleOrderItem.product_id.in_(product_ids),
            SaleOrder.status.in_([
                SaleOrderStatus.APPROVED,
                SaleOrderStatus.PARTIALLY_SHIPPED,
            ]),
            SaleOrderItem.quantity > SaleOrderItem.shipped_quantity,
        )
        .group_by(SaleOrderItem.product_id)
        .all()
    )
    backlog_map: dict[int, float] = {pid: float(qty or 0) for pid, qty in backlog_rows}

    # ── 近 60 天日销量 ──
    today = date.today()
    cutoff = today - timedelta(days=60)
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

    # 按 product_id 聚合销量 + 切割 7d/30d
    sales_map: dict[int, list[float]] = {}
    sales_7d_map: dict[int, float] = {}
    sales_30d_map: dict[int, float] = {}
    seven_days_ago = today - timedelta(days=7)
    thirty_days_ago = today - timedelta(days=30)
    for pid, d, qty in daily_rows:
        if isinstance(d, str):
            try:
                d = datetime.strptime(d, "%Y-%m-%d").date()
            except Exception:
                try:
                    d = datetime.fromisoformat(d).date()
                except Exception:
                    continue
        elif isinstance(d, datetime):
            d = d.date()
        qf = float(qty or 0)
        sales_map.setdefault(pid, []).append(qf)
        if d >= seven_days_ago:
            sales_7d_map[pid] = sales_7d_map.get(pid, 0.0) + qf
        if d >= thirty_days_ago:
            sales_30d_map[pid] = sales_30d_map.get(pid, 0.0) + qf

    # ── ABC 分类（按近90天销售额累计占比）──
    cutoff_90 = today - timedelta(days=90)
    revenue_rows = (
        db.query(
            SaleOrderItem.product_id,
            func.sum(SaleOrderItem.total_price).label("rev"),
        )
        .join(SaleOrder, SaleOrderItem.order_id == SaleOrder.id)
        .filter(
            SaleOrder.order_date >= cutoff_90,
            SaleOrder.status != "cancelled",
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
            if ratio <= 0.70:
                abc_map[row.product_id] = "A"
            elif ratio <= 0.90:
                abc_map[row.product_id] = "B"
            else:
                abc_map[row.product_id] = "C"

    _ABC_Z_BATCH = {"A": 1.65, "B": 1.28, "C": 1.04}
    _ABC_SERVICE = {"A": "95%", "B": "90%", "C": "85%"}

    result: dict[int, dict] = {}
    for pid in product_ids:
        prod = products.get(pid)
        if not prod:
            continue
        lt = lead_time_map.get(pid, 7)
        current_qty = inv_map.get(pid, 0.0)
        in_transit_qty = in_transit_map.get(pid, 0.0)
        backlog_qty = backlog_map.get(pid, 0.0)
        avg_7d = sales_7d_map.get(pid, 0.0) / 7.0
        avg_30d = sales_30d_map.get(pid, 0.0) / 30.0

        if avg_30d > 0:
            change_pct = (avg_7d - avg_30d) / avg_30d * 100
            if change_pct > 20:
                trend = "上升"
            elif change_pct < -20:
                trend = "下降"
            else:
                trend = "平稳"
        else:
            change_pct = 0.0
            trend = "平稳"

        sign = "+" if change_pct >= 0 else ""
        demand_desc = (
            f"近30天日均{round(avg_30d, 2)}件，"
            f"近7天日均{round(avg_7d, 2)}件，"
            f"趋势：{trend}({sign}{round(change_pct, 1)}%)"
        )

        quantities = sales_map.get(pid, [])
        abc = abc_map.get(pid, "C")
        z = _ABC_Z_BATCH.get(abc, 1.04)

        if not quantities:
            rop_val = prod.min_stock or 0
            safety_stock = prod.min_stock or 0
            avg_daily = 0.0
        else:
            sum_q = sum(quantities)
            k = len(quantities)
            avg_daily = sum_q / 60
            if k >= 2 and avg_daily > 0:
                ssd = sum((q - avg_daily) ** 2 for q in quantities)
                ssd += (60 - k) * (avg_daily ** 2)
                std_daily = math.sqrt(ssd / 60)
            else:
                std_daily = avg_daily * 0.3 if avg_daily > 0 else 0.0

            safety_stock = z * std_daily * math.sqrt(lt)
            rop_val = avg_daily * lt + safety_stock

        # ── 预测融合 ──
        # P1-5 修复：仅在有销量历史时融合预测；新品/冷品保留 min_stock 语义
        if quantities:
            fr = forecast_map.get(pid)
            avg_daily, safety_stock, batch_forecast_fields = _blend_forecast_into_rop(
                avg_daily, safety_stock, fr, z
            )
            rop_val = avg_daily * lt + safety_stock
        else:
            batch_forecast_fields = {}

        rop_based = max(round(rop_val) - int(current_qty) - int(in_transit_qty), 0)
        min_stock_gap = max(round(prod.min_stock or 0) - int(current_qty) - int(in_transit_qty), 0)
        raw_suggested = max(rop_based, min_stock_gap)
        box_qty = prod.box_qty or 1
        suggested_qty = math.ceil(raw_suggested / box_qty) * box_qty if raw_suggested > 0 else 0

        entry = {
            "product_id": pid,
            "product_name": prod.name,
            "rop": int(round(rop_val)),
            "avg_daily_sales": round(avg_daily, 2),
            "lead_time": lt,
            "safety_stock": int(round(safety_stock)),
            "service_level": _ABC_SERVICE.get(abc, "85%"),
            "abc_class": abc,
            # 新增字段（P0 状态快照）
            "current_qty": current_qty,
            "in_transit_qty": in_transit_qty,
            "backlog_qty": backlog_qty,
            "avg_daily_sales_30d": round(avg_30d, 2),
            "avg_daily_sales_7d": round(avg_7d, 2),
            "trend": trend,
            "trend_change_pct": round(change_pct, 1),
            "demand_desc": demand_desc,
            "suggested_qty": suggested_qty,
            **batch_forecast_fields,
        }
        if not quantities:
            entry["warning"] = "近60天无销量数据，使用 min_stock 作为保守值"
        result[pid] = entry

    return result
