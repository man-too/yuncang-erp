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
    {
        "type": "function",
        "function": {
            "name": "render_comprehensive_diagnosis",
            "description": "生成供应链综合诊断图表，包含健康评分雷达图、综合仪表盘和各维度分析表格。当用户询问综合诊断、供应链状况、全链路分析时调用",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "render_purchase_advice",
            "description": "生成采购建议图表，包含补货清单柱状图、推荐供应商表格和费用估算。当用户询问采购建议、补货推荐、需要采购什么时调用",
            "parameters": {"type": "object", "properties": {}, "required": []},
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
    if name == "render_comprehensive_diagnosis":
        return _render_comprehensive_diagnosis(db)
    if name == "render_purchase_advice":
        return _render_purchase_advice(db)
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

    # 数据量过大时降级为表格展示，避免热力图不可读
    if len(rows) > 60:
        blocks.append({
            "type": "table",
            "columns": [{"key": "msg", "title": "提示"}],
            "rows": [{"msg": f"库存数据量较大（{len(rows)}条产品×仓库组合），热力图将不可读，已自动切换为低库存表格展示。可通过筛选特定仓库或产品缩小范围。"}],
        })
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
            "tooltip": {"position": "top", "formatter": "{b}<br/>状态等级: {c}"},
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
    """返回供应商排名柱状图 chart block，根据数据量分级渲染"""
    suppliers = (
        db.query(Supplier)
        .filter(Supplier.status == "active")
        .order_by(Supplier.rating.desc())
        .all()
    )

    if not suppliers:
        return {
            "type": "table",
            "columns": [{"key": "msg", "title": "提示"}],
            "rows": [{"msg": "暂无活跃供应商数据"}],
            "_render": True,
        }

    n = len(suppliers)
    blocks = []

    # 数据量 >50: 图表只展示 Top 15
    chart_suppliers = suppliers[:15] if n > 50 else suppliers

    names = [s.name for s in chart_suppliers]

    metrics_def = [
        ("quality_score", "质量评分", "#5470c6"),
        ("delivery_score", "交付评分", "#91cc75"),
        ("price_score", "价格评分", "#fac858"),
        ("service_score", "服务评分", "#ee6666"),
        ("total_score", "综合评分", "#73c0de"),
    ]

    # Fetch average evaluation scores per chart supplier
    data_by_supplier = {}
    for s in chart_suppliers:
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
        values = [data_by_supplier.get(s.id, {}).get(key, 0) for s in chart_suppliers]
        series_list.append({
            "name": label,
            "type": "bar",
            "data": values,
            "itemStyle": {"color": color},
            "barMaxWidth": 16,
        })

    # Build chart options based on data volume
    if n <= 15:
        # 垂直柱状图 — 数据量小，直接展示
        chart_options = {
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
        }
    else:
        # 横向柱状图 + dataZoom — 数据量中等偏大
        title_text = "供应商评分对比（Top 15）" if n > 50 else "供应商评分对比"
        chart_options = {
            "title": {
                "text": title_text,
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
            "dataZoom": [
                {"type": "slider", "orient": "vertical", "right": 10, "start": 0, "end": 100},
                {"type": "inside", "orient": "vertical"},
            ],
            "grid": {"left": 140, "right": 60, "top": 50, "bottom": 30},
            "xAxis": {"type": "value", "min": 0, "name": "评分", "nameTextStyle": {"fontSize": 12}},
            "yAxis": {
                "type": "category",
                "data": names,
                "inverse": True,
                "axisLabel": {"fontSize": 11},
            },
            "series": series_list,
        }

    blocks.append({
        "type": "chart",
        "chartType": "bar",
        "data": chart_options,
    })

    # 数据量 >50: 追加完整排名表格
    if n > 50:
        # Compute scores for all suppliers for the table
        all_data = {}
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
            all_data[s.id] = {
                "quality_score": round(float(evals.q or 0), 1),
                "delivery_score": round(float(evals.d or 0), 1),
                "price_score": round(float(evals.p or 0), 1),
                "service_score": round(float(evals.s or 0), 1),
                "total_score": round(float(evals.total_label or 0), 1),
            }

        table_rows = []
        for i, s in enumerate(suppliers):
            scores = all_data.get(s.id, {})
            table_rows.append({
                "排名": i + 1,
                "供应商": s.name,
                "综合评分": scores.get("total_score", 0),
                "质量评分": scores.get("quality_score", 0),
                "交付评分": scores.get("delivery_score", 0),
                "价格评分": scores.get("price_score", 0),
                "服务评分": scores.get("service_score", 0),
            })

        blocks.append({
            "type": "table",
            "columns": [
                {"key": "排名", "title": "排名"},
                {"key": "供应商", "title": "供应商"},
                {"key": "综合评分", "title": "综合评分"},
                {"key": "质量评分", "title": "质量评分"},
                {"key": "交付评分", "title": "交付评分"},
                {"key": "价格评分", "title": "价格评分"},
                {"key": "服务评分", "title": "服务评分"},
            ],
            "rows": table_rows,
        })

    return {"_render": True, "blocks": blocks}


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


# ── 6. Comprehensive Diagnosis ─────────────────────────────────────────

def _render_comprehensive_diagnosis(db: Session) -> dict:
    """供应链综合诊断：健康评分雷达图 + 综合仪表盘 + 维度分析表格"""
    blocks = []

    # --- Dimension 1: Inventory health ---
    total_items = db.query(Inventory).filter(Inventory.quantity >= 0).count()
    out_of_stock_items = (
        db.query(Inventory)
        .join(Product, Inventory.product_id == Product.id)
        .filter(Inventory.quantity <= Product.min_stock, Inventory.quantity >= 0)
        .count()
    )
    if total_items > 0:
        stockout_rate = out_of_stock_items / total_items
        inventory_health = round(100 * (1 - stockout_rate), 1)
    else:
        inventory_health = 100.0

    # --- Dimension 2: Sales trend ---
    six_months_ago = date.today() - timedelta(days=180)
    date_fmt = func.date_format(SaleOrder.order_date, "%Y-%m")
    monthly_sales = (
        db.query(
            date_fmt.label("month"),
            func.sum(SaleOrderItem.total_price).label("amount"),
        )
        .join(SaleOrderItem, SaleOrderItem.order_id == SaleOrder.id)
        .filter(SaleOrder.order_date >= six_months_ago, SaleOrder.status != "cancelled")
        .group_by(date_fmt)
        .order_by(date_fmt)
        .all()
    )
    if len(monthly_sales) >= 2:
        amounts = [float(r.amount or 0) for r in monthly_sales]
        growth_rate = (amounts[-1] - amounts[-2]) / amounts[-2] if amounts[-2] > 0 else 0
        if growth_rate >= 0:
            sales_trend_score = min(50 + growth_rate * 500, 100)
        else:
            sales_trend_score = max(50 + growth_rate * 500, 0)
        sales_trend_score = round(sales_trend_score, 1)
    else:
        sales_trend_score = 50.0

    # --- Dimension 3: Supplier performance ---
    avg_supplier = (
        db.query(func.avg(SupplierEvaluation.total_score))
        .scalar()
    )
    supplier_score = round(float(avg_supplier or 0), 1)

    # --- Dimension 4: Stockout risk ---
    stockout_risk_score = round(100 - stockout_rate * 100, 1) if total_items > 0 else 100.0

    # --- Dimension 5: Turnover rate ---
    # Estimate from sales / inventory ratio over last 30 days
    thirty_days_ago = date.today() - timedelta(days=30)
    total_sales_30d = (
        db.query(func.sum(SaleOrderItem.total_price))
        .join(SaleOrder, SaleOrder.id == SaleOrderItem.order_id)
        .filter(SaleOrder.order_date >= thirty_days_ago, SaleOrder.status != "cancelled")
        .scalar()
    ) or 0
    total_inventory_value = (
        db.query(func.sum(Inventory.quantity * Product.unit_price))
        .join(Product, Inventory.product_id == Product.id)
        .filter(Inventory.quantity > 0)
        .scalar()
    ) or 0
    if total_inventory_value > 0:
        turnover_ratio = float(total_sales_30d) / float(total_inventory_value)
        # Normalize: ratio of 0.5-1.5 per month is healthy (score 70-90)
        turnover_score = min(max(50 + turnover_ratio * 40, 0), 100)
    else:
        turnover_score = 0.0
    turnover_score = round(turnover_score, 1)

    # --- Weighted overall score ---
    overall_score = round(
        inventory_health * 0.30
        + sales_trend_score * 0.25
        + supplier_score * 0.20
        + stockout_risk_score * 0.15
        + turnover_score * 0.10,
        1,
    )

    # --- Status and suggestions per dimension ---
    def _status_and_advice(score: float, dimension: str) -> tuple[str, str]:
        if score >= 80:
            return "良好", f"{dimension}状况良好，继续保持现有策略"
        elif score >= 60:
            return "一般", f"{dimension}有改善空间，建议关注异常指标"
        elif score >= 40:
            return "预警", f"{dimension}需要重点关注，建议及时调整策略"
        else:
            return "危险", f"{dimension}严重不足，需立即采取行动"

    inventory_status, inventory_advice = _status_and_advice(inventory_health, "库存")
    sales_status, sales_advice = _status_and_advice(sales_trend_score, "销售")
    supplier_status, supplier_advice = _status_and_advice(supplier_score, "供应商")
    stockout_status, stockout_advice = _status_and_advice(stockout_risk_score, "缺货风险")
    turnover_status, turnover_advice = _status_and_advice(turnover_score, "周转")

    # --- Block 1: Radar chart ---
    blocks.append({
        "type": "chart",
        "chartType": "radar",
        "data": {
            "title": {
                "text": "供应链健康评分雷达图",
                "left": "center",
                "textStyle": {"fontSize": 14, "fontWeight": "bold"},
            },
            "tooltip": {},
            "radar": {
                "indicator": [
                    {"name": "库存健康", "max": 100},
                    {"name": "销售趋势", "max": 100},
                    {"name": "供应商表现", "max": 100},
                    {"name": "缺货风险", "max": 100},
                    {"name": "周转率", "max": 100},
                ],
                "shape": "circle",
                "splitNumber": 5,
                "axisName": {"color": "#333", "fontSize": 12},
                "splitLine": {"lineStyle": {"color": ["#eee", "#ddd", "#ccc", "#bbb", "#aaa"]}},
                "splitArea": {"show": True, "areaStyle": {"color": ["rgba(84,112,198,0.05)", "rgba(84,112,198,0.1)"]}},
            },
            "series": [{
                "name": "健康评分",
                "type": "radar",
                "data": [{
                    "value": [inventory_health, sales_trend_score, supplier_score, stockout_risk_score, turnover_score],
                    "name": "当前评分",
                    "areaStyle": {"color": "rgba(84,112,198,0.2)"},
                    "lineStyle": {"color": "#5470c6", "width": 2},
                    "itemStyle": {"color": "#5470c6"},
                }],
            }],
        },
    })

    # --- Block 2: Gauge chart ---
    blocks.append({
        "type": "chart",
        "chartType": "gauge",
        "data": {
            "title": {
                "text": "综合健康评分",
                "left": "center",
                "top": "5%",
                "textStyle": {"fontSize": 14, "fontWeight": "bold"},
            },
            "series": [{
                "type": "gauge",
                "startAngle": 200,
                "endAngle": -20,
                "min": 0,
                "max": 100,
                "splitNumber": 10,
                "itemStyle": {"color": "#5470c6"},
                "progress": {"show": True, "width": 18},
                "pointer": {"show": True, "length": "60%", "width": 4},
                "axisLine": {"lineStyle": {"width": 18, "color": [[0.3, "#ee6666"], [0.7, "#fac858"], [1, "#91cc75"]]}},
                "axisTick": {"distance": -18, "length": 6, "lineStyle": {"color": "#fff", "width": 1}},
                "splitLine": {"distance": -18, "length": 18, "lineStyle": {"color": "#fff", "width": 2}},
                "axisLabel": {"distance": 25, "fontSize": 11, "color": "#999"},
                "detail": {
                    "valueAnimation": True,
                    "formatter": "{value}",
                    "fontSize": 28,
                    "fontWeight": "bold",
                    "color": "#333",
                    "offsetCenter": [0, "70%"],
                },
                "data": [{"value": overall_score, "name": "综合评分"}],
            }],
        },
    })

    # --- Block 3: Summary table ---
    table_rows = [
        {"维度": "库存健康", "评分": inventory_health, "状态": inventory_status, "建议": inventory_advice},
        {"维度": "销售趋势", "评分": sales_trend_score, "状态": sales_status, "建议": sales_advice},
        {"维度": "供应商表现", "评分": supplier_score, "状态": supplier_status, "建议": supplier_advice},
        {"维度": "缺货风险", "评分": stockout_risk_score, "状态": stockout_status, "建议": stockout_advice},
        {"维度": "周转率", "评分": turnover_score, "状态": turnover_status, "建议": turnover_advice},
    ]
    blocks.append({
        "type": "table",
        "columns": [
            {"key": "维度", "title": "维度"},
            {"key": "评分", "title": "评分"},
            {"key": "状态", "title": "状态"},
            {"key": "建议", "title": "建议"},
        ],
        "rows": table_rows,
    })

    return {"_render": True, "blocks": blocks}


# ── 7. Purchase Advice ──────────────────────────────────────────────────

def _render_purchase_advice(db: Session) -> dict:
    """采购建议：补货柱状图 + 推荐供应商表格 + 费用估算"""
    blocks = []

    # Reuse low-stock logic from _recommend_restock
    recommendations = _recommend_restock({}, db)
    recs = recommendations.get("recommendations", [])

    if not recs:
        blocks.append({
            "type": "table",
            "columns": [{"key": "msg", "title": "提示"}],
            "rows": [{"msg": "暂无需要补货的产品，库存充足"}],
        })
        return {"_render": True, "blocks": blocks}

    # For each item, find the best supplier using evaluation scores
    for rec in recs:
        product_id = rec.get("product_id")
        best_supplier_name = "-"
        if product_id:
            supplier_result = _recommend_supplier({"product_id": product_id}, db)
            suppliers_list = supplier_result.get("suppliers", [])
            if suppliers_list:
                # Sort by total_score descending, pick the best
                best = max(suppliers_list, key=lambda s: s.get("total_score", 0))
                best_supplier_name = best.get("supplier_name", "-")
        rec["推荐供应商"] = best_supplier_name
        # Estimate purchase amount: suggested_qty * product unit_price
        product = db.query(Product).filter(Product.id == product_id).first()
        unit_price = float(product.unit_price) if product and product.unit_price else 0
        estimated_amount = round(rec.get("suggested_qty", 0) * unit_price, 2)
        rec["预估金额"] = estimated_amount

    # --- Block 1: Bar chart (products x suggested qty, colored by urgency) ---
    urgency_colors = {"critical": "#ee6666", "high": "#fac858", "medium": "#5470c6"}
    bar_data = []
    for rec in recs:
        color = urgency_colors.get(rec.get("priority", "medium"), "#5470c6")
        bar_data.append({
            "value": rec.get("suggested_qty", 0),
            "itemStyle": {"color": color},
        })

    blocks.append({
        "type": "chart",
        "chartType": "bar",
        "data": {
            "title": {
                "text": "采购建议 — 建议补货量",
                "left": "center",
                "textStyle": {"fontSize": 14, "fontWeight": "bold"},
            },
            "tooltip": {"trigger": "axis"},
            "legend": {
                "data": ["紧急", "高优", "中等"],
                "bottom": 0,
                "selected": {"紧急": True, "高优": True, "中等": True},
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
                "data": [r.get("product_name", "") for r in recs],
                "axisLabel": {"rotate": 20, "fontSize": 11},
            },
            "yAxis": {"type": "value", "name": "建议采购量", "nameTextStyle": {"fontSize": 12}},
            "series": [{
                "name": "建议采购量",
                "type": "bar",
                "data": bar_data,
                "barMaxWidth": 30,
                "label": {"show": True, "position": "top", "fontSize": 10},
            }],
        },
    })

    # --- Block 2: Table ---
    table_rows = []
    total_estimated = 0.0
    critical_count = 0
    for rec in recs:
        estimated = rec.get("预估金额", 0)
        total_estimated += estimated
        if rec.get("priority") == "critical":
            critical_count += 1
        urgency_label = {"critical": "紧急", "high": "高优", "medium": "中等"}.get(rec.get("priority", ""), "中等")
        table_rows.append({
            "产品": rec.get("product_name", ""),
            "当前库存": rec.get("current_qty", 0),
            "安全库存": rec.get("min_stock", 0),
            "建议采购量": rec.get("suggested_qty", 0),
            "紧迫度": urgency_label,
            "推荐供应商": rec.get("推荐供应商", "-"),
            "预估金额": f"¥{estimated:,.2f}",
        })

    blocks.append({
        "type": "table",
        "columns": [
            {"key": "产品", "title": "产品"},
            {"key": "当前库存", "title": "当前库存"},
            {"key": "安全库存", "title": "安全库存"},
            {"key": "建议采购量", "title": "建议采购量"},
            {"key": "紧迫度", "title": "紧迫度"},
            {"key": "推荐供应商", "title": "推荐供应商"},
            {"key": "预估金额", "title": "预估金额"},
        ],
        "rows": table_rows,
    })

    # --- Block 3: Summary ---
    blocks.append({
        "type": "table",
        "columns": [{"key": "指标", "title": "指标"}, {"key": "值", "title": "值"}],
        "rows": [
            {"指标": "需补货产品数", "值": f"{len(recs)} 项"},
            {"指标": "紧急项数", "值": f"{critical_count} 项"},
            {"指标": "预估总金额", "值": f"¥{total_estimated:,.2f}"},
        ],
    })

    return {"_render": True, "blocks": blocks}
