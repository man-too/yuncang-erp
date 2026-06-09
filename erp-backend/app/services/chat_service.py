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

SYSTEM_PROMPT = """你是供应链ERP的AI助手。你的能力是调用工具查询数据库，同时可以帮助用户查询天气信息，然后根据问题类型选择回复方式。

## 核心原则
用户问的是业务数据问题，你必须调用合适的工具查询真实数据，不能只靠自己的知识回答。
如果用户要求看图或明确要求图表时才调用 render_* 画图工具，其余情况下采用正常的文本回答。

## 回复策略
- 用户问具体数值（"多少""几个""多少钱""库存量""销量""金额"等）→ 调用 query_* 工具查数据，文字回复，不画图
- 用户要图表（"画图""看图""趋势图""排名图""热力图""柱状图""折线图"等）→ 调用 render_* 工具，图表展示 + 文字分析
- 不确定用户意图时 → 文字回复，不画图。宁可少画图也不要乱画图
- 用户说"分析""对比""排名"但没有明确要图 → 调用 query_* 查数据，用表格或文字回复

## 工具选择（关键：区分 query_* 和 render_*）
**查询类工具（只查数据，不画图）：**
- 库存数量/状态 → query_inventory
- 销量/销售金额/卖了多少 → query_sales_history
- 供应商信息/评分 → query_suppliers
- 产品信息/价格 → query_products
- ROP/安全库存/补货量 → calc_reorder_point
- 供应商评分+风险 → calc_supplier_score
- 库存周转/呆滞/资金 → calc_inventory_kpi
- 天气查询/天气情况/天气对产品影响 → query_weather（用户问天气预报、天气状况、天气对销售/采购的影响时调用）

**画图类工具（仅在用户明确要图表时才调用）：**
- 库存热力图 → render_inventory_heatmap（用户说"看库存图""库存热力图"时）
- 销售趋势图 → render_sales_trend（用户说"看趋势图""销量走势图"时）
- 供应商排名图 → render_supplier_ranking（用户说"看供应商排名图"时）
- 供应链诊断图 → render_comprehensive_diagnosis（用户说"看诊断图"时）
- 采购建议图 → render_purchase_advice（用户说"看采购建议图"时）

**推荐类工具（返回建议，自带分析）：**
- 补货推荐 → recommend_restock
- 供应商推荐 → recommend_supplier
- 采购计划审核 → audit_purchase_plan

**重要：不要同时调 render_* 和对应的 query_*！**

## 回复格式（必须返回严格 JSON）
{"content": "markdown分析文字", "blocks": [...]}

- content 必须写自然语言分析文字，必须有结论和建议。绝不能只放原始 JSON 数据、数组或代码
- content 只写分析结论，不要再以 markdown 表格重复 blocks 中已有的数据
- blocks 必须包含工具返回的结构化数据（图表或表格），用于前端渲染

## blocks 规则
1. 查询类工具（query_*、calc_*、recommend_*、analyze_*）返回的数据 → 必须放在 blocks 的 table block 中展示
2. 画图类工具（render_*）返回的数据 → 必须放在 blocks 的 chart block 或 table block 中展示
3. 综合类（同时调了 query_* + render_*）→ 可以同时放 table + chart 多个 blocks
4. 纯文字问题（如"什么是安全库存"）→ blocks 可以为空，只写文字

blocks 中每个元素为以下三种之一：
图表 block：{"type": "chart", "chartType": "line|bar|pie|heatmap|scatter|radar", "data": {完整 ECharts option}}
表格 block：{"type": "table", "columns": [{"key": "键", "title": "列标题"}], "rows": [{"键": "值"}]}
操作按钮 block：{"type": "actions", "actions": [{"label": "按钮文字", "action": "create_purchase_order|create_stock_transfer", "params": {...}, "confirmTitle": "确认标题", "confirmDetail": "详细描述"}]}

## 库存分析规则
当你决定输出库存相关图表时，在 content 中补充：
1. 列出需补货的产品及建议补货量
2. 说明理由（当前库存量、安全库存量、近期销量趋势）
3. 按紧迫程度排序，控制在 200 字以内

## 行为准则
- 无法获取数据时，content 说明原因，blocks 为空，不编造数据
- 分析结果表明需要补货 → 附带采购操作按钮
- 仓库间库存不均衡 → 附带调拨操作按钮
- 跨领域问题 → 依次调用多个工具再综合分析
- 保持专业、简洁、可执行的风格

以下操作只能以 action block 输出，不能直接调用工具执行：
- create_purchase_order: 创建采购订单
- create_stock_transfer: 创建库存调拨单"""


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
        .filter(SaleOrder.order_date >= six_months_ago, SaleOrder.status != "cancelled")
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
        .filter(SaleOrder.order_date >= thirty_days_ago, SaleOrder.status != "cancelled")
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


def _user_wants_chart(user_msg: str) -> bool:
    """判断用户是否明确要求看图表"""
    chart_keywords = ["图", "图表", "画图", "看图", "趋势图", "走势图", "折线图",
                      "热力图", "柱状图", "排名图", "对比图", "雷达图", "仪表盘",
                      "诊断图", "可视化", "可视化图表"]
    return any(kw in user_msg for kw in chart_keywords)


def _summarize_render_result(tool_name: str, result: dict | None) -> str:
    """将 render 工具的完整结果压缩为摘要，喂给 LLM 第二轮。
    避免传完整 JSON（浪费 token 且导致 LLM 重复输出 blocks）。
    明确告知 LLM 图表/表格数据已在前端展示，它只需写分析文字。"""
    if not result or "error" in result:
        return json.dumps({"status": "error", "message": result.get("error", "工具执行失败") if result else "无结果"}, ensure_ascii=False)

    # Extract summary info from blocks
    blocks_info = []
    if isinstance(result, dict) and result.get("_render"):
        blocks = result.get("blocks", [])
        for b in blocks:
            if b.get("type") == "chart":
                title = ""
                data = b.get("data", {})
                t = data.get("title")
                if isinstance(t, dict):
                    title = t.get("text", "")
                elif isinstance(t, str):
                    title = t
                series_count = len(data.get("series", []))
                blocks_info.append(f"图表[{title}](含{series_count}个系列)")
            elif b.get("type") == "table":
                cols = b.get("columns", [])
                rows = b.get("rows", [])
                col_names = [c.get("title", c.get("key", "")) for c in cols]
                blocks_info.append(f"表格[{len(rows)}行×{len(cols)}列: {', '.join(col_names[:6])}]")

    desc = f"工具{tool_name}已执行成功，图表/表格数据已直接发送到前端展示。"
    if blocks_info:
        desc += f" 生成内容: {'; '.join(blocks_info)}。"
    desc += " 你不需要在 blocks 中重复输出这些数据，只需在 content 中写出分析文字和结论。"

    # For table-type results, include a few sample rows for LLM to reference in analysis
    if isinstance(result, dict) and result.get("_render"):
        blocks = result.get("blocks", [])
        for b in blocks:
            if b.get("type") == "table" and b.get("rows"):
                sample_rows = b["rows"][:5]
                desc += f"\n\n表格前5行摘要: {json.dumps(sample_rows, ensure_ascii=False, default=str)}"

    return desc


def chat(messages: list[dict], db: Session, creator_id: int = 0) -> dict:
    """主对话函数，处理 Function Calling 循环"""
    if not client:
        return {
            "content": "AI 服务未配置，请在 .env 中设置 OPENAI_API_KEY。",
            "blocks": [],
        }

    full_messages = [{"role": "system", "content": SYSTEM_PROMPT}] + messages

    # 预处理：检测用户是否问数据问题，强制加一条 tool_trigger 提示
    user_msg = messages[-1].get("content", "") if messages else ""
    data_keywords = ["销售", "库存", "供应商", "产品", "商品", "订单", "采购", "出库", "入库",
                     "预测", "数据", "统计", "报表", "预警", "风险", "利润", "成本",
                     "金额", "销量", "数量", "热销", "卖", "天气"]
    if any(kw in user_msg for kw in data_keywords):
        full_messages.insert(1, {
            "role": "system",
            "content": "用户问的是业务数据问题，调用合适的工具来查询真实数据，如果用户要求看或者明确要求要图的时候就调用画图工具，其余情况下"
                       "采用正常的文本回答，所有结果不能只靠自己的知识回答。",
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
                    "render_safety_stock_table", "render_transfer_advice_table",
                ):
                    # Chart/table render tools: execute, collect direct-render blocks
                    result = execute_tool(tc.function.name, args, db)
                    if isinstance(result, dict) and result.get("_render"):
                        if "blocks" in result:
                            direct_blocks.extend(result["blocks"])
                        else:
                            direct_blocks.append(result)
                    # Feed a SUMMARY to LLM (not full data) — blocks are sent directly to frontend
                    # This avoids token waste and prevents LLM from duplicating blocks
                    summary = _summarize_render_result(tc.function.name, result)
                    full_messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": summary,
                    })
                else:
                    args.setdefault("creator_id", creator_id)
                    result = execute_tool(tc.function.name, args, db)
                    full_messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": json.dumps(result, ensure_ascii=False, default=str)
                    })

            # ═══ 日志②：工具执行完毕，准备第二次调 AI ═══
            logger.info(f"[Chat] 工具执行完毕, full_messages共{len(full_messages)}条, direct_blocks={len(direct_blocks)}个")

            # Second call: LLM analyzes tool results and generates response with blocks
            try:
                resp2 = client.chat.completions.create(
                    model=settings.OPENAI_MODEL,
                    messages=full_messages,
                    temperature=0.5,
                    max_tokens=4096,
                    tools=ALL_TOOLS,
                    tool_choice="auto",
                    response_format={"type": "json_object"},
                    extra_body={"thinking": {"type": "disabled"}},
                )
            except Exception as e:
                if "response_format" in str(e).lower() or "json_object" in str(e).lower():
                    resp2 = client.chat.completions.create(
                        model=settings.OPENAI_MODEL,
                        messages=full_messages,
                        temperature=0.5,
                        max_tokens=4096,
                        tools=ALL_TOOLS,
                        tool_choice="auto",
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
            # Merge direct blocks (charts/tables from render tools) — always include them
            # LLM's own blocks are merged AFTER direct_blocks so direct_blocks take priority
            if direct_blocks:
                all_blocks = direct_blocks + parsed.get("blocks", [])
                parsed["blocks"] = _dedup_chart_blocks(all_blocks)
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
                    elif tc.function.name in ("render_inventory_heatmap", "render_sales_trend", "render_supplier_ranking", "render_comprehensive_diagnosis", "render_purchase_advice", "render_safety_stock_table", "render_transfer_advice_table"):
                        result = execute_tool(tc.function.name, args, db)
                        if isinstance(result, dict) and result.get("_render"):
                            if "blocks" in result:
                                direct_blocks.extend(result["blocks"])
                            else:
                                direct_blocks.append(result)
                        summary = _summarize_render_result(tc.function.name, result)
                        full_messages.append({
                            "role": "tool", "tool_call_id": tc.id,
                            "content": summary,
                        })
                    else:
                        args.setdefault("creator_id", creator_id)
                        result = execute_tool(tc.function.name, args, db)
                        full_messages.append({
                            "role": "tool", "tool_call_id": tc.id,
                            "content": json.dumps(result, ensure_ascii=False, default=str)
                        })

                resp2 = client.chat.completions.create(
                    model=settings.OPENAI_MODEL,
                    messages=full_messages,
                    temperature=0.5,
                    max_tokens=4096,
                    tools=ALL_TOOLS,
                    tool_choice="auto",
                    response_format={"type": "json_object"},
                    extra_body={"thinking": {"type": "disabled"}},
                )
                parsed = _parse_response(resp2.choices[0].message.content)
                if direct_blocks:
                    all_blocks = direct_blocks + parsed.get("blocks", [])
                    parsed["blocks"] = _dedup_chart_blocks(all_blocks)
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


def _dedup_chart_blocks(blocks: list) -> list:
    """去除重复的 chart block（相同 title 的图表只保留第一个）"""
    seen_titles = set()
    result = []
    for b in blocks:
        if b.get("type") == "chart":
            data = b.get("data", {})
            title = ""
            if isinstance(data, dict):
                t = data.get("title")
                if isinstance(t, dict):
                    title = t.get("text", "")
                elif isinstance(t, str):
                    title = t
            if title and title in seen_titles:
                continue
            seen_titles.add(title)
        result.append(b)
    return result


def _parse_response(raw: str | None) -> dict:
    """解析 LLM 返回的原始文本为 {content, blocks} 结构"""

    def _extract_embedded_chart_json(result: dict) -> dict:
        """从 content 中提取嵌入的 chart JSON 对象，移入 blocks 列表"""
        import re
        content = result.get("content", "")
        if not content:
            return result
        blocks = result.get("blocks", [])
        # Loop until no more chart JSON found in content
        while True:
            # Find pattern {"type":"chart" or {"type": "chart"
            match = re.search(r'\{\s*"type"\s*:\s*"chart"', content)
            if not match:
                break
            start = match.start()
            # Brace-match to find the complete JSON object
            depth = 0
            in_string = False
            escape_next = False
            end = -1
            for i in range(start, len(content)):
                ch = content[i]
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
                        end = i + 1
                        break
            if end == -1:
                # No matching close brace, stop
                break
            json_str = content[start:end]
            try:
                obj = json.loads(json_str)
                if isinstance(obj, dict) and obj.get("type") == "chart" and "data" in obj:
                    blocks.append({
                        "type": "chart",
                        "chartType": obj.get("chartType", "line"),
                        "data": obj.get("data", {}),
                    })
                    # Remove the JSON fragment from content
                    content = content[:start] + content[end:]
                    # Clean up extra whitespace/newlines
                    content = re.sub(r'\s{2,}', ' ', content).strip()
                    continue
            except json.JSONDecodeError:
                pass
            # If we got here, the match didn't produce a valid chart JSON; skip it
            break

        # If content is empty or only whitespace after extraction, set default message
        if not content.strip():
            content = "图表数据已生成，请查看上方图表。"

        result["content"] = content
        result["blocks"] = blocks
        return result

    if not raw:
        return _extract_embedded_chart_json({"content": "AI 处理完成，请查看上方图表数据。", "blocks": []})
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
        # Bug 1.1: JSON array - convert to table block
        if isinstance(parsed, list):
            cols = []
            if parsed and isinstance(parsed[0], dict):
                cols = [{"key": k, "title": k} for k in parsed[0].keys()]
            return {"content": f"查询到 {len(parsed)} 条数据，详情如下。", "blocks": [{"type": "table", "columns": cols, "rows": parsed}]}
        if isinstance(parsed, (str, int, float, bool)) or parsed is None:
            return {"content": str(parsed), "blocks": []}
        # Fallback for any other type
        return {"content": json.dumps(parsed, ensure_ascii=False), "blocks": []}

    # Try direct parse
    result = try_parse(text)
    if result:
        return _extract_embedded_chart_json(result)

    # Try stripping markdown code blocks: ```json ... ``` or ``` ... ```
    import re
    m = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
    if m:
        result = try_parse(m.group(1).strip())
        if result:
            return _extract_embedded_chart_json(result)

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
                    return _extract_embedded_chart_json(result)
            except json.JSONDecodeError:
                pass
            # Keep first valid result as fallback
            if best_result is None:
                best_result = result
    if best_result:
        return _extract_embedded_chart_json(best_result)

    return _extract_embedded_chart_json({"content": raw, "blocks": []})
