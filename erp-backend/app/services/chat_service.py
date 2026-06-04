"""AI 对话服务 — 单 Agent + Function Calling"""
import json
import uuid
import logging
from datetime import date, timedelta
from openai import OpenAI
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.config import settings
from app.tools import ALL_TOOLS, execute_tool

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

client = None
if settings.OPENAI_API_KEY:
    client = OpenAI(api_key=settings.OPENAI_API_KEY, base_url=settings.AI_BASE_URL)

SYSTEM_PROMPT = """你是供应链ERP系统的AI决策助手。你的核心能力是：用户问数据类问题→调工具查数据→用图表展示→文字分析。

## 第一准则：有数据就有图表
用户任何涉及数据的问题（销售、库存、供应商、产品、趋势、排名等），你必须：
1. 调用工具获取数据（至少1个，推荐2-3个多维度）
2. 在回复的 blocks 中用图表/表格展示数据
3. 再用文字分析

## 工具说明
query_inventory / analyze_stock_risk — 库存相关
query_sales_history / forecast_sales — 销售相关（销售预测要两个都调，合并成双线图）
query_suppliers / rank_suppliers — 供应商相关
query_products — 产品查询
render_inventory_heatmap / render_sales_trend / render_supplier_ranking — 专属图表（复杂可视化）
render_comprehensive_diagnosis — 供应链综合诊断（健康评分雷达图+仪表盘+总结表格），当用户问"综合诊断"/"供应链状况"时调用
render_purchase_advice — 采购建议（补货柱状图+推荐供应商表格+费用估算），当用户问"采购建议"/"补货推荐"时调用
recommend_restock / recommend_supplier — 多维度推荐

## 回复格式（必须返回JSON）
{"content": "markdown文字", "blocks": [可视化块]}
- 时间序列→折线图, 对比数据→柱状图, 关系数据→热力图, 列表→表格

## 关键：无法获取数据时的处理
如果调工具失败或数据为空，在 content 中明确告知用户原因，blocks 保持空数组。不要编造数据。
以下操作只能以 action block 形式输出给用户，不能直接调用工具执行：
- create_purchase_order: 创建采购订单
- create_stock_transfer: 创建库存调拨单

## 回复格式
你必须返回严格的JSON格式，包含以下字段：
{
  "content": "Markdown格式的自然语言回复（面向业务人员，简洁实用，适当使用**加粗**、- 列表等格式）",
  "blocks": []
}

blocks 是可选的结构化内容数组，每个元素可以是：

1. 图表 block：
{"type": "chart", "chartType": "line|bar|pie|heatmap|scatter|radar", "data": {完整的ECharts option对象}}
注意 data 必须包含 title、tooltip、xAxis、yAxis、series 等完整配置。如果不需要legend则省略。所有文字标签使用中文。
配色推荐：蓝色系(#5470c6, #91cc75, #fac858, #ee6666, #73c0de, #fc8452)

2. 表格 block：
{"type": "table", "columns": [{"key": "键", "title": "列标题"}], "rows": [{"键": "值"}]}

3. 操作按钮 block：
{"type": "actions", "actions": [{"label": "按钮文字", "action": "create_purchase_order|create_stock_transfer", "params": {...}, "confirmTitle": "确认标题", "confirmDetail": "详细描述"}]}

## 行为准则
- 用户问数据类问题时，先调用工具获取最新数据再回答
- 用图表直观展示数据趋势和对比
- 当分析结果表明需要补货时，给出具体的采购建议并附带操作按钮
- 当发现仓库间库存不均衡时，给出调拨建议并附带操作按钮
- 对于跨领域问题（如"低库存产品的供应商表现如何"），依次调用多个工具再综合分析
- 保持专业、简洁、可执行的风格"""


def build_welcome_context(db: Session) -> dict:
    """预加载会话摘要上下文"""
    from app.models.product import Product
    from app.models.inventory import Inventory, Warehouse
    from app.models.supplier import Supplier
    from app.models.sale import SaleOrder, SaleOrderItem

    # Low stock
    low_rows = (
        db.query(Product.name, Inventory.quantity, Product.min_stock, Product.unit,
                 Warehouse.name.label("wname"))
        .join(Inventory, Inventory.product_id == Product.id)
        .join(Warehouse, Inventory.warehouse_id == Warehouse.id)
        .filter(Inventory.quantity <= Product.min_stock, Inventory.quantity >= 0)
        .order_by(Inventory.quantity)
        .limit(10).all()
    )
    low_stock = [
        {"name": r[0], "qty": float(r[1]), "min": float(r[2]), "unit": r[3], "warehouse": r[4]}
        for r in low_rows
    ]

    # Out of stock count
    out_of_stock = (
        db.query(Inventory).filter(Inventory.quantity == 0).count()
    )

    # Monthly sales (last 6 months)
    six_months_ago = date.today() - timedelta(days=180)
    date_fmt = func.date_format(SaleOrder.order_date, '%Y-%m')
    monthly = (
        db.query(
            date_fmt.label('m'),
            func.sum(SaleOrderItem.quantity).label('qty'),
            func.sum(SaleOrderItem.total_price).label('amount'),
        )
        .join(SaleOrderItem, SaleOrderItem.order_id == SaleOrder.id)
        .filter(SaleOrder.order_date >= six_months_ago)
        .group_by(date_fmt).order_by(date_fmt)
        .all()
    )
    monthly_trend = [
        {"month": r.m, "qty": float(r.qty or 0), "amount": float(r.amount or 0)}
        for r in monthly
    ]

    # Top suppliers
    top = (
        db.query(Supplier.name, Supplier.rating, Supplier.delivery_lead_time)
        .filter(Supplier.status == "active")
        .order_by(Supplier.rating.desc())
        .limit(5).all()
    )
    top_suppliers = [
        {"name": s[0], "rating": float(s[1] or 0), "lead_time": s[2]}
        for s in top
    ]

    # Hot selling products (last 30 days)
    thirty_days_ago = date.today() - timedelta(days=30)
    hot = (
        db.query(
            Product.name,
            func.sum(SaleOrderItem.quantity).label('qty'),
            func.sum(SaleOrderItem.total_price).label('amount'),
        )
        .join(SaleOrderItem, SaleOrderItem.product_id == Product.id)
        .join(SaleOrder, SaleOrder.id == SaleOrderItem.order_id)
        .filter(SaleOrder.order_date >= thirty_days_ago)
        .group_by(Product.id, Product.name)
        .order_by(func.sum(SaleOrderItem.quantity).desc())
        .limit(5).all()
    )
    hot_products = [
        {"name": h[0], "qty": float(h[1] or 0), "amount": float(h[2] or 0)}
        for h in hot
    ]

    return {
        "low_stock": low_stock,
        "out_of_stock_count": out_of_stock,
        "monthly_sales_trend": monthly_trend,
        "top_suppliers": top_suppliers,
        "hot_products": hot_products,
    }


def build_welcome_message(context: dict) -> dict:
    """生成首次进入的主动问候"""
    low = context["low_stock"]
    hot = context["hot_products"]
    top_sup = context["top_suppliers"]

    parts = ["您好！我是您的供应链AI助手。以下是当前系统状态概览：\n"]

    # 库存状态
    if low:
        parts.append("### 🔴 库存高危预警")
        for p in low[:5]:
            parts.append(f"- **{p['name']}**：仅剩 {p['qty']}{p['unit']}（安全线 {p['min']}{p['unit']}），仓库：{p['warehouse']}")
        parts.append("")
    elif context["out_of_stock_count"] > 0:
        parts.append(f"### 🔴 库存预警：{context['out_of_stock_count']} 个产品已缺货\n")
    else:
        parts.append("### ✅ 库存状态：所有产品库存正常\n")

    # 月度趋势
    trend = context["monthly_sales_trend"]
    if len(trend) >= 2:
        latest = trend[-1]
        prev = trend[-2]
        change = (latest["amount"] - prev["amount"]) / prev["amount"] * 100 if prev["amount"] > 0 else 0
        arrow = "↑" if change > 0 else "↓" if change < 0 else "→"
        parts.append(f"### 📊 月度销售：{latest['month']} 金额 ¥{latest['amount']:,.0f}（环比 {arrow}{abs(change):.1f}%）\n")

    # 优质供应商
    if top_sup:
        parts.append("### 🏆 优质供应商 TOP3：" + "、".join(s["name"] for s in top_sup[:3]) + "\n")

    # 热销产品 - 放在文字最后，紧挨表格
    parts.append("### 📈 近期热销产品 TOP5（近30天）")
    hot_rows = [
        {"rank": i + 1, "name": h["name"], "qty": f"{h['qty']:.0f}", "amount": f"¥{h['amount']:,.0f}"}
        for i, h in enumerate(hot[:5])
    ]
    hot_table = {
        "type": "table",
        "columns": [
            {"key": "rank", "title": "排名"},
            {"key": "name", "title": "产品名称"},
            {"key": "qty", "title": "销量（件）"},
            {"key": "amount", "title": "金额（元）"},
        ],
        "rows": hot_rows if hot_rows else [{"rank": "-", "name": "暂无近30天销售数据", "qty": "-", "amount": "-"}]
    }
    parts.append("")

    content = "\n".join(parts)

    # Blocks: 热销表在前，库存柱状图在后
    blocks: list = [hot_table]
    if low:
        names = [p["name"] for p in low[:8]]
        current_qtys = [p["qty"] for p in low[:8]]
        min_stocks = [p["min"] for p in low[:8]]

        blocks.append({
            "type": "chart",
            "chartType": "bar",
            "data": {
                "title": {"text": "低库存产品概览", "left": "center", "textStyle": {"fontSize": 14}},
                "tooltip": {"trigger": "axis", "axisPointer": {"type": "shadow"}},
                "legend": {"data": ["当前库存", "安全库存"], "bottom": 0},
                "grid": {"top": 50, "bottom": 60, "left": 60, "right": 30},
                "xAxis": {"type": "category", "data": names, "axisLabel": {"rotate": 30, "fontSize": 11}},
                "yAxis": {"type": "value", "name": "库存量"},
                "series": [
                    {"name": "当前库存", "type": "bar", "data": current_qtys, "itemStyle": {"color": "#5470c6"}, "barMaxWidth": 30},
                    {"name": "安全库存", "type": "bar", "data": min_stocks, "itemStyle": {"color": "#ee6666"}, "barMaxWidth": 30},
                ],
            }
        })

    return {"content": content, "blocks": blocks}


def _auto_chart_from_result(tool_name: str, result: dict) -> dict | None:
    """自动从工具结果中提取数据并生成图表 block"""
    if not isinstance(result, dict):
        return None

    # query_sales_history → 折线图
    if tool_name == "query_sales_history":
        items = result.get("items", [])
        if len(items) >= 2:
            dates = [str(i.get("date", i.get("period", ""))) for i in items]
            values = [float(i.get("quantity", i.get("amount", 0))) for i in items]
            label = "销量" if "quantity" in (items[0] if items else {}) else "金额"
            return {
                "type": "chart", "chartType": "line",
                "data": {
                    "title": {"text": "销售趋势", "left": "center", "textStyle": {"fontSize": 14}},
                    "tooltip": {"trigger": "axis"},
                    "legend": {"data": [label], "bottom": 0},
                    "grid": {"left": 60, "right": 30, "top": 40, "bottom": 40},
                    "xAxis": {"type": "category", "data": dates, "axisLabel": {"rotate": 30, "fontSize": 10}},
                    "yAxis": {"type": "value", "name": label},
                    "dataZoom": [{"type": "inside"}],
                    "series": [{"name": label, "type": "line", "smooth": True, "data": values,
                                "lineStyle": {"color": "#5470c6", "width": 2}, "areaStyle": {"color": "rgba(84,112,198,0.12)"}}],
                },
            }

    # forecast_sales → 预测数据 + 历史数据合并为双线图
    if tool_name == "forecast_sales":
        history = result.get("history", [])
        forecast_qty = result.get("forecast_next_30d", 0)
        trend = result.get("trend", "")
        if history:
            hist_dates = [str(h.get("date", "")) for h in history]
            hist_values = [float(h.get("quantity", 0)) for h in history]
            # Generate future dates for prediction
            last_date = hist_dates[-1] if hist_dates else ""
            try:
                from datetime import datetime, timedelta
                last = datetime.strptime(last_date, "%Y-%m-%d") if last_date else datetime.today()
                fut_dates = [(last + timedelta(days=i+1)).strftime("%Y-%m-%d") for i in range(7)]
            except:
                fut_dates = [f"预测D+{i+1}" for i in range(7)]
            # Distribute forecast across 7 days
            daily_forecast = round(forecast_qty / 7, 1) if forecast_qty > 0 else 0
            fut_values = [daily_forecast] * 7

            # Build dual-line chart with empty gaps
            all_dates = hist_dates + fut_dates
            all_hist = hist_values + [None] * len(fut_dates)
            all_fcst = [None] * len(hist_values) + fut_values

            return {
                "type": "chart", "chartType": "line",
                "data": {
                    "title": {"text": "销售预测", "left": "center", "textStyle": {"fontSize": 14}},
                    "tooltip": {"trigger": "axis", "axisPointer": {"type": "cross"}},
                    "legend": {"data": ["历史销量", "预测销量"], "bottom": 0},
                    "grid": {"left": 60, "right": 30, "top": 40, "bottom": 40},
                    "xAxis": {"type": "category", "data": all_dates, "axisLabel": {"fontSize": 10}},
                    "yAxis": {"type": "value", "name": "销量"},
                    "dataZoom": [{"type": "inside"}, {"type": "slider", "bottom": 30}],
                    "series": [
                        {"name": "历史销量", "type": "line", "smooth": True, "data": all_hist,
                         "lineStyle": {"color": "#5470c6", "width": 2}, "symbol": "circle", "symbolSize": 5},
                        {"name": "预测销量", "type": "line", "smooth": True, "data": all_fcst,
                         "lineStyle": {"color": "#fc8452", "width": 2, "type": "dashed"},
                         "symbol": "diamond", "symbolSize": 7, "areaStyle": {"color": "rgba(252,132,82,0.1)"}},
                    ],
                },
            }

    # query_inventory → 柱状图
    if tool_name == "query_inventory":
        items = result.get("items", [])
        if len(items) >= 2:
            names = [i.get("product_name", "") for i in items]
            values = [float(i.get("quantity", 0)) for i in items]
            return {
                "type": "chart", "chartType": "bar",
                "data": {
                    "title": {"text": "库存分布", "left": "center", "textStyle": {"fontSize": 14}},
                    "tooltip": {"trigger": "axis"},
                    "grid": {"left": 60, "right": 30, "top": 40, "bottom": 60},
                    "xAxis": {"type": "category", "data": names, "axisLabel": {"rotate": 30, "fontSize": 10}},
                    "yAxis": {"type": "value", "name": "库存量"},
                    "series": [{"name": "库存量", "type": "bar", "data": values, "itemStyle": {"color": "#5470c6"}, "barMaxWidth": 30}],
                },
            }

    # query_suppliers / rank_suppliers → 柱状图
    if tool_name in ("query_suppliers", "rank_suppliers"):
        key = "suppliers" if "suppliers" in result else ("items" if "items" in result else None)
        items = result.get(key, []) if key else []
        if len(items) >= 2:
            names = [i.get("name", i.get("supplier_name", "")) for i in items]
            values = [float(i.get("rating", i.get("total_score", 0))) for i in items]
            return {
                "type": "chart", "chartType": "bar",
                "data": {
                    "title": {"text": "供应商评分", "left": "center", "textStyle": {"fontSize": 14}},
                    "tooltip": {"trigger": "axis"},
                    "grid": {"left": 60, "right": 30, "top": 40, "bottom": 60},
                    "xAxis": {"type": "category", "data": names, "axisLabel": {"rotate": 20, "fontSize": 10}},
                    "yAxis": {"type": "value", "name": "评分"},
                    "series": [{"name": "评分", "type": "bar", "data": values, "itemStyle": {"color": "#91cc75"}, "barMaxWidth": 30}],
                },
            }

    return None


def chat(messages: list[dict], db: Session, creator_id: int = 0) -> dict:
    """主对话函数，处理 Function Calling 循环"""
    if not client:
        return {
            "content": "AI 服务未配置，请在 .env 中设置 OPENAI_API_KEY（可使用 DeepSeek API）。",
            "blocks": [],
        }

    full_messages = [{"role": "system", "content": SYSTEM_PROMPT}] + messages

    # 预处理：检测用户是否问数据问题，强制加一条 tool_trigger 提示
    user_msg = messages[-1].get("content", "") if messages else ""
    data_keywords = ["销售", "库存", "供应商", "产品", "订单", "采购", "出库", "入库",
                     "趋势", "预测", "排名", "对比", "分析", "数据", "统计", "报表",
                     "预警", "风险", "利润", "成本", "金额", "销量", "数量"]
    if any(kw in user_msg for kw in data_keywords):
        full_messages.insert(1, {
            "role": "system",
            "content": "用户问的是业务数据问题，你必须调用合适的工具来查询真实数据，不能只靠自己的知识回答。查询到数据后在blocks中用图表展示。",
        })

    try:
        resp = client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=full_messages,
            tools=ALL_TOOLS,
            tool_choice="auto",
            temperature=0.3,
            max_tokens=8192,
            extra_body={"thinking": {"type": "disabled"}},
        )
        msg = resp.choices[0].message

        # ═══ 日志①：第一次 AI 调用结果 ═══
        logger.info(f"[Chat] 第一次调 AI | 模型: {resp.model} | finish: {resp.choices[0].finish_reason} | token: {resp.usage}")
        if msg.tool_calls:
            logger.info(f"[Chat] AI 决定调 {len(msg.tool_calls)} 个工具: {[tc.function.name for tc in msg.tool_calls]}")
        else:
            logger.info(f"[Chat] AI 直接回答（未调工具）, content长度={len(msg.content or '')}")

        if msg.tool_calls:
            assistant_msg: dict = {
                "role": "assistant",
                "content": msg.content or "",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments}
                    }
                    for tc in msg.tool_calls
                ]
            }
            # DeepSeek thinking models require reasoning_content to be passed back
            if hasattr(msg, 'reasoning_content') and msg.reasoning_content:
                assistant_msg["reasoning_content"] = msg.reasoning_content
            full_messages.append(assistant_msg)

            direct_blocks: list = []
            for tc in msg.tool_calls:
                try:
                    args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    args = {}
                # Action tools must not execute here — return action block instead
                if tc.function.name in ("create_purchase_order", "create_stock_transfer"):
                    full_messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": json.dumps({
                            "blocked": True,
                            "message": "此操作需要用户确认后才能执行，请以 action block 形式输出给用户"
                        }, ensure_ascii=False)
                    })
                elif tc.function.name in (
                    "render_inventory_heatmap", "render_sales_trend",
                    "render_supplier_ranking",
                    "render_comprehensive_diagnosis", "render_purchase_advice",
                ):
                    # Chart tools: execute, collect direct-render blocks, also feed to LLM
                    result = execute_tool(tc.function.name, args, db)
                    if isinstance(result, dict) and result.get("_render"):
                        if "blocks" in result:
                            # Multi-block format
                            direct_blocks.extend(result["blocks"])
                        else:
                            # Single block fallback
                            direct_blocks.append(result)
                    full_messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": json.dumps(result, ensure_ascii=False, default=str)
                    })
                else:
                    args.setdefault("creator_id", creator_id)
                    result = execute_tool(tc.function.name, args, db)
                    full_messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": json.dumps(result, ensure_ascii=False, default=str)
                    })
                    # Auto-generate chart from structured tool result data
                    chart = _auto_chart_from_result(tc.function.name, result)
                    if chart:
                        direct_blocks.append(chart)

            # ═══ 日志②：工具执行完毕，准备第二次调 AI ═══
            logger.info(f"[Chat] 工具执行完毕, full_messages共{len(full_messages)}条, direct_blocks={len(direct_blocks)}个")

            # Second call: LLM analyzes tool results and generates response with blocks
            try:
                resp2 = client.chat.completions.create(
                    model=settings.OPENAI_MODEL,
                    messages=full_messages,
                    temperature=0.3,
                    max_tokens=4096,
                    response_format={"type": "json_object"},
                    extra_body={"thinking": {"type": "disabled"}},
                )
            except Exception as e:
                if "response_format" in str(e).lower() or "json_object" in str(e).lower():
                    resp2 = client.chat.completions.create(
                        model=settings.OPENAI_MODEL,
                        messages=full_messages,
                        temperature=0.3,
                        max_tokens=4096,
                        extra_body={"thinking": {"type": "disabled"}},
                    )
                else:
                    raise
            raw_content = resp2.choices[0].message.content

            # Bug 1.4: Handle reasoning_content from second LLM call (DeepSeek thinking models)
            msg2 = resp2.choices[0].message
            if hasattr(msg2, 'reasoning_content') and msg2.reasoning_content:
                logger.info(f"[Chat] 第二次调用有 reasoning_content, 长度={len(msg2.reasoning_content)}")

            # ═══ 日志③：第二次 AI 调用结果 ═══
            logger.info(f"[Chat] 第二次调 AI | finish: {resp2.choices[0].finish_reason} | "
                        f"token: {resp2.usage} | content长度={len(raw_content or '')} | "
                        f"前200字: >>>{(raw_content or '')[:200]}<<<")

            parsed = _parse_response(raw_content)
            # Merge direct blocks (charts) at front of response
            if direct_blocks:
                parsed["blocks"] = direct_blocks + parsed.get("blocks", [])
            return parsed

        # LLM 没调工具：如果是数据类问题，强制重试一次
        is_data_query = any(kw in user_msg for kw in data_keywords)
        if is_data_query:
            full_messages.append({
                "role": "system",
                "content": "警告：你刚才没有调用任何工具就直接回答了。用户问的是业务数据，你必须调用工具查询真实数据库，不能凭空回答。现在请重新调用合适的工具来获取数据。",
            })
            retry = client.chat.completions.create(
                model=settings.OPENAI_MODEL,
                messages=full_messages,
                tools=ALL_TOOLS,
                tool_choice="auto",
                temperature=0.3,
                max_tokens=8192,
                extra_body={"thinking": {"type": "disabled"}},
            )
            retry_msg = retry.choices[0].message
            if retry_msg.tool_calls:
                # Replace msg with retry result
                msg = retry_msg
                # Re-construct assistant_msg and continue to tool processing
                assistant_msg = {
                    "role": "assistant",
                    "content": msg.content or "",
                    "tool_calls": [
                        {"id": tc.id, "type": "function",
                         "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                        for tc in msg.tool_calls
                    ],
                }
                if hasattr(msg, 'reasoning_content') and msg.reasoning_content:
                    assistant_msg["reasoning_content"] = msg.reasoning_content
                full_messages.append(assistant_msg)

                direct_blocks = []
                for tc in msg.tool_calls:
                    try:
                        args = json.loads(tc.function.arguments)
                    except json.JSONDecodeError:
                        args = {}
                    if tc.function.name in ("create_purchase_order", "create_stock_transfer"):
                        full_messages.append({
                            "role": "tool", "tool_call_id": tc.id,
                            "content": json.dumps({"blocked": True, "message": "需用户确认"}, ensure_ascii=False)
                        })
                    elif tc.function.name in ("render_inventory_heatmap", "render_sales_trend", "render_supplier_ranking", "render_comprehensive_diagnosis", "render_purchase_advice"):
                        result = execute_tool(tc.function.name, args, db)
                        if isinstance(result, dict) and result.get("_render"):
                            if "blocks" in result:
                                direct_blocks.extend(result["blocks"])
                            else:
                                direct_blocks.append(result)
                        full_messages.append({
                            "role": "tool", "tool_call_id": tc.id,
                            "content": json.dumps(result, ensure_ascii=False, default=str)
                        })
                    else:
                        args.setdefault("creator_id", creator_id)
                        result = execute_tool(tc.function.name, args, db)
                        full_messages.append({
                            "role": "tool", "tool_call_id": tc.id,
                            "content": json.dumps(result, ensure_ascii=False, default=str)
                        })
                        chart = _auto_chart_from_result(tc.function.name, result)
                        if chart:
                            direct_blocks.append(chart)

                resp2 = client.chat.completions.create(
                    model=settings.OPENAI_MODEL,
                    messages=full_messages,
                    temperature=0.3,
                    max_tokens=4096,
                    response_format={"type": "json_object"},
                    extra_body={"thinking": {"type": "disabled"}},
                )
                parsed = _parse_response(resp2.choices[0].message.content)
                if direct_blocks:
                    parsed["blocks"] = direct_blocks + parsed.get("blocks", [])
                return parsed

            else:
                # 重试后 AI 仍没调工具，直接返回 retry_msg 的内容
                logger.info(f"[Chat] 重试后 AI 仍没调工具, content={retry_msg.content}")
                return _parse_response(retry_msg.content)

        # ═══ 日志④：AI 直接返回 ═══
        logger.info(f"[Chat] AI 直接返回, content长度={len(msg.content or '')}, 前50字: {(msg.content or '')[:50]}")
        return _parse_response(msg.content)

    except Exception as e:
        logger.error(f"[Chat] 异常: {e}", exc_info=True)
        return {"content": f"处理请求时出错，请重试。错误信息：{str(e)}", "blocks": []}


def _parse_response(raw: str | None) -> dict:
    if not raw:
        return {"content": "AI 处理完成，请查看上方图表数据。", "blocks": []}
    text = raw.strip()

    def try_parse(t: str) -> dict | None:
        try:
            parsed = json.loads(t)
        except json.JSONDecodeError:
            return None
        if isinstance(parsed, dict):
            return {
                "content": parsed.get("content", raw),
                "blocks": parsed.get("blocks", []),
            }
        # Bug 1.1: JSON array or other non-dict - convert to readable string
        if isinstance(parsed, list):
            return {"content": json.dumps(parsed, ensure_ascii=False), "blocks": []}
        if isinstance(parsed, (str, int, float, bool)) or parsed is None:
            return {"content": str(parsed), "blocks": []}
        # Fallback for any other type
        return {"content": json.dumps(parsed, ensure_ascii=False), "blocks": []}

    # Try direct parse
    result = try_parse(text)
    if result:
        return result

    # Try stripping markdown code blocks: ```json ... ``` or ``` ... ```
    import re
    m = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
    if m:
        result = try_parse(m.group(1).strip())
        if result:
            return result

    # Bug 1.5: Try ALL {...} candidates (last to first), prefer ones with content/blocks keys
    candidates = []
    pos = 0
    while True:
        start = text.find("{", pos)
        if start == -1:
            break
        depth = 0
        in_string = False
        escape_next = False
        for i in range(start, len(text)):
            ch = text[i]
            if escape_next:
                escape_next = False
                continue
            if ch == "\\":
                escape_next = True
                continue
            if ch == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    candidates.append(text[start:i + 1])
                    pos = i + 1
                    break
        else:
            # No matching close brace found for this open brace
            break

    # Try candidates from last to first, preferring ones with content/blocks keys
    best_result = None
    for candidate in reversed(candidates):
        result = try_parse(candidate)
        if result:
            # Check if this dict has content or blocks keys (preferred)
            try:
                parsed = json.loads(candidate)
                if isinstance(parsed, dict) and ("content" in parsed or "blocks" in parsed):
                    return result
            except json.JSONDecodeError:
                pass
            # Keep first valid result as fallback
            if best_result is None:
                best_result = result
    if best_result:
        return best_result

    return {"content": raw, "blocks": []}
