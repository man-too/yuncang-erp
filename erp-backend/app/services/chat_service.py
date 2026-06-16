"""AI 对话服务 — 两层串联 + 纯文本分析 + 流式版本

架构:
  Layer 1 (ROUTING_PROMPT): LLM 选择工具调用，不生成分析文字
  Layer 2 (ANALYSIS_PROMPT): LLM 根据精简数据写纯文本分析，不输出 JSON

chat()       → 非流式，返回 {"content": ..., "blocks": [...]}
chat_stream() → 流式，yield {"type": "blocks"/"content_delta"/"done", ...}
"""
import json
import logging
from dataclasses import dataclass
from datetime import date, timedelta
from openai import OpenAI
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.config import settings
from app.tools import ALL_TOOLS, execute_tool, get_tool_meta

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# ═══════════════════════════════════════════════════════════════
# Intent classification — pre_filter layer
# ═══════════════════════════════════════════════════════════════

ONLY_CHART_KW = ["只要图", "只看图", "给我图", "图就行", "不用分析", "不用解释", "别分析", "图就好"]
CHART_KW = ["看图", "画图", "趋势图", "走势图", "折线图", "热力图", "柱状图", "排名图", "诊断图", "图表"]
ACTION_KW = ["下单", "创建订单", "调拨", "创建调拨"]
DATA_KW = [
    "销售", "库存", "供应商", "产品", "商品", "订单", "采购", "出库", "入库",
    "预测", "数据", "统计", "报表", "预警", "风险", "利润", "成本", "金额",
    "销量", "数量", "热销", "卖", "天气", "补货", "推荐补货", "供应商推荐",
]


@dataclass
class IntentResult:
    intent: str       # "data_query" | "chart_only" | "casual" | "action"
    chart_flag: bool  # 是否需要图表


def classify_intent(user_msg: str) -> IntentResult:
    """基于关键词的意图分类，优先级: ONLY_CHART > ACTION > CHART > DATA > casual"""
    if any(kw in user_msg for kw in ONLY_CHART_KW):
        return IntentResult(intent="chart_only", chart_flag=True)
    if any(kw in user_msg for kw in ACTION_KW):
        return IntentResult(intent="action", chart_flag=False)
    if any(kw in user_msg for kw in CHART_KW):
        return IntentResult(intent="data_query", chart_flag=True)
    if any(kw in user_msg for kw in DATA_KW):
        return IntentResult(intent="data_query", chart_flag=False)
    return IntentResult(intent="casual", chart_flag=False)


def _infer_chart_flag(tool_calls: list) -> bool:
    """从 LLM 选择的工具推断是否需要图表"""
    for tc in tool_calls:
        name = tc.function.name if hasattr(tc, "function") else tc.get("function", {}).get("name", "")
        meta = get_tool_meta(name)
        if meta and meta.category == "render":
            return True
    return False


def _strategy_hints_for_tools(tool_calls: list) -> list[str]:
    """根据本轮调用的工具名，返回需要注入到 ANALYSIS 阶段的策略提示。

    - recommend_restock / 任何包含 'restock'/'replenish'/'reorder' 的工具 → 补货策略
    - recommend_supplier / 任何包含 'supplier' 的工具 → 供应商策略
    """
    hints: list[str] = []
    seen_replenish = False
    seen_supplier = False
    for tc in tool_calls or []:
        name = tc.function.name if hasattr(tc, "function") else tc.get("function", {}).get("name", "")
        if not name:
            continue
        lname = name.lower()
        if not seen_replenish and any(k in lname for k in ("restock", "replenish", "reorder")):
            hints.append(REPLENISHMENT_STRATEGY_HINT)
            seen_replenish = True
        if not seen_supplier and "supplier" in lname:
            hints.append(SUPPLIER_STRATEGY_HINT)
            seen_supplier = True
    return hints


# ═══════════════════════════════════════════════════════════════
# Prompt constants — Layer 1 routing + Layer 2 analysis
# ═══════════════════════════════════════════════════════════════

ROUTING_PROMPT = """你是供应链ERP的AI助手。用户问业务数据时必须调用工具查询真实数据，不能凭空回答。不要假设参数值，不确定时先问用户。只能使用提供的工具，不要编造工具。

## 工具选择步骤
Step 1: 用户要图表（含"图/画图/看图/趋势图/热力图/排名图/诊断图"等）→ 调 render_*，不要再调对应的 query_*
Step 2: 用户不要图表 → 调 query_* 或 calc_* 查数据，用文字回复
Step 3: 用户要补货推荐 → recommend_restock；供应商推荐 → recommend_supplier；采购审核 → audit_purchase_plan
Step 4: 操作类（create_purchase_order / create_stock_transfer）→ 只输出 action block，需用户确认"""

ANALYSIS_PROMPT = """你是供应链分析师。根据工具返回的数据写分析。

规则：
1. 结论 + 行动建议，200字以内
2. 只引用数据中存在的数字，不编造
3. 数据不足时明确说"缺少XX数据，建议查询YY"
4. 纯文本，不输出 JSON、不调工具

好：电子元件A仅剩2.7天库存，低于14天交期，建议立即下单≥42件。
差：✗"建议优化管理流程"（无数据支撑）✗输出JSON ✗重复描述数据 ✗超过200字

现在请分析以下数据："""

ANALYSIS_HINT_RENDER = "图表/表格数据已直接发送到前端展示，你只需写出分析文字和结论，不要重复输出这些数据。"

DATA_HINT = "用户问的是业务数据问题，必须调用工具获取真实数据，不能凭空回答。用户要图时直接调 render_*（不要先调 query_* 查数据），只要数据时用 query_* + calc_*。"

RETRY_HINT = "警告：你刚才没有调用任何工具就直接回答了。用户问的是业务数据，你必须调用工具查询真实数据库，不能凭空回答。现在请重新调用合适的工具来获取数据。"

# ── 补货决策场景的策略注入（供参考，不强制遵循）──
REPLENISHMENT_STRATEGY_HINT = """补货决策法则（供参考，根据实际情况灵活判断）：
1. 再订货点 ROP = 日均需求 × 提前期 + 安全库存 — 工具已计算，重点看 current_qty 与 ROP 的差距
2. 补货量 ≈ ROP - current_qty - in_transit_qty，工具已算出 suggested_qty 字段，可直接引用
3. 趋势(trend)上升且变化幅度>20% → 在 suggested_qty 基础上上调 10-30%
4. 趋势下降且变化幅度>20% → 在 suggested_qty 基础上下调 10-30%
5. abc_class 为 C 类 + 趋势平稳 → 维持基线，不需要上调
6. backlog_qty > 0 表示有未发货积压，应纳入紧急度判断
7. 若有 forecast_avg_daily 字段，优先使用预测日均需求而非历史均值
8. 若 forecast_confidence_high 远高于 forecast_confidence_mid，说明需求不确定性高，应增加安全库存
9. 若 forecast_seasonality 不为 none，说明存在季节性周期，需考虑提前备货
10. 若回测结果显示某模型 WMAPE < 0.2，说明该模型预测可靠，可优先参考其预测值
11. 若回测最优模型为 naive 而非 prophet，说明该产品季节性弱，Prophet 可能过拟合
12. ensemble 模式下权重由回测表现动态决定，非固定值
分析时优先引用 demand_desc / rop / suggested_qty / trend / forecast_avg_daily 字段，不要自己重算公式。"""

# ── 供应商选择场景的策略注入 ──
SUPPLIER_STRATEGY_HINT = """供应商选择优先级（工具已按 urgency 给出动态权重，weights_used 字段可见）：
- urgent (缺货)：交付准时率为王，价格次要
- very_high / high：偏向交付，质量与价格平衡
- normal：性价比优先，质量与价格并重
关注 total_score、is_single_source、suggested_share 三个字段做排序与建议；单源依赖供应商需提示开发备选。"""

# ═══════════════════════════════════════════════════════════════
# OpenAI client
# ═══════════════════════════════════════════════════════════════

client = None
if settings.OPENAI_API_KEY:
    client = OpenAI(api_key=settings.OPENAI_API_KEY, base_url=settings.AI_BASE_URL)


# ═══════════════════════════════════════════════════════════════
# Welcome context (unchanged)
# ═══════════════════════════════════════════════════════════════

def build_welcome_context(db: Session) -> dict:
    """预加载会话摘要上下文"""
    from app.models.product import Product
    from app.models.inventory import Inventory, Warehouse
    from app.models.supplier import Supplier
    from app.models.sale import SaleOrder, SaleOrderItem

    # Low stock (按产品聚合全仓库库存后判断)
    low_stock_rows = (
        db.query(
            Product.name, Product.min_stock, Product.unit,
            func.sum(Inventory.quantity).label("total_qty"),
            func.group_concat(func.distinct(Warehouse.name)).label("warehouses"),
        )
        .join(Inventory, Inventory.product_id == Product.id)
        .join(Warehouse, Warehouse.id == Inventory.warehouse_id)
        .group_by(Product.id)
        .having(func.sum(Inventory.quantity) <= Product.min_stock)
        .order_by(func.sum(Inventory.quantity))
        .limit(10).all()
    )
    low_stock = [
        {
            "name": r[0],
            "qty": float(r[3]),
            "min": float(r[1]),
            "unit": r[2],
            "warehouse": (r[4] or "").replace(",", "、") if r[4] else "未知仓库",
        }
        for r in low_stock_rows
    ]

    # Out of stock count (全仓库总量为0的产品数)
    out_of_stock = (
        db.query(func.count())
        .select_from(
            db.query(Inventory.product_id)
            .group_by(Inventory.product_id)
            .having(func.sum(Inventory.quantity) == 0)
            .subquery()
        )
        .scalar() or 0
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


# ═══════════════════════════════════════════════════════════════
# Helper functions
# ═══════════════════════════════════════════════════════════════

def _call_llm_once(messages, tool_choice="auto", temperature=0.3):
    """Single LLM call with tools"""
    return client.chat.completions.create(
        model=settings.OPENAI_MODEL,
        messages=messages,
        tools=ALL_TOOLS,
        tool_choice=tool_choice,
        temperature=temperature,
        max_tokens=8192,
        extra_body={"thinking": {"type": "disabled"}},
    )


def _build_assistant_msg(msg) -> dict:
    """Build assistant message dict from LLM response"""
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
    return assistant_msg


def _template_fallback(tool_calls, tool_cache: dict, db) -> str:
    """Rule template fallback — uses cache, no re-execution"""
    for tc in tool_calls:
        name = tc.function.name if hasattr(tc, "function") else tc.get("function", {}).get("name", "")
        meta = get_tool_meta(name)
        if meta and meta.nl_template:
            cached_result = tool_cache.get(name)
            if cached_result:
                return meta.nl_template(cached_result)
    return "数据已加载，请查看下方图表/表格。"


# ═══════════════════════════════════════════════════════════════
# _process_tool_calls — unified tool processing
# ═══════════════════════════════════════════════════════════════

def _process_tool_calls(tool_calls: list, db: Session, creator_id: int) -> tuple[list, list, list[dict], dict]:
    """统一处理 LLM 返回的工具调用

    Returns:
        (direct_blocks, condense_texts, tool_results, tool_cache)
    """
    direct_blocks = []
    condense_texts = []
    tool_results = []
    tool_cache = {}

    for tc in tool_calls:
        name = tc.function.name if hasattr(tc, "function") else tc.get("function", {}).get("name", "")
        try:
            args = json.loads(tc.function.arguments if hasattr(tc, "function") else tc["function"]["arguments"])
        except json.JSONDecodeError:
            args = {}

        tc_id = tc.id if hasattr(tc, "id") else tc.get("id", "")
        meta = get_tool_meta(name)
        result = None
        per_tool_condensed: str | None = None

        if meta and meta.requires_confirm:
            tool_results.append({
                "role": "tool", "tool_call_id": tc_id,
                "content": json.dumps({"blocked": True, "message": "此操作需要用户确认后才能执行"}, ensure_ascii=False)
            })
        else:
            args.setdefault("creator_id", creator_id)
            result = execute_tool(name, args, db)

            # Block layer: deterministic build
            if meta and meta.build_blocks:
                direct_blocks.extend(meta.build_blocks(result))
            elif isinstance(result, dict) and result.get("_render"):
                direct_blocks.extend(result.get("blocks", []))

            # condense: extract key numbers for Layer 2
            if meta and meta.condense:
                condensed = meta.condense(result)
                # Convert dict condense result to text for LLM
                if isinstance(condensed, dict):
                    condensed_text = json.dumps(condensed, ensure_ascii=False, default=str)
                else:
                    condensed_text = str(condensed)
                per_tool_condensed = f"[{name}] {condensed_text}"
                condense_texts.append(per_tool_condensed)

            # tool result: this tool's own condense feeds LLM (not full JSON)
            tool_results.append({
                "role": "tool", "tool_call_id": tc_id,
                "content": per_tool_condensed if per_tool_condensed else "工具已执行。",
            })

        if result is not None:
            tool_cache[name] = result

    return direct_blocks, condense_texts, tool_results, tool_cache


# ═══════════════════════════════════════════════════════════════
# _dedup_chart_blocks — simplified dedup
# ═══════════════════════════════════════════════════════════════

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


# ═══════════════════════════════════════════════════════════════
# _parse_response — simplified: LLM outputs pure text now
# ═══════════════════════════════════════════════════════════════

def _parse_response(raw: str | None) -> dict:
    """解析 LLM 返回的原始文本为 {content, blocks} 结构

    Since Layer 2 outputs pure text (no JSON), this is much simpler:
    - If it looks like valid JSON with content/blocks, parse it (backward compat)
    - Otherwise, treat the entire text as content
    """
    if not raw:
        return {"content": "数据已生成，请查看下方图表/表格中的详细数据。", "blocks": []}

    text = raw.strip()

    # Try JSON parse — for backward compat with models that still output JSON
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict) and ("content" in parsed or "blocks" in parsed):
            return {
                "content": parsed.get("content", ""),
                "blocks": parsed.get("blocks", []),
            }
        if isinstance(parsed, dict):
            # Some other JSON dict — just use as content
            return {"content": text, "blocks": []}
    except json.JSONDecodeError:
        pass

    # Pure text — the common case for Layer 2
    return {"content": text, "blocks": []}


# ═══════════════════════════════════════════════════════════════
# chat() — non-streaming, backward compatible
# ═══════════════════════════════════════════════════════════════

def _parse_dsml_tool_calls(text: str) -> list[dict] | None:
    """从 LLM 文本中解析 DSML 格式的工具调用（DeepSeek 模型有时不用标准 function calling）

    格式示例:
        <｜｜DSML｜｜tool_calls>
        <｜｜DSML｜｜invoke name="render_sales_trend">
        <｜｜DSML｜｜parameter name="product_id" string="false">2</｜｜DSML｜｜parameter>
        </｜｜DSML｜｜invoke>
        </｜｜DSML｜｜tool_calls>
    """
    import re
    if "DSML" not in text:
        return None

    calls = []
    # Find all invoke blocks
    invoke_pattern = re.compile(r'<｜｜DSML｜｜invoke\s+name="([^"]+)">(.*?)</｜｜DSML｜｜invoke>', re.DOTALL)
    param_pattern = re.compile(r'<｜｜DSML｜｜parameter\s+name="([^"]+)"[^>]*>(.*?)</｜｜DSML｜｜parameter>', re.DOTALL)

    for m in invoke_pattern.finditer(text):
        tool_name = m.group(1)
        invoke_body = m.group(2)
        args = {}
        for pm in param_pattern.finditer(invoke_body):
            key = pm.group(1)
            val = pm.group(2).strip()
            # Try to convert to appropriate type
            try:
                args[key] = int(val)
            except ValueError:
                try:
                    args[key] = float(val)
                except ValueError:
                    if val.lower() in ("true", "false"):
                        args[key] = val.lower() == "true"
                    else:
                        args[key] = val
        calls.append({"name": tool_name, "arguments": json.dumps(args, ensure_ascii=False)})

    return calls if calls else None


def chat(messages: list[dict], db: Session, creator_id: int = 0) -> dict:
    """主对话函数 — 两层串联，返回 {"content": ..., "blocks": [...]}"""
    if not client:
        return {
            "content": "AI 服务未配置，请在 .env 中设置 OPENAI_API_KEY。",
            "blocks": [],
        }

    user_msg = messages[-1].get("content", "") if messages else ""
    intent = classify_intent(user_msg)

    full_messages = [{"role": "system", "content": ROUTING_PROMPT}] + messages
    if intent.intent in ("data_query", "chart_only", "action"):
        full_messages.insert(1, {"role": "system", "content": DATA_HINT})

    try:
        # Layer 1: routing — up to 3 rounds of tool calls
        # (e.g. query_products → render_sales_trend needs 2 rounds)
        MAX_L1_ROUNDS = 3
        direct_blocks = []
        condense_texts = []
        tool_cache = {}
        all_tool_calls: list = []  # accumulate every round's tool_calls (P1-4 fix)

        for round_idx in range(MAX_L1_ROUNDS):
            resp = _call_llm_once(full_messages, tool_choice="auto", temperature=0.3)
            msg = resp.choices[0].message

            logger.info(f"[Chat] L1 round={round_idx+1} | model: {resp.model} | finish: {resp.choices[0].finish_reason} | token: {resp.usage}")
            if msg.tool_calls:
                logger.info(f"[Chat] L1 工具: {[tc.function.name for tc in msg.tool_calls]}")
            else:
                logger.info(f"[Chat] L1 直接回答, content长度={len(msg.content or '')}")

            # No tool calls → either retry (round 0 only) or break
            if not msg.tool_calls:
                if round_idx == 0 and intent.intent in ("data_query", "chart_only", "action"):
                    full_messages.append({"role": "system", "content": RETRY_HINT})
                    retry = _call_llm_once(full_messages, tool_choice="auto", temperature=0.3)
                    retry_msg = retry.choices[0].message
                    if retry_msg.tool_calls:
                        msg = retry_msg
                        logger.info(f"[Chat] L1 重试成功, 工具: {[tc.function.name for tc in msg.tool_calls]}")
                    else:
                        logger.info(f"[Chat] L1 重试仍无工具调用")
                        return _parse_response(retry_msg.content)
                else:
                    if round_idx == 0:
                        return _parse_response(msg.content)
                    break  # later rounds with no tool calls = L1 done

            # Process tool calls from this round
            assistant_msg = _build_assistant_msg(msg)
            full_messages.append(assistant_msg)

            round_blocks, round_condense, round_results, round_cache = _process_tool_calls(
                msg.tool_calls, db, creator_id
            )
            full_messages.extend(round_results)

            direct_blocks.extend(round_blocks)
            condense_texts.extend(round_condense)
            tool_cache.update(round_cache)
            all_tool_calls.extend(msg.tool_calls)  # accumulate for downstream use

            logger.info(f"[Chat] L1 round={round_idx+1} 工具执行完毕, blocks={len(round_blocks)}, condense={len(round_condense)}")

            # If LLM called render_* tools, we have chart blocks — no need for more rounds
            has_render = any(
                (tc.function.name if hasattr(tc, "function") else tc.get("function", {}).get("name", "")).startswith("render_")
                for tc in msg.tool_calls
            )
            if has_render:
                logger.info(f"[Chat] L1 render工具已调用, 跳过后续轮次")
                break

        logger.info(f"[Chat] L1 完成, total direct_blocks={len(direct_blocks)}, total condense_texts={len(condense_texts)}")

        # chart_only → skip Layer 2
        if intent.intent == "chart_only":
            content = _template_fallback(all_tool_calls, tool_cache, db)
            return {"content": content, "blocks": _dedup_chart_blocks(direct_blocks)}

        # Layer 2: analysis (1 LLM call, pure text)
        analysis_messages = full_messages.copy()
        analysis_messages.append({"role": "system", "content": ANALYSIS_PROMPT})
        if condense_texts:
            analysis_messages.append({
                "role": "system",
                "content": "数据如下：\n" + "\n".join(condense_texts),
            })
        if direct_blocks:
            analysis_messages.append({"role": "system", "content": ANALYSIS_HINT_RENDER})
        # 注入场景化策略提示（补货 / 供应商）
        for hint in _strategy_hints_for_tools(all_tool_calls):
            analysis_messages.append({"role": "system", "content": hint})

        try:
            resp2 = client.chat.completions.create(
                model=settings.OPENAI_MODEL,
                messages=analysis_messages,
                temperature=0.5,
                max_tokens=1024,
                extra_body={"thinking": {"type": "disabled"}},
            )
            raw_content = resp2.choices[0].message.content
            logger.info(f"[Chat] L2 | token: {resp2.usage} | content长度={len(raw_content or '')}")

            parsed = _parse_response(raw_content)
        except Exception as e:
            logger.error(f"[Chat] L2 异常: {e}", exc_info=True)
            parsed = {"content": "", "blocks": []}

        # Merge direct blocks
        if direct_blocks:
            all_blocks = direct_blocks + parsed.get("blocks", [])
            parsed["blocks"] = _dedup_chart_blocks(all_blocks)

        # Fallback: if LLM analysis empty but we have blocks
        if not parsed.get("content", "").strip() and direct_blocks:
            parsed["content"] = _template_fallback(all_tool_calls, tool_cache, db)

        return parsed

    except Exception as e:
        logger.error(f"[Chat] 异常: {e}", exc_info=True)
        return {"content": f"处理请求时出错，请重试。错误信息：{str(e)}", "blocks": []}


# ═══════════════════════════════════════════════════════════════
# chat_stream() — streaming version
# ═══════════════════════════════════════════════════════════════

def chat_stream(messages: list[dict], db: Session, creator_id: int = 0):
    """流式对话生成器 — 两层串联

    Yields:
        {"type": "blocks", "data": [...]}        — 确定性渲染块（图表/表格）
        {"type": "content_delta", "text": "..."}  — 增量文本
        {"type": "done", "data": {}}              — 结束标记
    """
    if not client:
        yield {"type": "content_delta", "text": "AI 服务未配置。"}
        yield {"type": "done", "data": {}}
        return

    user_msg = messages[-1].get("content", "") if messages else ""
    intent = classify_intent(user_msg)

    full_messages = [{"role": "system", "content": ROUTING_PROMPT}] + messages
    if intent.intent in ("data_query", "chart_only", "action"):
        full_messages.insert(1, {"role": "system", "content": DATA_HINT})

    try:
        # Layer 1: routing (1 LLM call)
        resp = _call_llm_once(full_messages, tool_choice="auto", temperature=0.3)
        msg = resp.choices[0].message

        if not msg.tool_calls:
            if intent.intent in ("data_query", "chart_only", "action"):
                full_messages.append({"role": "system", "content": RETRY_HINT})
                retry = _call_llm_once(full_messages, tool_choice="auto", temperature=0.3)
                retry_msg = retry.choices[0].message
                if retry_msg.tool_calls:
                    yield from _handle_tool_calls_stream(retry_msg, full_messages, db, creator_id, intent)
                    return
                yield {"type": "content_delta", "text": retry_msg.content or ""}
                yield {"type": "done", "data": {}}
                return
            yield {"type": "content_delta", "text": msg.content or ""}
            yield {"type": "done", "data": {}}
            return

        yield from _handle_tool_calls_stream(msg, full_messages, db, creator_id, intent)

    except Exception as e:
        logger.error(f"[ChatStream] 异常: {e}", exc_info=True)
        yield {"type": "content_delta", "text": f"处理请求时出错：{str(e)}"}
        yield {"type": "done", "data": {}}


def _handle_tool_calls_stream(msg, full_messages, db, creator_id, intent: IntentResult):
    """流式处理工具调用 + Layer 2 分析"""
    assistant_msg = _build_assistant_msg(msg)
    full_messages.append(assistant_msg)

    direct_blocks, condense_texts, tool_results, tool_cache = _process_tool_calls(
        msg.tool_calls, db, creator_id
    )
    full_messages.extend(tool_results)

    # Push blocks first (deterministic, before LLM text)
    if direct_blocks:
        yield {"type": "blocks", "data": _dedup_chart_blocks(direct_blocks)}

    # chart_only → skip Layer 2
    if intent.intent == "chart_only":
        fallback = _template_fallback(msg.tool_calls, tool_cache, db)
        yield {"type": "content_delta", "text": fallback}
        yield {"type": "done", "data": {}}
        return

    # Layer 2: analysis (1 LLM call, pure text streaming)
    analysis_messages = full_messages.copy()
    analysis_messages.append({"role": "system", "content": ANALYSIS_PROMPT})
    if condense_texts:
        analysis_messages.append({
            "role": "system",
            "content": "数据如下：\n" + "\n".join(condense_texts),
        })
    if direct_blocks:
        analysis_messages.append({"role": "system", "content": ANALYSIS_HINT_RENDER})
    # 注入场景化策略提示（补货 / 供应商）
    for hint in _strategy_hints_for_tools(msg.tool_calls):
        analysis_messages.append({"role": "system", "content": hint})

    try:
        stream = client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=analysis_messages,
            temperature=0.5,
            max_tokens=1024,
            stream=True,
            extra_body={"thinking": {"type": "disabled"}},
        )

        collected = []
        for chunk in stream:
            delta = chunk.choices[0].delta
            if delta.content:
                collected.append(delta.content)
                yield {"type": "content_delta", "text": delta.content}

        # fallback: LLM analysis empty → rule template
        if not "".join(collected).strip() and direct_blocks:
            fallback = _template_fallback(msg.tool_calls, tool_cache, db)
            yield {"type": "content_delta", "text": fallback}

    except Exception:
        if direct_blocks:
            fallback = _template_fallback(msg.tool_calls, tool_cache, db)
            yield {"type": "content_delta", "text": fallback}

    yield {"type": "done", "data": {}}
