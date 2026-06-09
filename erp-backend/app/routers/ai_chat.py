"""AI 对话路由"""
import json
import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.routers.auth import get_current_user
from app.models.user import User
from app.models.ai_analysis import AIDecisionRecord
from app.schemas.chat import ChatRequest, ChatResponse, ExecuteRequest, ExecuteResult
from app.services.chat_service import chat, build_welcome_context, build_welcome_message
from app.tools import execute_tool

router = APIRouter(prefix="/api/ai", tags=["AI 对话"])

# 快捷操作 → 后端 render 工具映射
QUICK_ACTION_TOOLS = {
    "stock_alert": "render_inventory_heatmap",
    "sales_forecast": "render_sales_trend",
    "supplier_ranking": "render_supplier_ranking",
    "dashboard": "render_comprehensive_diagnosis",
    "purchase_advice": "render_purchase_advice",
    "safety_stock": "render_safety_stock_table",
    "transfer_advice": "render_transfer_advice_table",
}


@router.get("/quick-chart")
def ai_quick_chart(
    type: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """快捷操作直接获取图表 blocks，不经过 LLM"""
    tool_name = QUICK_ACTION_TOOLS.get(type)
    if not tool_name:
        raise HTTPException(status_code=400, detail=f"不支持的快捷操作类型: {type}")

    result = execute_tool(tool_name, {}, db)
    if not result or "error" in result:
        return {"content": "数据查询失败，请稍后重试。", "blocks": []}

    # render_* tools return either {"_render": True, "blocks": [...]} or a single block with _render
    blocks = []
    if isinstance(result, dict):
        if result.get("_render"):
            if "blocks" in result:
                blocks = result["blocks"]
            else:
                # Single chart block (like render_sales_trend)
                block = {k: v for k, v in result.items() if k != "_render"}
                blocks = [block]
        elif result.get("type") in ("chart", "table"):
            blocks = [result]

    # Generate analysis text based on quick action type and data
    content = _generate_quick_analysis(type, blocks)

    return {"content": content, "blocks": blocks}


# 快捷操作默认分析文字模板
_QUICK_ACTION_TITLES = {
    "stock_alert": "库存预警分析",
    "sales_forecast": "销售趋势分析",
    "supplier_ranking": "供应商排名分析",
    "dashboard": "供应链综合诊断",
    "purchase_advice": "采购建议分析",
    "safety_stock": "安全库存分析",
    "transfer_advice": "仓库调拨建议",
}


def _generate_quick_analysis(action_type: str, blocks: list) -> str:
    """根据快捷操作类型和数据生成分析文字"""
    title = _QUICK_ACTION_TITLES.get(action_type, "数据分析")

    # Extract key data from blocks for analysis
    table_rows = []
    for b in blocks:
        if b.get("type") == "table":
            table_rows = b.get("rows", [])
            break

    if action_type == "stock_alert":
        # Try to extract stats from chart data (heatmap values are ratios)
        chart_data_points = []
        for b in blocks:
            if b.get("type") == "chart":
                for s in b.get("data", {}).get("series", []):
                    chart_data_points.extend(s.get("data", []))
        if chart_data_points:
            # Heatmap values: ratio = current_qty / min_stock
            critical = sum(1 for p in chart_data_points if isinstance(p, (list, tuple)) and len(p) >= 3 and p[2] < 0.5)
            warning = sum(1 for p in chart_data_points if isinstance(p, (list, tuple)) and len(p) >= 3 and 0.5 <= p[2] <= 1.0)
            normal = sum(1 for p in chart_data_points if isinstance(p, (list, tuple)) and len(p) >= 3 and p[2] > 1.0)
            total = len(chart_data_points)
            parts = [f"## {title}\n"]
            parts.append(f"当前共监控 **{total}** 个仓库×产品库存项：")
            if critical > 0:
                parts.append(f"- 🔴 **严重不足/缺货**：{critical} 项（库存低于安全线的50%），需立即补货")
            if warning > 0:
                parts.append(f"- 🟡 **库存偏低**：{warning} 项（库存低于安全线），建议安排补货")
            if normal > 0:
                parts.append(f"- 🟢 **库存正常**：{normal} 项")
            parts.append("\n请查看上方热力图了解各仓库×产品的库存分布详情，红色区域需重点关注。")
            return "\n".join(parts)
        if not table_rows:
            return f"## {title}\n\n当前库存状态良好，暂无预警项目。"
        critical = sum(1 for r in table_rows if "缺货" in str(r.get("status", "")) or "严重" in str(r.get("status", "")))
        warning = sum(1 for r in table_rows if "偏低" in str(r.get("status", "")))
        normal = sum(1 for r in table_rows if "正常" in str(r.get("status", "")))
        parts = [f"## {title}\n"]
        parts.append(f"当前共监控 **{len(table_rows)}** 个库存项：")
        if critical > 0:
            parts.append(f"- 🔴 **严重不足/缺货**：{critical} 项，需立即补货")
        if warning > 0:
            parts.append(f"- 🟡 **库存偏低**：{warning} 项，建议安排补货")
        if normal > 0:
            parts.append(f"- 🟢 **库存正常**：{normal} 项")
        parts.append("\n请查看上方热力图了解各仓库×产品的库存分布详情，红色区域需重点关注。")
        return "\n".join(parts)

    elif action_type == "safety_stock":
        if not table_rows:
            return f"## {title}\n\n暂无产品数据。"
        urgent = sum(1 for r in table_rows if "紧急" in str(r.get("status", "")))
        suggest = sum(1 for r in table_rows if "建议" in str(r.get("status", "")))
        safe = sum(1 for r in table_rows if "安全" in str(r.get("status", "")))
        parts = [f"## {title}\n"]
        parts.append(f"共分析 **{len(table_rows)}** 个产品的安全库存和再订货点(ROP)：")
        if urgent > 0:
            parts.append(f"- 🔴 **紧急补货**：{urgent} 项（库存低于安全库存线）")
        if suggest > 0:
            parts.append(f"- 🟡 **建议补货**：{suggest} 项（库存低于再订货点）")
        if safe > 0:
            parts.append(f"- 🟢 **库存安全**：{safe} 项")
        parts.append("\n建议优先处理紧急补货项目，避免断货风险。")
        return "\n".join(parts)

    elif action_type == "transfer_advice":
        if not table_rows or any("暂无" in str(r.get("msg", "")) or "均衡" in str(r.get("msg", "")) for r in table_rows):
            return f"## {title}\n\n当前各仓库库存分布均衡，暂无调拨需求。"
        parts = [f"## {title}\n"]
        parts.append(f"检测到 **{len(table_rows)}** 项调拨建议，可从富余仓库向短缺仓库调拨以平衡库存：")
        for r in table_rows[:5]:
            parts.append(f"- {r.get('product_name', '')}：从{r.get('from_warehouse', '')}调拨{r.get('transfer_qty', 0)}件到{r.get('to_warehouse', '')}")
        if len(table_rows) > 5:
            parts.append(f"\n...还有 {len(table_rows) - 5} 项调拨建议，详见上方表格。")
        return "\n".join(parts)

    elif action_type == "sales_forecast":
        return f"## {title}\n\n上方图表展示了近6个月的实际销量及AI预测趋势。请关注：\n- 上升趋势的产品可适当增加库存\n- 下降趋势的产品需控制采购量，避免积压\n- 预测数据基于历史销量，仅供参考"

    elif action_type == "supplier_ranking":
        # Try to extract ranking data from chart series
        supplier_names = []
        for b in blocks:
            if b.get("type") == "chart":
                # Radar chart: indicator has names; Bar chart: xAxis has names
                data = b.get("data", {})
                # Try xAxis categories (bar chart)
                x_data = data.get("xAxis", {})
                if isinstance(x_data, dict):
                    categories = x_data.get("data", [])
                    supplier_names = [c for c in categories if isinstance(c, str) and c]
                elif isinstance(x_data, list):
                    supplier_names = [c for c in x_data if isinstance(c, str) and c]
                # Try indicator (radar chart)
                if not supplier_names:
                    indicators = data.get("radar", {}).get("indicator", []) if isinstance(data.get("radar"), dict) else []
                    supplier_names = [ind.get("name", "") for ind in indicators if isinstance(ind, dict) and ind.get("name")]
        if supplier_names:
            parts = [f"## {title}\n"]
            parts.append(f"共评估 **{len(supplier_names)}** 家活跃供应商：")
            for i, name in enumerate(supplier_names[:5], 1):
                parts.append(f"{i}. **{name}**")
            if len(supplier_names) > 5:
                parts.append(f"\n...共 {len(supplier_names)} 家，详见上方排名图表。")
            parts.append("\n建议优先与综合评分高的供应商合作，同时关注交付率和质量评分。")
            return "\n".join(parts)
        if not table_rows:
            return f"## {title}\n\n暂无供应商评分数据。"
        parts = [f"## {title}\n"]
        for i, r in enumerate(table_rows[:5], 1):
            name = r.get("supplier_name", "")
            score = r.get("total_score", 0)
            parts.append(f"{i}. **{name}** — 综合评分 {score}")
        parts.append("\n建议优先与综合评分高的供应商合作，同时关注交付率和质量评分。")
        return "\n".join(parts)

    elif action_type == "purchase_advice":
        if not table_rows or any("暂无" in str(r.get("msg", "")) for r in table_rows):
            return f"## {title}\n\n当前库存充足，暂无紧急采购需求。"
        parts = [f"## {title}\n"]
        parts.append(f"共 **{len(table_rows)}** 项采购建议：")
        for r in table_rows[:5]:
            parts.append(f"- {r.get('product_name', '')}：建议采购 {r.get('suggested_qty', r.get('suggested_reorder_qty', 0))} 件")
        if len(table_rows) > 5:
            parts.append(f"\n...共 {len(table_rows)} 项，详见上方表格。")
        return "\n".join(parts)

    elif action_type == "dashboard":
        return f"## {title}\n\n上方图表展示了供应链各环节的综合诊断结果，包括库存健康度、销售趋势、供应商表现等。请重点关注标红的风险项。"

    else:
        return f"## {title}\n\n数据已加载，请查看上方图表。"


@router.post("/chat", response_model=ChatResponse)
def ai_chat(
    req: ChatRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    conversation_id = req.conversation_id or uuid.uuid4().hex[:12]

    if not req.messages:
        context = build_welcome_context(db)
        result = build_welcome_message(context)
        result["conversation_id"] = conversation_id
        return result

    messages = [{"role": m.role, "content": m.content} for m in req.messages]
    result = chat(messages, db, creator_id=user.id)
    result["conversation_id"] = conversation_id
    return result


@router.post("/execute", response_model=ExecuteResult)
def ai_execute(
    req: ExecuteRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if req.action not in ("create_purchase_order", "create_stock_transfer"):
        raise HTTPException(status_code=400, detail=f"不支持的操作: {req.action}")

    args = {**req.params, "creator_id": user.id}
    result = execute_tool(req.action, args, db)

    if "error" in result:
        return ExecuteResult(success=False, message=result["error"])

    related_id = result.get("order_id") or 0
    link = f"/purchase?order_id={related_id}" if req.action == "create_purchase_order" and related_id else None

    record = AIDecisionRecord(
        decision_type="chat_decision",
        title=f"对话决策 - {req.action}",
        input_data=json.dumps({"action": req.action, "params": req.params}, ensure_ascii=False),
        output_data=json.dumps(result, ensure_ascii=False, default=str),
        summary=result.get("message", "执行成功"),
        confidence=1.0,
        related_id=related_id,
        is_applied=True,
    )
    db.add(record)
    db.commit()

    return ExecuteResult(
        success=True,
        message=result.get("message", "操作已执行"),
        related_id=related_id,
        link=link,
    )


# ── Phase 3 新增端点 ──────────────────────────────────────────────────

@router.post("/inventory-kpi")
def ai_inventory_kpi(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """库存KPI：周转天数、呆滞SKU数、资金占用"""
    return execute_tool("calc_inventory_kpi", {}, db)


@router.post("/suggested-qty")
def ai_suggested_qty(
    product_id: int,
    supplier_id: int | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """ROP建议采购量（单个产品）"""
    return execute_tool("calc_reorder_point", {"product_id": product_id, "supplier_id": supplier_id}, db)


@router.post("/batch-rop")
def ai_batch_rop(
    data: dict,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """批量计算 ROP（多个产品一次性）"""
    from app.services.calculation_service import batch_calc_reorder_point
    product_ids = data.get("product_ids", [])
    if not product_ids:
        return {}
    return batch_calc_reorder_point(product_ids, db)


@router.post("/supplier-score")
def ai_supplier_score(
    data: dict | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """供应商综合评分+风险惩罚+建议份额"""
    from app.services.supplier_scoring import calc_supplier_score
    supplier_ids = (data or {}).get("supplier_ids") if data else None
    if supplier_ids:
        results = []
        for sid in supplier_ids:
            try:
                results.append(calc_supplier_score(sid, db))
            except Exception:
                continue
        results.sort(key=lambda x: x.get("total_score", 0), reverse=True)
        return {"suppliers": results}
    return {"suppliers": calc_supplier_score(None, db)}


@router.get("/weather")
def ai_weather(
    city: str = "上海",
    days: int = 7,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """天气查询"""
    return execute_tool("query_weather", {"city": city, "days": days}, db)


@router.post("/audit-plan")
def ai_audit_plan(
    data: dict,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """采购计划风险审核"""
    items = data.get("items", [])
    return execute_tool("audit_purchase_plan", {"items": items}, db)
