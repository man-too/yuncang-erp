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
