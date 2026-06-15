"""AI 工具集 — 注册表架构 (ToolMeta + REGISTRY + condense + build_blocks + nl_template)

所有 23 个工具通过 _register() 注册到 REGISTRY 字典，
execute_tool() 通过 O(1) 查找分发，不再线性扫描 8 个 executor。

兼容层：
- ALL_TOOLS: 与原格式完全一致的 OpenAI function calling 列表
- execute_tool(name, args, db): 返回格式不变
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Any

# ── Handler imports (private functions from each module) ────────────────
from app.tools.inventory_tools import (
    _query_inventory,
    _analyze_stock_risk,
)
from app.tools.sales_tools import (
    _query_sales_history,
    _forecast_sales,
)
from app.tools.supplier_tools import (
    _query_suppliers,
    _rank_suppliers,
)
from app.tools.product_tools import execute as _product_exec
from app.tools.action_tools import (
    _create_purchase_order,
    _create_stock_transfer,
)
from app.tools.chart_tools import (
    _render_inventory_heatmap,
    _render_sales_trend,
    _render_supplier_ranking,
    _recommend_restock,
    _recommend_supplier,
    _render_comprehensive_diagnosis,
    _render_purchase_advice,
    _audit_purchase_plan,
    _render_safety_stock_table,
    _render_transfer_advice_table,
)
from app.tools.calculation_tools import execute as _calc_exec
from app.tools.weather_tools import execute as _weather_exec_raw

# weather_tools.execute 签名是 (name, args, db)，需要适配 (args, db)
def _weather_exec(args: dict, db) -> dict | None:
    return _weather_exec_raw("query_weather", args, db)

# ── Service imports (for calculation tool wrappers) ─────────────────────
from app.services.calculation_service import (
    calc_reorder_point as _svc_calc_rop,
    calc_inventory_kpi as _svc_calc_kpi,
)
from app.services.supplier_scoring import (
    calc_supplier_score as _svc_calc_supplier_score,
)


# ═══════════════════════════════════════════════════════════════════════
# 1. ToolMeta dataclass
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class ToolMeta:
    """工具元数据注册项"""
    name: str
    category: str                          # query | render | action | calc | recommend
    description: str
    parameters: dict                       # JSON Schema (OpenAI function calling format)
    handler: Callable                      # (args: dict, db: Session) -> dict
    condense: Callable | None = None       # (result: dict) -> dict  — 提取关键指标
    build_blocks: Callable | None = None   # (result: dict) -> list[dict]  — 构建渲染块
    nl_template: Callable | None = None    # (result: dict) -> str  — 规则驱动分析模板
    requires_confirm: bool = False         # 是否需要用户确认
    tool_chain: list[str] = field(default_factory=list)  # 推荐的前置工具链


# ═══════════════════════════════════════════════════════════════════════
# 2. REGISTRY + _register
# ═══════════════════════════════════════════════════════════════════════

REGISTRY: dict[str, ToolMeta] = {}


def _register(meta: ToolMeta) -> None:
    """注册工具到 REGISTRY，重复 name 会覆盖"""
    REGISTRY[meta.name] = meta


# ── Helper: wrap (db)-only chart handlers to (args, db) signature ──────
def _db_only(fn: Callable) -> Callable:
    """将 (db) 签名包装为 (args, db) 签名"""
    return lambda args, db, _fn=fn: _fn(db)


# ── Helper: product query handler (inline logic in execute()) ──────────
def _query_products_handler(args: dict, db) -> dict:
    """产品查询 — 原逻辑内联在 product_tools.execute() 中"""
    from app.models.product import Product

    q = db.query(Product)
    if args.get("product_id"):
        q = q.filter(Product.id == args["product_id"])
    if args.get("category_id"):
        q = q.filter(Product.category_id == args["category_id"])
    if args.get("keyword"):
        kw = f"%{args['keyword']}%"
        q = q.filter((Product.name.like(kw)) | (Product.code.like(kw)))
    if args.get("is_active") is not None:
        q = q.filter(Product.is_active == args["is_active"])

    products = q.limit(args.get("limit", 50)).all()
    return {
        "products": [
            {
                "id": p.id, "code": p.code, "name": p.name,
                "category_id": p.category_id, "unit": p.unit,
                "purchase_price": p.purchase_price, "sale_price": p.sale_price,
                "min_stock": p.min_stock, "max_stock": p.max_stock,
                "is_active": p.is_active,
            }
            for p in products
        ],
        "total": len(products),
    }


# ── Helper: calculation tool wrappers ──────────────────────────────────
def _calc_rop_handler(args: dict, db) -> dict:
    """ROP 计算 — 包装 calculation_service.calc_reorder_point"""
    product_id = args.get("product_id")
    supplier_id = args.get("supplier_id")
    if product_id:
        return _svc_calc_rop(product_id, db, supplier_id)
    from app.models.product import Product
    products = db.query(Product).filter(Product.is_active == True).all()
    results = []
    for p in products:
        try:
            r = _svc_calc_rop(p.id, db, supplier_id)
            results.append(r)
        except Exception:
            pass
    return {"total": len(results), "products": results}


def _calc_supplier_score_handler(args: dict, db) -> dict:
    """供应商评分 — 包装 supplier_scoring.calc_supplier_score"""
    supplier_id = args.get("supplier_id")
    return _svc_calc_supplier_score(supplier_id, db)


def _calc_kpi_handler(args: dict, db) -> dict:
    """库存 KPI — 包装 calculation_service.calc_inventory_kpi"""
    return _svc_calc_kpi(db)


# ═══════════════════════════════════════════════════════════════════════
# 3. Condense functions — 提取关键指标，减少 LLM 上下文消耗
# ═══════════════════════════════════════════════════════════════════════

def _condense_inventory(result: dict) -> dict:
    """库存查询结果精简：只保留低库存/异常项"""
    items = result.get("items", [])
    abnormal = [it for it in items if it.get("status") != "正常"]
    return {
        "total": result.get("total", 0),
        "abnormal_count": len(abnormal),
        "abnormal_items": abnormal[:10],
    }


def _condense_sales(result: dict) -> dict:
    """销售历史/预测结果精简"""
    items = result.get("items", [])
    # 只保留最近 7 天 + 汇总
    recent = items[-7:] if len(items) > 7 else items
    return {
        "total_quantity": result.get("total_quantity", 0),
        "total_amount": result.get("total_amount", 0),
        "days": result.get("days", 0),
        "recent_items": recent,
    }


def _condense_suppliers(result: dict) -> dict:
    """供应商查询结果精简"""
    suppliers = result.get("suppliers", [])
    return {
        "total": result.get("total", 0),
        "suppliers": [
            {
                "id": s.get("id"), "name": s.get("name"),
                "status": s.get("status"), "rating": s.get("rating"),
                "avg_total_score": s.get("avg_total_score"),
                "completion_rate": s.get("completion_rate"),
            }
            for s in suppliers[:10]
        ],
    }


def _condense_products(result: dict) -> dict:
    """产品查询结果精简"""
    products = result.get("products", [])
    return {
        "total": result.get("total", 0),
        "products": [
            {
                "id": p.get("id"), "code": p.get("code"), "name": p.get("name"),
                "min_stock": p.get("min_stock"), "max_stock": p.get("max_stock"),
                "is_active": p.get("is_active"),
            }
            for p in products[:10]
        ],
    }


def _condense_rop(result: dict) -> dict:
    """ROP 计算结果精简"""
    if "products" in result:
        # 批量模式
        prods = result.get("products", [])
        return {
            "total": result.get("total", 0),
            "products": [
                {
                    "product_name": p.get("product_name"),
                    "rop": p.get("rop"),
                    "safety_stock": p.get("safety_stock"),
                    "current_qty": p.get("current_qty"),
                    "status": p.get("status"),
                }
                for p in prods[:10]
            ],
        }
    # 单产品模式
    return {
        "product_name": result.get("product_name"),
        "rop": result.get("rop"),
        "safety_stock": result.get("safety_stock"),
        "current_qty": result.get("current_qty"),
        "status": result.get("status"),
    }


def _condense_supplier_score(result: dict) -> dict:
    """供应商评分结果精简"""
    if "suppliers" in result:
        # 批量模式
        return {
            "total": result.get("total", 0),
            "suppliers": [
                {
                    "supplier_name": s.get("supplier_name"),
                    "total_score": s.get("total_score"),
                    "risk_penalty": s.get("risk_penalty"),
                    "is_single_source": s.get("is_single_source"),
                }
                for s in result.get("suppliers", [])[:10]
            ],
        }
    # 单供应商模式
    return {
        "supplier_name": result.get("supplier_name"),
        "total_score": result.get("total_score"),
        "risk_penalty": result.get("risk_penalty"),
        "is_single_source": result.get("is_single_source"),
    }


def _condense_kpi(result: dict) -> dict:
    """库存 KPI 结果精简"""
    return {
        "turnover_days": result.get("turnover_days"),
        "dead_sku_count": result.get("dead_sku_count"),
        "dead_sku_ratio": result.get("dead_sku_ratio"),
        "total_inventory_value": result.get("total_inventory_value"),
    }


def _condense_weather(result: dict) -> dict:
    """天气查询结果精简"""
    return {
        "city": result.get("city"),
        "summary": result.get("summary"),
        "affected_products": result.get("affected_products", [])[:5],
    }


def _condense_render(result: dict) -> dict:
    """渲染工具结果精简：提取 blocks 摘要"""
    blocks = _extract_blocks(result)
    summary_parts = []
    for b in blocks:
        btype = b.get("type", "unknown")
        if btype == "chart":
            chart_type = b.get("chartType", "unknown")
            title = ""
            data = b.get("data", {})
            if isinstance(data, dict):
                title_obj = data.get("title", {})
                if isinstance(title_obj, dict):
                    title = title_obj.get("text", "")
                elif isinstance(title_obj, str):
                    title = title_obj
            summary_parts.append(f"[chart:{chart_type}] {title}")
        elif btype == "table":
            cols = [c.get("title", c.get("key", "")) for c in b.get("columns", [])]
            row_count = len(b.get("rows", []))
            summary_parts.append(f"[table:{row_count}rows] {', '.join(cols[:5])}")
    return {
        "_render": True,
        "block_count": len(blocks),
        "block_summary": summary_parts,
    }


# ═══════════════════════════════════════════════════════════════════════
# 4. build_blocks functions — 构建前端渲染块
# ═══════════════════════════════════════════════════════════════════════

_FIELD_LABELS: dict[str, str] = {
    # 通用
    "id": "ID", "code": "编码", "name": "名称", "status": "状态",
    "unit": "单位", "category": "分类", "item": "项目", "date": "日期",
    "quantity": "数量", "amount": "金额", "total": "合计",
    "suggestion": "建议", "confidence": "置信度", "reason": "原因",
    "warning": "警告", "score": "评分", "summary": "摘要",
    "action": "操作", "city": "城市",
    # 产品
    "product_id": "产品ID", "product_name": "产品", "product_code": "产品编码",
    "category_id": "分类ID", "purchase_price": "采购价", "sale_price": "销售价",
    "is_active": "启用",
    # 仓库/库存
    "warehouse_id": "仓库ID", "warehouse_name": "仓库", "warehouse": "仓库",
    "current_qty": "当前库存", "min_stock": "安全库存", "max_stock": "最大库存",
    "daily_sales": "日均销量", "days_support": "可支撑天数",
    "alert_level": "预警等级", "suggested_action": "建议操作",
    "suggested_order_qty": "建议补货量", "suggested_qty": "建议补货量",
    "daily_sales_avg": "日均销量", "priority": "优先级",
    "rop": "再订货点(ROP)", "safety_stock": "安全库存",
    "avg_daily_sales": "日均销量", "lead_time": "交货期(天)",
    "service_level": "服务水平", "abc_class": "ABC分类",
    "turnover_days": "周转天数", "dead_stock_count": "呆滞SKU数",
    "dead_stock_pct": "呆滞占比", "capital_occupied": "占用资金",
    # 供应商
    "supplier_id": "供应商ID", "supplier_name": "供应商",
    "contact_person": "联系人", "phone": "电话", "rating": "评分",
    "delivery_lead_time": "交货期(天)", "lead_time_days": "交货期(天)",
    "avg_quality_score": "质量评分", "avg_delivery_score": "交付评分",
    "avg_price_score": "价格评分", "avg_service_score": "服务评分",
    "avg_total_score": "综合评分", "total_orders": "总订单数",
    "completed_orders": "已完成订单", "completion_rate": "完成率",
    "ai_score": "AI评分", "total_score": "综合评分",
    "strengths": "优势", "weaknesses": "劣势",
    "quality_score": "质量评分", "delivery_score": "交付评分",
    "price_score": "价格评分", "service_score": "服务评分",
    "past_orders": "历史订单数", "is_single_source": "单一来源",
    "stock_risk": "库存风险", "supplier_risk": "供应商风险",
    "quality": "质量", "delivery": "交付", "price": "价格", "service": "服务",
    "base_score": "基础分", "risk_penalty": "风险扣分",
    "single_source_penalty": "单一来源扣分", "delay_std_penalty": "交期波动扣分",
    "suggested_share": "建议份额",
    # 销售
    "total_quantity": "总数量", "total_amount": "总金额", "days": "天数",
    "forecast_next_30d": "30天预测", "predictions": "预测值",
    "prediction_dates": "预测日期", "trend": "趋势",
    "seasonal_factor": "季节因子",
    # 风险/天气
    "probability": "概率", "impact": "影响", "mitigability": "可缓解度",
    "weather_summary": "天气摘要", "kpi": "KPI", "overall_risk": "整体风险",
    "temp_high": "最高温", "temp_low": "最低温", "weather": "天气",
    "weather_code": "天气代码", "precip_prob": "降水概率",
    "matched_weather_types": "匹配天气类型",
}


def _query_result_to_table(result: dict) -> list[dict]:
    """通用查询结果 → table block

    支持 items / suppliers / products / recommendations / risk_items / rankings / risk_matrix / forecast 等列表键
    """
    # 尝试识别列表键（按优先级）
    list_data = None
    for key in ("items", "suppliers", "products", "recommendations", "risk_items",
                "rankings", "risk_matrix", "forecast", "history", "supplier_data",
                "product_risks", "affected_products"):
        if key in result and isinstance(result[key], list) and result[key]:
            list_data = result[key]
            break

    # 兜底：遍历所有值找第一个非空列表
    if not list_data:
        for v in result.values():
            if isinstance(v, list) and v and isinstance(v[0], dict):
                list_data = v
                break

    if not list_data:
        return [{"type": "table", "columns": [{"key": "msg", "title": "提示"}], "rows": [{"msg": "暂无数据"}]}]

    first = list_data[0]
    columns = [{"key": k, "title": _FIELD_LABELS.get(k, k)} for k in first.keys()]
    rows = list_data[:50]

    return [{"type": "table", "columns": columns, "rows": rows}]


def _render_passthrough(result: dict) -> list[dict]:
    """渲染工具直通：工具已返回 {"_render": True, "blocks": [...]}"""
    return _extract_blocks(result)


# ═══════════════════════════════════════════════════════════════════════
# 5. nl_template functions — 规则驱动分析模板（快捷操作用）
# ═══════════════════════════════════════════════════════════════════════

def _stock_alert_template(result: dict) -> str:
    """库存预警分析模板"""
    items = result.get("items", [])
    if not items:
        return "当前库存状态良好，所有产品库存均在安全范围内。"

    abnormal = [it for it in items if it.get("status") != "正常"]
    if not abnormal:
        return f"已检查 {len(items)} 项库存，全部处于正常水平。"

    critical = [it for it in abnormal if it.get("status") in ("缺货", "严重不足")]
    low = [it for it in abnormal if it.get("status") == "偏低"]

    parts = [f"发现 {len(abnormal)} 项库存异常（共 {len(items)} 项）："]
    if critical:
        names = ", ".join(it.get("product_name", "?") for it in critical[:5])
        parts.append(f"- 缺货/严重不足 {len(critical)} 项：{names}")
    if low:
        names = ", ".join(it.get("product_name", "?") for it in low[:5])
        parts.append(f"- 偏低 {len(low)} 项：{names}")
    parts.append("建议优先处理缺货产品，可调用 recommend_restock 获取补货建议。")
    return "\n".join(parts)


def _sales_trend_template(result: dict) -> str:
    """销售趋势分析模板"""
    items = result.get("items", [])
    total_qty = result.get("total_quantity", 0)
    total_amount = result.get("total_amount", 0)
    days = result.get("days", 0)

    if not items:
        return f"近 {days} 天无销售数据。"

    # 计算趋势
    if len(items) >= 2:
        recent_qty = sum(it.get("quantity", 0) for it in items[-7:])
        earlier_qty = sum(it.get("quantity", 0) for it in items[:7])
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

    return (
        f"近 {days} 天销售汇总：\n"
        f"- 总销量：{total_qty:,.0f}\n"
        f"- 总金额：¥{total_amount:,.2f}\n"
        f"- 趋势：{trend}\n"
        f"如需详细预测，可调用 forecast_sales。"
    )


def _supplier_ranking_template(result: dict) -> str:
    """供应商排名分析模板"""
    rankings = result.get("rankings", [])
    summary = result.get("summary", "")
    supplier_data = result.get("supplier_data", [])

    if not rankings and not supplier_data:
        return "暂无供应商评估数据。"

    parts = []
    if summary:
        parts.append(summary)

    if rankings:
        top3 = rankings[:3]
        for i, r in enumerate(top3):
            parts.append(f"第{i+1}名：{r.get('supplier_name', '?')}（综合评分 {r.get('total_score', 'N/A')}）")

    if not parts and supplier_data:
        sorted_data = sorted(supplier_data, key=lambda s: s.get("total_score", 0), reverse=True)
        for i, s in enumerate(sorted_data[:3]):
            parts.append(f"第{i+1}名：{s.get('supplier_name', '?')}（综合评分 {s.get('total_score', 0)}）")

    return "\n".join(parts) if parts else "供应商评估完成，详见数据。"


def _dashboard_template(result: dict) -> str:
    """综合诊断模板"""
    blocks = _extract_blocks(result)
    # 尝试从表格块提取评分
    for b in blocks:
        if b.get("type") == "table":
            rows = b.get("rows", [])
            if rows and "评分" in rows[0]:
                parts = ["供应链综合诊断："]
                for r in rows[:5]:
                    parts.append(f"- {r.get('维度', '?')}：{r.get('评分', 'N/A')}（{r.get('状态', '?')}）")
                return "\n".join(parts)
    return "供应链综合诊断已完成，请查看图表。"


def _purchase_advice_template(result: dict) -> str:
    """采购建议模板"""
    blocks = _extract_blocks(result)
    # 从汇总表格提取
    for b in blocks:
        if b.get("type") == "table":
            rows = b.get("rows", [])
            for r in rows:
                if "需补货产品数" in str(r.get("指标", "")):
                    return (
                        f"采购建议：需补货 {r.get('值', '?')}，"
                        f"紧急项 {rows[-1].get('值', '?') if len(rows) > 1 else '?'}，"
                        f"预估总金额 {rows[-1].get('值', '?') if len(rows) > 2 else '?'}。"
                    )
    return "采购建议已生成，请查看图表和表格。"


def _safety_stock_template(result: dict) -> str:
    """安全库存模板"""
    blocks = _extract_blocks(result)
    for b in blocks:
        if b.get("type") == "table":
            rows = b.get("rows", [])
            urgent = [r for r in rows if r.get("status") == "紧急补货"]
            suggest = [r for r in rows if r.get("status") == "建议补货"]
            parts = [f"安全库存分析（共 {len(rows)} 项）："]
            if urgent:
                names = ", ".join(r.get("product_name", "?") for r in urgent[:5])
                parts.append(f"- 紧急补货 {len(urgent)} 项：{names}")
            if suggest:
                names = ", ".join(r.get("product_name", "?") for r in suggest[:5])
                parts.append(f"- 建议补货 {len(suggest)} 项：{names}")
            safe_count = len(rows) - len(urgent) - len(suggest)
            if safe_count > 0:
                parts.append(f"- 安全 {safe_count} 项")
            return "\n".join(parts)
    return "安全库存分析已完成。"


def _transfer_advice_template(result: dict) -> str:
    """调拨建议模板"""
    blocks = _extract_blocks(result)
    for b in blocks:
        if b.get("type") == "table":
            rows = b.get("rows", [])
            if not rows:
                return "各仓库库存分布均衡，暂无调拨需求。"
            parts = [f"发现 {len(rows)} 项调拨建议："]
            for r in rows[:5]:
                parts.append(
                    f"- {r.get('product_name', '?')}：{r.get('from_warehouse', '?')} → "
                    f"{r.get('to_warehouse', '?')}，建议调拨 {r.get('transfer_qty', '?')} 件"
                )
            return "\n".join(parts)
    return "调拨建议分析已完成。"


# ═══════════════════════════════════════════════════════════════════════
# 6. Helper functions
# ═══════════════════════════════════════════════════════════════════════

def _extract_blocks(result: dict) -> list[dict]:
    """从工具结果中提取 blocks 列表

    支持两种格式：
    1. {"_render": True, "blocks": [...]}
    2. {"type": "chart"/"table", ...}  (单块格式)
    """
    if "blocks" in result and isinstance(result["blocks"], list):
        return result["blocks"]
    # 单块格式（如 render_sales_trend 返回的顶层 type/data）
    if "type" in result and result["type"] in ("chart", "table"):
        return [result]
    return []


def _parse_blocks(result: dict) -> list[dict]:
    """解析并规范化 blocks（确保每个 block 有 type 字段）"""
    blocks = _extract_blocks(result)
    normalized = []
    for b in blocks:
        if not isinstance(b, dict):
            continue
        if "type" not in b:
            continue
        normalized.append(b)
    return normalized


# ═══════════════════════════════════════════════════════════════════════
# 7. Register ALL 23 tools
# ═══════════════════════════════════════════════════════════════════════

# ── Inventory (query) ──────────────────────────────────────────────────
_register(ToolMeta(
    name="query_inventory",
    category="query",
    description="查询当前库存状态，可按产品ID、仓库ID筛选，支持仅查低库存产品。返回产品名、仓库名、库存量、最低/最高库存警戒线",
    parameters={
        "type": "object",
        "properties": {
            "product_id": {"type": "integer", "description": "产品ID，可选"},
            "warehouse_id": {"type": "integer", "description": "仓库ID，可选"},
            "low_stock_only": {"type": "boolean", "description": "仅返回库存≤最低库存线的产品"},
            "limit": {"type": "integer", "description": "返回条数上限，默认100"},
        },
        "required": [],
    },
    handler=_query_inventory,
    condense=_condense_inventory,
    build_blocks=_query_result_to_table,
    nl_template=_stock_alert_template,
))

_register(ToolMeta(
    name="analyze_stock_risk",
    category="query",
    description="AI库存风险分析。识别缺货/低库存/积压产品，按风险等级排序并给出补货建议",
    parameters={
        "type": "object",
        "properties": {
            "product_ids": {
                "type": "array", "items": {"type": "integer"},
                "description": "要分析的产品ID列表，为空则分析全部低库存产品",
            },
        },
        "required": [],
    },
    handler=_analyze_stock_risk,
    condense=_condense_inventory,
    build_blocks=_query_result_to_table,
    nl_template=_stock_alert_template,
))

# ── Sales (query) ──────────────────────────────────────────────────────
_register(ToolMeta(
    name="query_sales_history",
    category="query",
    description="查询销售数据，包括销量、销售金额、卖了多少、什么卖得好等。返回按日期聚合的销量和金额，可按产品筛选、设定回溯天数。用户问销量相关数值问题时优先使用此工具，不要用 render_sales_trend",
    parameters={
        "type": "object",
        "properties": {
            "product_id": {"type": "integer", "description": "产品ID，可选"},
            "days": {"type": "integer", "description": "回溯天数，默认90"},
            "group_by": {"type": "string", "enum": ["day", "week", "month"], "description": "聚合粒度，默认day"},
        },
        "required": [],
    },
    handler=_query_sales_history,
    condense=_condense_sales,
    build_blocks=_query_result_to_table,
    nl_template=_sales_trend_template,
))

_register(ToolMeta(
    name="forecast_sales",
    category="query",
    description="基于历史销售数据进行AI销售预测，返回30天预测数量、趋势判断和采购建议",
    parameters={
        "type": "object",
        "properties": {
            "product_id": {"type": "integer", "description": "产品ID"},
        },
        "required": ["product_id"],
    },
    handler=_forecast_sales,
    condense=_condense_sales,
    build_blocks=_query_result_to_table,
    nl_template=_sales_trend_template,
))

# ── Supplier (query) ───────────────────────────────────────────────────
_register(ToolMeta(
    name="query_suppliers",
    category="query",
    description="查询供应商信息，包括评分、交期、交易统计等",
    parameters={
        "type": "object",
        "properties": {
            "supplier_id": {"type": "integer", "description": "供应商ID，可选"},
            "status": {"type": "string", "description": "状态筛选：active/inactive/blacklisted"},
            "limit": {"type": "integer", "description": "返回条数上限，默认50"},
        },
        "required": [],
    },
    handler=_query_suppliers,
    condense=_condense_suppliers,
    build_blocks=_query_result_to_table,
    nl_template=_supplier_ranking_template,
))

_register(ToolMeta(
    name="rank_suppliers",
    category="query",
    description="AI供应商综合排名。从质量、交付、价格、服务四个维度综合评估所有活跃供应商",
    parameters={
        "type": "object",
        "properties": {
            "product_id": {"type": "integer", "description": "按产品需求评估供应商适配度，可选"},
        },
        "required": [],
    },
    handler=_rank_suppliers,
    condense=_condense_suppliers,
    build_blocks=_query_result_to_table,
    nl_template=_supplier_ranking_template,
))

# ── Product (query) ────────────────────────────────────────────────────
_register(ToolMeta(
    name="query_products",
    category="query",
    description="查询产品信息，包括价格、库存警戒线等。可按ID精确定位、按分类筛选或关键字搜索",
    parameters={
        "type": "object",
        "properties": {
            "product_id": {"type": "integer", "description": "产品ID，可选"},
            "category_id": {"type": "integer", "description": "分类ID，可选"},
            "keyword": {"type": "string", "description": "名称/编码关键词搜索"},
            "is_active": {"type": "boolean", "description": "仅活跃产品"},
            "limit": {"type": "integer", "description": "返回条数上限，默认50"},
        },
        "required": [],
    },
    handler=_query_products_handler,
    condense=_condense_products,
    build_blocks=_query_result_to_table,
))

# ── Action tools ───────────────────────────────────────────────────────
_register(ToolMeta(
    name="create_purchase_order",
    category="action",
    description="创建采购订单。仅在用户明确确认后由 /api/ai/execute 端点调用",
    parameters={
        "type": "object",
        "properties": {
            "supplier_id": {"type": "integer", "description": "供应商ID"},
            "items": {
                "type": "array", "items": {
                    "type": "object",
                    "properties": {
                        "product_id": {"type": "integer"},
                        "quantity": {"type": "number"},
                        "unit_price": {"type": "number"},
                    },
                    "required": ["product_id", "quantity", "unit_price"],
                },
            },
            "expected_delivery_date": {"type": "string", "description": "期望交期 YYYY-MM-DD"},
            "remark": {"type": "string", "description": "备注"},
        },
        "required": ["supplier_id", "items"],
    },
    handler=_create_purchase_order,
    requires_confirm=True,
    tool_chain=["recommend_restock", "recommend_supplier"],
))

_register(ToolMeta(
    name="create_stock_transfer",
    category="action",
    description="创建库存调拨单。仅在用户明确确认后调用",
    parameters={
        "type": "object",
        "properties": {
            "product_id": {"type": "integer", "description": "产品ID"},
            "from_warehouse_id": {"type": "integer", "description": "调出仓库ID"},
            "to_warehouse_id": {"type": "integer", "description": "调入仓库ID"},
            "quantity": {"type": "number", "description": "调拨数量"},
            "remark": {"type": "string", "description": "备注"},
        },
        "required": ["product_id", "from_warehouse_id", "to_warehouse_id", "quantity"],
    },
    handler=_create_stock_transfer,
    requires_confirm=True,
    tool_chain=["render_transfer_advice_table"],
))

# ── Chart / Render tools ───────────────────────────────────────────────
_register(ToolMeta(
    name="render_inventory_heatmap",
    category="render",
    description="生成库存热力图(ECharts)，颜色深浅表示缺货严重程度。适用：用户说'看库存图''库存热力图'。不适用：只问库存数量→query_inventory；问补货时机→calc_reorder_point",
    parameters={"type": "object", "properties": {}, "required": []},
    handler=_db_only(_render_inventory_heatmap),
    condense=_condense_render,
    build_blocks=_render_passthrough,
    nl_template=_stock_alert_template,
))

_register(ToolMeta(
    name="render_sales_trend",
    category="render",
    description="生成销售趋势折线图(ECharts)。适用：用户说'看趋势图''销量走势图''销售折线图'。支持按产品筛选：直接传 product_name（如'塑料粒子'），不需要先查ID。不适用：只问销量多少→query_sales_history",
    parameters={
        "type": "object",
        "properties": {
            "product_id": {"type": "integer", "description": "产品ID，可选，不传则展示全部产品汇总"},
            "product_name": {"type": "string", "description": "产品名称，可选，传入后自动匹配产品ID生成图表"},
        },
        "required": [],
    },
    handler=_render_sales_trend,
    condense=_condense_render,
    build_blocks=_render_passthrough,
    nl_template=_sales_trend_template,
))

_register(ToolMeta(
    name="render_supplier_ranking",
    category="render",
    description="生成供应商评分对比柱状图(ECharts)，支持多维度切换(质量/交付/价格/服务/综合/交付率/收货率)。适用：用户说'看供应商排名图''供应商对比图'。不适用：只问供应商信息→query_suppliers；问供应商风险→calc_supplier_score",
    parameters={"type": "object", "properties": {}, "required": []},
    handler=_db_only(_render_supplier_ranking),
    condense=_condense_render,
    build_blocks=_render_passthrough,
    nl_template=_supplier_ranking_template,
))

_register(ToolMeta(
    name="render_comprehensive_diagnosis",
    category="render",
    description="生成供应链综合诊断图表，包含健康评分雷达图、综合仪表盘和各维度分析表格。适用：用户说'看诊断图''供应链仪表盘'",
    parameters={"type": "object", "properties": {}, "required": []},
    handler=_db_only(_render_comprehensive_diagnosis),
    condense=_condense_render,
    build_blocks=_render_passthrough,
    nl_template=_dashboard_template,
))

_register(ToolMeta(
    name="render_purchase_advice",
    category="render",
    description="生成采购建议图表，包含补货清单柱状图、推荐供应商表格和费用估算。适用：用户说'看采购建议图'。不适用：只问需要采购什么→recommend_restock",
    parameters={"type": "object", "properties": {}, "required": []},
    handler=_db_only(_render_purchase_advice),
    condense=_condense_render,
    build_blocks=_render_passthrough,
    nl_template=_purchase_advice_template,
))

_register(ToolMeta(
    name="render_safety_stock_table",
    category="render",
    description="生成安全库存分析表格，批量计算所有产品的再订货点(ROP)和安全库存，标注补货状态。适用：用户说'看安全库存''ROP分析''补货时机'",
    parameters={"type": "object", "properties": {}, "required": []},
    handler=_db_only(_render_safety_stock_table),
    condense=_condense_render,
    build_blocks=_render_passthrough,
    nl_template=_safety_stock_template,
))

_register(ToolMeta(
    name="render_transfer_advice_table",
    category="render",
    description="生成仓库间调拨建议表格，分析各仓库库存不平衡情况，推荐从富余仓库向短缺仓库调拨。适用：用户说'看调拨建议''仓库调拨'",
    parameters={"type": "object", "properties": {}, "required": []},
    handler=_db_only(_render_transfer_advice_table),
    condense=_condense_render,
    build_blocks=_render_passthrough,
    nl_template=_transfer_advice_template,
))

# ── Recommend tools ────────────────────────────────────────────────────
_register(ToolMeta(
    name="recommend_restock",
    category="recommend",
    description="综合库存水位、近30天销量、供应商交期等多维度数据，智能推荐补货清单和补货量。适用：用户问'该补什么货''需要采购什么'",
    parameters={
        "type": "object",
        "properties": {
            "product_ids": {
                "type": "array", "items": {"type": "integer"},
                "description": "要分析的产品ID列表，为空则分析全部低库存产品",
            },
        },
        "required": [],
    },
    handler=_recommend_restock,
    condense=_condense_inventory,
    build_blocks=_query_result_to_table,
    nl_template=_stock_alert_template,
    tool_chain=["query_inventory", "query_sales_history"],
))

_register(ToolMeta(
    name="recommend_supplier",
    category="recommend",
    description="为指定产品智能推荐最佳供应商，综合质量评分、交付评分、价格评分、服务评分、历史合作次数、交付率和交期天数等多因素。适用：用户问'哪个供应商好''推荐供应商'",
    parameters={
        "type": "object",
        "properties": {
            "product_id": {"type": "integer", "description": "产品ID，必需"},
        },
        "required": ["product_id"],
    },
    handler=_recommend_supplier,
    condense=_condense_suppliers,
    build_blocks=_query_result_to_table,
    nl_template=_supplier_ranking_template,
    tool_chain=["query_products", "query_suppliers"],
))

# ── Audit (recommend) ─────────────────────────────────────────────────
_register(ToolMeta(
    name="audit_purchase_plan",
    category="recommend",
    description="审核采购计划风险：并行调用库存KPI、供应商评分、天气数据、销量预测，由LLM串联输出风险矩阵。当用户要求审核采购方案、评估采购风险时调用",
    parameters={
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "product_id": {"type": "integer", "description": "产品ID"},
                        "product_name": {"type": "string", "description": "产品名称"},
                        "quantity": {"type": "integer", "description": "采购数量"},
                        "supplier_id": {"type": "integer", "description": "供应商ID"},
                        "supplier_name": {"type": "string", "description": "供应商名称"},
                    },
                    "required": ["product_id", "product_name", "quantity", "supplier_id", "supplier_name"],
                },
                "description": "采购计划明细列表",
            },
        },
        "required": ["items"],
    },
    handler=_audit_purchase_plan,
    condense=_condense_render,
    build_blocks=_query_result_to_table,
    tool_chain=["calc_inventory_kpi", "calc_supplier_score", "query_weather", "forecast_sales"],
))

# ── Calculation tools ──────────────────────────────────────────────────
_register(ToolMeta(
    name="calc_reorder_point",
    category="calc",
    description="计算产品的再订货点(ROP)，包含安全库存、日均销量、交期天数。基于近60天销量数据和供应商交期，按ABC分类确定服务水平。当用户询问补货时机、再订货点、安全库存时应首先调用此工具。不指定product_id时计算所有产品的ROP",
    parameters={
        "type": "object",
        "properties": {
            "product_id": {
                "type": "integer",
                "description": "产品ID（可选，不指定则计算所有产品）",
            },
            "supplier_id": {
                "type": "integer",
                "description": "供应商ID（可选，默认取最近采购的供应商）",
            },
        },
        "required": [],
    },
    handler=_calc_rop_handler,
    condense=_condense_rop,
    build_blocks=_query_result_to_table,
    nl_template=_safety_stock_template,
))

_register(ToolMeta(
    name="calc_supplier_score",
    category="calc",
    description="计算供应商综合评分，包含质量/交付/价格/服务四维评分和风险惩罚（单源依赖+交付波动）。不传supplier_id则计算全部活跃供应商。当用户询问供应商评分、供应商对比、供应商风险时调用",
    parameters={
        "type": "object",
        "properties": {
            "supplier_id": {
                "type": "integer",
                "description": "供应商ID（可选，不传则计算全部）",
            },
        },
        "required": [],
    },
    handler=_calc_supplier_score_handler,
    condense=_condense_supplier_score,
    build_blocks=_query_result_to_table,
    nl_template=_supplier_ranking_template,
))

_register(ToolMeta(
    name="calc_inventory_kpi",
    category="calc",
    description="计算全量库存KPI：周转天数、呆滞SKU数及占比、资金占用。当用户询问库存效率、周转率、呆滞库存、资金占用时调用",
    parameters={
        "type": "object",
        "properties": {},
        "required": [],
    },
    handler=_calc_kpi_handler,
    condense=_condense_kpi,
    build_blocks=_query_result_to_table,
))

# ── Weather (query) ────────────────────────────────────────────────────
_register(ToolMeta(
    name="query_weather",
    category="query",
    description="查询指定城市未来7天天气预报，并自动分析受天气影响的产品品类（如冷饮受高温影响、雨具受降雨影响）。当用户询问天气、天气对产品的影响、或需要根据天气做采购决策时调用",
    parameters={
        "type": "object",
        "properties": {
            "city": {
                "type": "string",
                "description": "城市名称（中文），如：上海、北京、广州",
            },
            "days": {
                "type": "integer",
                "description": "预报天数，1-16，默认7",
                "default": 7,
            },
        },
        "required": ["city"],
    },
    handler=_weather_exec,
    condense=_condense_weather,
    build_blocks=_query_result_to_table,
))


# ═══════════════════════════════════════════════════════════════════════
# 8. Public API — ALL_TOOLS, execute_tool, helpers
# ═══════════════════════════════════════════════════════════════════════

def _build_all_tools() -> list[dict]:
    """从 REGISTRY 构建 OpenAI function calling 格式的工具列表"""
    tools = []
    for name, meta in REGISTRY.items():
        tools.append({
            "type": "function",
            "function": {
                "name": meta.name,
                "description": meta.description,
                "parameters": meta.parameters,
            },
        })
    return tools


# 按注册顺序排列（与原 ALL_TOOLS 兼容）
ALL_TOOLS = _build_all_tools()


def execute_tool(name: str, arguments: dict, db) -> dict:
    """通过 REGISTRY 查找并执行工具

    Args:
        name: 工具名称
        arguments: 工具参数字典
        db: SQLAlchemy Session

    Returns:
        工具执行结果字典，未找到工具时返回 {"error": "Unknown tool: ..."}
    """
    meta = REGISTRY.get(name)
    if meta is None:
        return {"error": f"Unknown tool: {name}"}
    return meta.handler(arguments, db)


def get_tool_meta(name: str) -> ToolMeta | None:
    """获取工具元数据"""
    return REGISTRY.get(name)


def get_tools_by_category(category: str) -> list[ToolMeta]:
    """按类别获取工具列表"""
    return [m for m in REGISTRY.values() if m.category == category]
