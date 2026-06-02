"""采购管理路由"""
from datetime import date
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional

from app.database import get_db
from app.models.purchase import PurchaseOrder, PurchaseOrderItem, PurchaseInbound
from app.models.inventory import Inventory, InventoryRecord
from app.models.product import Product
from app.schemas.business import PurchaseOrderCreate, PurchaseInboundCreate, PurchaseOrderResponse
from app.routers.auth import get_current_user
from app.models.user import User

router = APIRouter(prefix="/api/purchase", tags=["采购管理"])


def generate_order_no(db: Session) -> str:
    """生成采购单号：PO + 日期 + 序号"""
    today = date.today().strftime("%Y%m%d")
    count = db.query(PurchaseOrder).filter(
        PurchaseOrder.order_no.like(f"PO{today}%")
    ).count()
    return f"PO{today}{count + 1:04d}"


@router.get("/orders")
def list_orders(
    keyword: Optional[str] = Query(None, description="订单号模糊搜索"),
    status: Optional[str] = Query(None, description="状态：draft/pending_approval/approved/completed/cancelled"),
    supplier_id: Optional[int] = Query(None, description="供应商ID精确匹配"),
    amount_min: Optional[float] = Query(None, ge=0, description="金额下限"),
    amount_max: Optional[float] = Query(None, ge=0, description="金额上限"),
    date_from: Optional[str] = Query(None, description="下单日期起始 YYYY-MM-DD"),
    date_to: Optional[str] = Query(None, description="下单日期截止 YYYY-MM-DD"),
    delivery_from: Optional[str] = Query(None, description="预计到货起始 YYYY-MM-DD"),
    delivery_to: Optional[str] = Query(None, description="预计到货截止 YYYY-MM-DD"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    query = db.query(PurchaseOrder)
    if keyword:
        query = query.filter(PurchaseOrder.order_no.ilike(f"%{keyword}%"))
    if status:
        query = query.filter(PurchaseOrder.status == status)
    if supplier_id:
        query = query.filter(PurchaseOrder.supplier_id == supplier_id)
    if amount_min is not None:
        query = query.filter(PurchaseOrder.total_amount >= amount_min)
    if amount_max is not None:
        query = query.filter(PurchaseOrder.total_amount <= amount_max)
    if date_from:
        query = query.filter(PurchaseOrder.order_date >= date_from)
    if date_to:
        query = query.filter(PurchaseOrder.order_date <= date_to)
    if delivery_from:
        query = query.filter(PurchaseOrder.expected_delivery_date >= delivery_from)
    if delivery_to:
        query = query.filter(PurchaseOrder.expected_delivery_date <= delivery_to)
    total = query.count()
    items = query.order_by(PurchaseOrder.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return {"total": total, "page": page, "page_size": page_size, "items": items}


@router.get("/orders/{order_id}")
def get_order(order_id: int, db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    order = db.query(PurchaseOrder).filter(PurchaseOrder.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="采购订单不存在")
    items = db.query(PurchaseOrderItem).filter(PurchaseOrderItem.order_id == order_id).all()
    return {"order": order, "items": items}


@router.post("/orders")
def create_order(req: PurchaseOrderCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    total = sum(item["quantity"] * item["unit_price"] for item in req.items)
    order = PurchaseOrder(
        order_no=generate_order_no(db),
        supplier_id=req.supplier_id,
        status="draft",
        expected_delivery_date=req.expected_delivery_date,
        total_amount=total,
        creator_id=user.id,
        remark=req.remark,
    )
    db.add(order)
    db.flush()

    for item in req.items:
        db.add(PurchaseOrderItem(
            order_id=order.id,
            product_id=item["product_id"],
            quantity=item["quantity"],
            unit_price=item["unit_price"],
            total_price=item["quantity"] * item["unit_price"],
        ))
    db.commit()
    db.refresh(order)
    return order


@router.post("/orders/{order_id}/approve")
def approve_order(order_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    order = db.query(PurchaseOrder).filter(PurchaseOrder.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")
    if order.status != "draft" and order.status != "pending_approval":
        raise HTTPException(status_code=400, detail="当前状态不允许审批")
    order.status = "approved"
    order.approver_id = user.id
    db.commit()
    return {"message": "审批通过"}


@router.delete("/orders/{order_id}")
def delete_order(order_id: int, db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    order = db.query(PurchaseOrder).filter(PurchaseOrder.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")
    db.query(PurchaseOrderItem).filter(PurchaseOrderItem.order_id == order_id).delete()
    db.delete(order)
    db.commit()
    return {"message": "删除成功"}


@router.post("/inbound")
def create_inbound(req: PurchaseInboundCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """采购入库"""
    order = db.query(PurchaseOrder).filter(PurchaseOrder.id == req.order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="采购订单不存在")

    inbound_no = f"IN{date.today().strftime('%Y%m%d')}{db.query(PurchaseInbound).count() + 1:04d}"
    inbound = PurchaseInbound(
        inbound_no=inbound_no,
        order_id=req.order_id,
        warehouse_id=req.warehouse_id,
        operator_id=user.id,
        remark=req.remark,
    )
    db.add(inbound)

    items = db.query(PurchaseOrderItem).filter(PurchaseOrderItem.order_id == req.order_id).all()
    total_in = 0
    for item in items:
        inv = db.query(Inventory).filter(
            Inventory.product_id == item.product_id,
            Inventory.warehouse_id == req.warehouse_id,
        ).first()
        if not inv:
            inv = Inventory(
                product_id=item.product_id,
                warehouse_id=req.warehouse_id,
                quantity=0,
                locked_quantity=0,
                available_quantity=0,
            )
            db.add(inv)
            db.flush()

        qty = item.quantity - item.received_quantity
        if qty <= 0:
            continue
        inv.quantity += qty
        inv.available_quantity = inv.quantity - inv.locked_quantity
        item.received_quantity += qty

        db.add(InventoryRecord(
            product_id=item.product_id,
            warehouse_id=req.warehouse_id,
            change_type="inbound",
            change_quantity=qty,
            before_quantity=inv.quantity - qty,
            after_quantity=inv.quantity,
            ref_type="purchase_inbound",
            ref_id=inbound.id,
            operator_id=user.id,
        ))
        total_in += qty * item.unit_price

    order.received_amount += total_in
    # 检查是否全部收货
    all_received = all(
        item.received_quantity >= item.quantity
        for item in items
    )
    order.status = "completed" if all_received else "partially_received"

    inbound.total_amount = total_in
    db.commit()
    return {"message": "入库成功", "inbound_no": inbound_no}
