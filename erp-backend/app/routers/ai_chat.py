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
    "safety_stock": "render_inventory_heatmap",
    "transfer_advice": "render_inventory_heatmap",  # 调拨基于库存热力图
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
        return {"blocks": []}

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

    return {"blocks": blocks}


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
    """ROP建议采购量"""
    return execute_tool("calc_reorder_point", {"product_id": product_id, "supplier_id": supplier_id}, db)


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
