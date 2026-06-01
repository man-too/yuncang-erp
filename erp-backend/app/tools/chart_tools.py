"""图表渲染工具 — 查询数据 + 直接返回完整 ECharts option"""

from datetime import date, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models.inventory import Inventory, Warehouse, InventoryAlert
from app.models.product import Product
from app.models.supplier import Supplier, SupplierEvaluation
from app.models.purchase import PurchaseOrder
from app.models.sale import SaleOrder, SaleOrderItem


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "render_inventory_heatmap",
            "description": "生成库存热力图(ECharts)，展示各仓库×各产品的库存状态，用颜色深浅表示缺货严重程度。当用户询问库存风险、低库存产品时调用",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "render_sales_trend",
            "description": "生成销售趋势折线图(ECharts)，展示近6个月月度销量趋势及预测。当用户询问销售趋势、销量走势、历史销量时调用",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "render_supplier_ranking",
            "description": "生成供应商评分对比柱状图(ECharts)，支持多维度切换(质量/交付/价格/服务/综合/交付率/收货率)。当用户询问供应商排名、供应商对比时调用",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "recommend_restock",
            "description": "综合库存水位、近30天销量、供应商交期等多维度数据，智能推荐补货清单和补货量。使用时建议先分别调用 query_inventory 和 query_sales_history 获取基础数据",
            "parameters": {
                "type": "object",
                "properties": {
                    "product_ids": {
                        "type": "array", "items": {"type": "integer"},
                        "description": "要分析的产品ID列表，为空则分析全部低库存产品",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "recommend_supplier",
            "description": "为指定产品智能推荐最佳供应商，综合质量评分、交付评分、价格评分、服务评分、历史合作次数、交付率和交期天数等多因素。使用时建议先调用 query_products 和 query_suppliers 获取基础数据",
            "parameters": {
                "type": "object",
                "properties": {
                    "product_id": {"type": "integer", "description": "产品ID，必需"},
                },
                "required": ["product_id"],
            },
        },
    },
]


def execute(name: str, args: dict, db: Session) -> dict | None:
    if name == "render_inventory_heatmap":
        return _render_inventory_heatmap(db)
    if name == "render_sales_trend":
        return _render_sales_trend(db)
    if name == "render_supplier_ranking":
        return _render_supplier_ranking(db)
    if name == "recommend_restock":
        return _recommend_restock(args, db)
    if name == "recommend_supplier":
        return _recommend_supplier(args, db)
    return None


# ── 1. Inventory Heatmap ──────────────────────────────────────────────

def _build_low_stock_table(db: Session) -> list[dict]:
    """生成低库存产品表格数据"""
    from datetime import date, timedelta
    rows = (
        db.query(Inventory, Product, Warehouse.name.label("wname"))
        .join(Product, Inventory.product_id == Product.id)
        .join(Warehouse, Inventory.warehouse_id == Warehouse.id)
        .filter(Inventory.quantity <= Product.min_stock, Inventory.quantity >= 0)
        .order_by(Inventory.quantity)
        .limit(20)
        .all()
    )
    if not rows:
        return []

    thirty_days_ago = date.today() - timedelta(days=30)
    table_rows = []
    for inv, prod, wname in rows:
        sales_30d = (
            db.query(func.sum(SaleOrderItem.quantity))
            .join(SaleOrder, SaleOrder.id == SaleOrderItem.order_id)
            .filter(SaleOrderItem.product_id == prod.id, SaleOrder.order_date >= thirty_days_ago)
            .scalar()
        ) or 0
        status = "缺货" if inv.quantity == 0 else "严重不足" if inv.quantity < prod.min_stock * 0.5 else "偏低"
        table_rows.append({
            "产品": prod.name,
            "仓库": wname,
            "当前库存": float(inv.quantity),
            "安全库存": float(prod.min_stock),
            "近30天销量": float(sales_30d),
            "建议补货量": max(int(float(prod.max_stock) - float(inv.quantity)), 0),
            "状态": status,
        })

    return table_rows


def _render_inventory_heatmap(db: Session) -> dict:
    """返回库存热力图 + 低库存表格"""
    rows = (
        db.query(
            Product.name.label("product_name"),
            Warehouse.name.label("warehouse_name"),
            Inventory.quantity,
            Product.min_stock,
            Product.max_stock,
            Product.unit,
        )
        .join(Inventory, Inventory.product_id == Product.id)
        .join(Warehouse, Inventory.warehouse_id == Warehouse.id)
        .filter(Inventory.quantity >= 0, Product.is_active == True)
        .order_by(Inventory.quantity)
        .limit(200)
        .all()
    )

    blocks = []

    if not rows:
        blocks.append({
            "type": "table",
            "columns": [{"key": "msg", "title": "提示"}],
            "rows": [{"msg": "暂无库存数据"}],
        })
        return {"_render": True, "blocks": blocks}

    # Build warehouse × product matrix
    wh_names = sorted(set(r.warehouse_name for r in rows))
    prod_names = []
    seen = set()
    for r in rows:
        if r.product_name not in seen:
            prod_names.append(r.product_name)
            seen.add(r.product_name)

    wh_idx = {n: i for i, n in enumerate(wh_names)}
    prod_idx = {n: i for i, n in enumerate(prod_names)}

    heatmap_data = []
    for r in rows:
        wi = wh_idx.get(r.warehouse_name, 0)
        pi = prod_idx.get(r.product_name, 0)
        ratio = r.quantity / r.min_stock if r.min_stock > 0 else 1.0
        level = min(max(1.0 - ratio / 2.0, 0), 1) if ratio < 1 else max(1.0 - ratio / 4.0, 0)
        if r.quantity == 0:
            level = 1.0
        heatmap_data.append([wi, pi, round(level, 2)])

    # Chart block
    blocks.append({
        "type": "chart",
        "chartType": "heatmap",
        "data": {
            "title": {"text": "库存状态热力图", "left": "center", "textStyle": {"fontSize": 14, "fontWeight": "bold"}},
            "tooltip": {"position": "top", "formatter": "function(params) { return '<b>'+params.name+'</b><br/>状态等级: '+params.data.value[2]; }"},
            "grid": {"left": 160, "right": 60, "top": 50, "bottom": 60},
            "xAxis": {"type": "category", "data": wh_names, "splitArea": {"show": True}, "axisLabel": {"fontSize": 11}},
            "yAxis": {"type": "category", "data": prod_names, "splitArea": {"show": True}, "axisLabel": {"fontSize": 11}},
            "visualMap": {"min": 0, "max": 1, "calculable": True, "orient": "horizontal", "left": "center", "bottom": 0,
                          "inRange": {"color": ["#e8f5e9", "#fff9c4", "#ffcc80", "#ef5350"]}},
            "series": [{"name": "库存状态", "type": "heatmap", "data": heatmap_data,
                        "label": {"show": len(heatmap_data) < 80},
                        "emphasis": {"itemStyle": {"shadowBlur": 10, "shadowColor": "rgba(0,0,0,0.5)"}}}],
        },
    })

    # Low stock table block
    table_rows = _build_low_stock_table(db)
    if table_rows:
        blocks.append({
            "type": "table",
            "columns": [
                {"key": "产品", "title": "产品"},
                {"key": "仓库", "title": "仓库"},
                {"key": "当前库存", "title": "当前库存"},
                {"key": "安全库存", "title": "安全库存"},
                {"key": "近30天销量", "title": "近30天销量"},
                {"key": "建议补货量", "title": "建议补货量"},
                {"key": "状态", "title": "状态"},
            ],
            "rows": table_rows,
        })

    return {"_render": True, "blocks": blocks}


# ── 2. Sales Trend ────────────────────────────────────────────────────

def _render_sales_trend(db: Session) -> dict:
    """返回销售趋势折线图 chart block"""
    six_months_ago = date.today() - timedelta(days=180)
    date_fmt = func.date_format(SaleOrder.order_date, "%Y-%m")

    rows = (
        db.query(
            date_fmt.label("month"),
            func.sum(SaleOrderItem.quantity).label("qty"),
            func.sum(SaleOrderItem.total_price).label("amount"),
        )
        .join(SaleOrderItem, SaleOrderItem.order_id == SaleOrder.id)
        .filter(SaleOrder.order_date >= six_months_ago, SaleOrder.status != "cancelled")
        .group_by(date_fmt)
        .order_by(date_fmt)
        .all()
    )

    if not rows:
        return {
            "type": "table",
            "columns": [{"key": "msg", "title": "提示"}],
            "rows": [{"msg": "暂无近6个月销售数据"}],
            "_render": True,
        }

    months = [r.month for r in rows]
    amounts = [float(r.amount or 0) for r in rows]

    # Simple linear forecast: next 3 months
    if len(amounts) >= 2:
        n = len(amounts)
        x_mean = (n - 1) / 2
        y_mean = sum(amounts) / n
        num = sum(i * amounts[i] for i in range(n)) - n * x_mean * y_mean
        den = sum(i * i for i in range(n)) - n * x_mean * x_mean
        slope = num / den if den != 0 else 0
        intercept = y_mean - slope * x_mean
        forecast_vals = [slope * (n + i) + intercept for i in range(3)]
        # Ensure non-negative
        forecast_vals = [max(0, v) for v in forecast_vals]
        last_month = months[-1]
        forecast_months = _next_months(last_month, 3)
    else:
        forecast_vals = amounts[-3:] if amounts else [0, 0, 0]
        forecast_months = _next_months(months[-1] if months else "2026-01", 3)

    return {
        "type": "chart",
        "chartType": "line",
        "data": {
            "title": {
                "text": "月度销售趋势（近6个月 + 预测）",
                "left": "center",
                "textStyle": {"fontSize": 14, "fontWeight": "bold"},
            },
            "tooltip": {
                "trigger": "axis",
                "axisPointer": {"type": "cross", "crossStyle": {"color": "#999"}},
            },
            "legend": {"data": ["历史销量", "预测销量"], "bottom": 0},
            "toolbox": {
                "feature": {
                    "saveAsImage": {},
                    "dataView": {"readOnly": False},
                    "restore": {},
                }
            },
            "dataZoom": [
                {"type": "inside", "start": 0, "end": 100},
                {"type": "slider", "start": 0, "end": 100, "bottom": 30},
            ],
            "grid": {"left": 60, "right": 30, "top": 50, "bottom": 80},
            "xAxis": {
                "type": "category",
                "data": months + forecast_months,
                "axisLabel": {"fontSize": 11},
            },
            "yAxis": {"type": "value", "name": "金额 (¥)", "nameTextStyle": {"fontSize": 12}},
            "series": [
                {
                    "name": "历史销量",
                    "type": "line",
                    "smooth": True,
                    "data": amounts + [None] * len(forecast_months),
                    "showSymbol": True,
                    "symbol": "circle",
                    "symbolSize": 7,
                    "lineStyle": {"color": "#5470c6", "width": 2.5},
                    "areaStyle": {"color": "rgba(84,112,198,0.12)"},
                    "emphasis": {
                        "itemStyle": {"color": "#5470c6", "borderColor": "#fff", "borderWidth": 2},
                        "scale": 1.8,
                    },
                },
                {
                    "name": "预测销量",
                    "type": "line",
                    "smooth": True,
                    "data": [None] * len(amounts) + forecast_vals,
                    "showSymbol": True,
                    "symbol": "diamond",
                    "symbolSize": 9,
                    "lineStyle": {"color": "#fc8452", "width": 2.5, "type": "dashed"},
                    "areaStyle": {"color": "rgba(252,132,82,0.1)"},
                    "itemStyle": {"color": "#fc8452"},
                    "emphasis": {
                        "focus": "series",
                        "itemStyle": {"color": "#fc8452", "borderColor": "#fff", "borderWidth": 2},
                        "scale": 1.6,
                    },
                },
            ],
        },
        "_render": True,
    }


def _next_months(last_month: str, count: int) -> list[str]:
    """生成后续月份列表"""
    try:
        year, month = int(last_month[:4]), int(last_month[5:7])
    except (ValueError, IndexError):
        return [f"M+{i+1}" for i in range(count)]
    result = []
    for i in range(count):
        month += 1
        if month > 12:
            month = 1
            year += 1
        result.append(f"{year}-{month:02d}")
    return result


# ── 3. Supplier Ranking ───────────────────────────────────────────────

def _render_supplier_ranking(db: Session) -> dict:
    """返回供应商排名柱状图 chart block"""
    suppliers = (
        db.query(Supplier)
        .filter(Supplier.status == "active")
        .order_by(Supplier.rating.desc())
        .limit(20)
        .all()
    )

    if not suppliers:
        return {
            "type": "table",
            "columns": [{"key": "msg", "title": "提示"}],
            "rows": [{"msg": "暂无活跃供应商数据"}],
            "_render": True,
        }

    names = [s.name for s in suppliers]
    metrics_def = [
        ("quality_score", "质量评分", "#5470c6"),
        ("delivery_score", "交付评分", "#91cc75"),
        ("price_score", "价格评分", "#fac858"),
        ("service_score", "服务评分", "#ee6666"),
        ("total_score", "综合评分", "#73c0de"),
    ]

    # Fetch average evaluation scores per supplier
    data_by_supplier = {}
    for s in suppliers:
        evals = (
            db.query(
                func.avg(SupplierEvaluation.quality_score).label("q"),
                func.avg(SupplierEvaluation.delivery_score).label("d"),
                func.avg(SupplierEvaluation.price_score).label("p"),
                func.avg(SupplierEvaluation.service_score).label("s"),
                func.avg(SupplierEvaluation.total_score).label("total_label"),
            )
            .filter(SupplierEvaluation.supplier_id == s.id)
            .first()
        )
        data_by_supplier[s.id] = {
            "quality_score": round(float(evals.q or 0), 1),
            "delivery_score": round(float(evals.d or 0), 1),
            "price_score": round(float(evals.p or 0), 1),
            "service_score": round(float(evals.s or 0), 1),
            "total_score": round(float(evals.total_label or 0), 1),
        }

    series_list = []
    for key, label, color in metrics_def:
        values = [data_by_supplier.get(s.id, {}).get(key, 0) for s in suppliers]
        series_list.append({
            "name": label,
            "type": "bar",
            "data": values,
            "itemStyle": {"color": color},
            "barMaxWidth": 16,
        })

    return {
        "type": "chart",
        "chartType": "bar",
        "data": {
            "title": {
                "text": "供应商评分对比",
                "left": "center",
                "textStyle": {"fontSize": 14, "fontWeight": "bold"},
            },
            "tooltip": {"trigger": "axis"},
            "legend": {
                "data": [m[1] for m in metrics_def],
                "bottom": 0,
                "type": "scroll",
            },
            "toolbox": {
                "feature": {
                    "saveAsImage": {},
                    "dataView": {"readOnly": False},
                    "restore": {},
                }
            },
            "grid": {"left": 80, "right": 30, "top": 50, "bottom": 80},
            "xAxis": {
                "type": "category",
                "data": names,
                "axisLabel": {"rotate": 20, "fontSize": 11},
            },
            "yAxis": {"type": "value", "min": 0, "name": "评分", "nameTextStyle": {"fontSize": 12}},
            "series": series_list,
        },
        "_render": True,
    }


# ── 4. Recommend Restock ──────────────────────────────────────────────

def _recommend_restock(args: dict, db: Session) -> dict:
    """推荐补货清单（准备数据供 LLM 分析）"""
    q = (
        db.query(Inventory, Product, Warehouse.name.label("wname"))
        .join(Product, Inventory.product_id == Product.id)
        .join(Warehouse, Inventory.warehouse_id == Warehouse.id)
        .filter(Inventory.quantity <= Product.min_stock, Inventory.quantity >= 0)
    )
    if args.get("product_ids"):
        q = q.filter(Inventory.product_id.in_(args["product_ids"]))

    rows = q.order_by(Inventory.quantity).limit(30).all()

    if not rows:
        return {"recommendations": [], "message": "暂无不需补货，库存充足"}

    # Compute suggested order qty based on min/max stock
    thirty_days_ago = date.today() - timedelta(days=30)
    recommendations = []
    for inv, prod, wname in rows:
        # Get recent daily sales
        sales_row = (
            db.query(func.sum(SaleOrderItem.quantity))
            .join(SaleOrder, SaleOrder.id == SaleOrderItem.order_id)
            .filter(
                SaleOrderItem.product_id == prod.id,
                SaleOrder.order_date >= thirty_days_ago,
                SaleOrder.status != "cancelled",
            )
            .scalar()
        )
        daily_sales = (float(sales_row or 0)) / 30.0

        # Suggest order quantity
        gap = prod.max_stock - inv.quantity
        if daily_sales > 0:
            suggested = max(int(daily_sales * prod.min_stock / max(inv.quantity, 1) * 1.5), int(gap))
        else:
            suggested = int(max(gap, prod.max_stock * 0.3))

        if suggested <= 0:
            continue

        recommendations.append({
            "product_id": prod.id,
            "product_name": prod.name,
            "product_code": prod.code,
            "warehouse": wname,
            "current_qty": float(inv.quantity),
            "min_stock": float(prod.min_stock),
            "max_stock": float(prod.max_stock),
            "suggested_qty": min(suggested, int(prod.max_stock * 2)),
            "unit": prod.unit,
            "daily_sales_avg": round(daily_sales, 1),
            "priority": "critical" if inv.quantity == 0 else "high" if inv.quantity < prod.min_stock * 0.5 else "medium",
        })

    return {"recommendations": recommendations, "total": len(recommendations)}


# ── 5. Recommend Supplier ─────────────────────────────────────────────

def _recommend_supplier(args: dict, db: Session) -> dict:
    """为指定产品推荐最佳供应商（准备数据供 LLM 分析）"""
    product_id = args.get("product_id")
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        return {"error": f"产品 #{product_id} 不存在"}

    # Get all active suppliers with evaluations and order stats
    suppliers = db.query(Supplier).filter(Supplier.status == "active").all()
    results = []
    for s in suppliers:
        evals = (
            db.query(
                func.avg(SupplierEvaluation.quality_score).label("q"),
                func.avg(SupplierEvaluation.delivery_score).label("d"),
                func.avg(SupplierEvaluation.price_score).label("p"),
                func.avg(SupplierEvaluation.service_score).label("s"),
                func.avg(SupplierEvaluation.total_score).label("total_label"),
            )
            .filter(SupplierEvaluation.supplier_id == s.id)
            .first()
        )

        # Order history for this product from this supplier
        from app.models.purchase import PurchaseOrderItem, PurchaseOrder as PO
        po_count = (
            db.query(func.count(PurchaseOrderItem.id))
            .join(PO, PO.id == PurchaseOrderItem.order_id)
            .filter(PO.supplier_id == s.id, PurchaseOrderItem.product_id == product_id)
            .scalar()
        )

        results.append({
            "supplier_id": s.id,
            "supplier_name": s.name,
            "rating": float(s.rating),
            "delivery_lead_time": s.delivery_lead_time,
            "quality_score": round(float(evals.q or 0), 1),
            "delivery_score": round(float(evals.d or 0), 1),
            "price_score": round(float(evals.p or 0), 1),
            "service_score": round(float(evals.s or 0), 1),
            "total_score": round(float(evals.total_label or 0), 1),
            "past_orders": int(po_count or 0),
        })

    return {
        "product": {"id": product.id, "name": product.name, "code": product.code},
        "suppliers": results,
        "total": len(results),
    }
