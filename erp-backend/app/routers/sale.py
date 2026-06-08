"""销售管理路由"""
from datetime import date
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional

from app.database import get_db
from app.models.sale import Customer, SaleOrder, SaleOrderItem, SaleOutbound
from app.models.inventory import Inventory, InventoryRecord
from app.schemas.business import CustomerCreate, CustomerUpdate, SaleOrderCreate, SaleOutboundCreate
from app.routers.auth import get_current_user
from app.models.user import User

router = APIRouter(prefix="/api/sales", tags=["销售管理"])


# ========== 客户 ==========
@router.get("/customers")
def list_customers(
    keyword: Optional[str] = Query(None, description="名称/编码模糊搜索"),
    contact: Optional[str] = Query(None, description="联系人模糊搜索"),
    is_active: Optional[bool] = Query(None, description="启用状态"),
    credit_min: Optional[float] = Query(None, ge=0, description="信用额度下限"),
    credit_max: Optional[float] = Query(None, ge=0, description="信用额度上限"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    query = db.query(Customer)
    if keyword:
        query = query.filter(
            Customer.name.ilike(f"%{keyword}%") | Customer.code.ilike(f"%{keyword}%")
        )
    if contact:
        query = query.filter(Customer.contact_person.ilike(f"%{contact}%"))
    if is_active is not None:
        query = query.filter(Customer.is_active == is_active)
    if credit_min is not None:
        query = query.filter(Customer.credit_limit >= credit_min)
    if credit_max is not None:
        query = query.filter(Customer.credit_limit <= credit_max)
    total = query.count()
    items = query.order_by(Customer.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return {"total": total, "page": page, "page_size": page_size, "items": items}


@router.post("/customers")
def create_customer(req: CustomerCreate, db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    if db.query(Customer).filter(Customer.code == req.code).first():
        raise HTTPException(status_code=400, detail="客户编码已存在")
    customer = Customer(**req.model_dump())
    db.add(customer)
    db.commit()
    db.refresh(customer)
    return customer


@router.put("/customers/{customer_id}")
def update_customer(customer_id: int, req: CustomerUpdate, db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="客户不存在")
    for key, val in req.model_dump(exclude_unset=True).items():
        setattr(customer, key, val)
    db.commit()
    db.refresh(customer)
    return customer


@router.delete("/customers/{customer_id}")
def delete_customer(customer_id: int, db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="客户不存在")
    if db.query(SaleOrder).filter(SaleOrder.customer_id == customer_id).first():
        raise HTTPException(status_code=400, detail="该客户下存在销售订单，无法删除")
    db.delete(customer)
    db.commit()
    return {"message": "删除成功"}


# ========== 销售订单 ==========
def generate_so_no(db: Session) -> str:
    """生成销售单号：SO + 日期 + 序号（加锁防竞态）"""
    today = date.today().strftime("%Y%m%d")
    prefix = f"SO{today}"
    last = (
        db.query(SaleOrder.order_no)
        .filter(SaleOrder.order_no.like(f"{prefix}%"))
        .order_by(SaleOrder.id.desc())
        .with_for_update()
        .first()
    )
    seq = int(last[0][len(prefix):]) + 1 if last else 1
    return f"{prefix}{seq:04d}"


@router.get("/orders")
def list_sale_orders(
    keyword: Optional[str] = Query(None, description="订单号模糊搜索"),
    status: Optional[str] = Query(None, description="状态：draft/approved/completed/cancelled"),
    customer_id: Optional[int] = Query(None, description="客户ID精确匹配"),
    amount_min: Optional[float] = Query(None, ge=0, description="金额下限"),
    amount_max: Optional[float] = Query(None, ge=0, description="金额上限"),
    date_from: Optional[str] = Query(None, description="下单日期起始 YYYY-MM-DD"),
    date_to: Optional[str] = Query(None, description="下单日期截止 YYYY-MM-DD"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    query = db.query(SaleOrder)
    if keyword:
        query = query.filter(SaleOrder.order_no.ilike(f"%{keyword}%"))
    if status:
        query = query.filter(SaleOrder.status == status)
    if customer_id:
        query = query.filter(SaleOrder.customer_id == customer_id)
    if amount_min is not None:
        query = query.filter(SaleOrder.total_amount >= amount_min)
    if amount_max is not None:
        query = query.filter(SaleOrder.total_amount <= amount_max)
    if date_from:
        query = query.filter(SaleOrder.order_date >= date_from)
    if date_to:
        query = query.filter(SaleOrder.order_date <= date_to)
    total = query.count()
    items = query.order_by(SaleOrder.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return {"total": total, "page": page, "page_size": page_size, "items": items}


@router.get("/orders/{order_id}")
def get_sale_order(order_id: int, db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    order = db.query(SaleOrder).filter(SaleOrder.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="销售订单不存在")
    items = db.query(SaleOrderItem).filter(SaleOrderItem.order_id == order_id).all()
    return {"order": order, "items": items}


@router.post("/orders")
def create_sale_order(req: SaleOrderCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    total = sum(item["quantity"] * item["unit_price"] for item in req.items)
    order = SaleOrder(
        order_no=generate_so_no(db),
        customer_id=req.customer_id,
        expected_delivery_date=req.expected_delivery_date,
        total_amount=total,
        creator_id=user.id,
        remark=req.remark,
    )
    db.add(order)
    db.flush()

    for item in req.items:
        # 锁定库存
        inv = db.query(Inventory).filter(
            Inventory.product_id == item["product_id"],
            Inventory.warehouse_id == item.get("warehouse_id", 1),
        ).first()
        if inv and inv.available_quantity < item["quantity"]:
            raise HTTPException(status_code=400, detail=f"产品 {item['product_id']} 库存不足")

        db.add(SaleOrderItem(
            order_id=order.id,
            product_id=item["product_id"],
            quantity=item["quantity"],
            unit_price=item["unit_price"],
            total_price=item["quantity"] * item["unit_price"],
        ))

    db.commit()
    db.refresh(order)
    return order


@router.delete("/orders/{order_id}")
def delete_sale_order(order_id: int, db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    order = db.query(SaleOrder).filter(SaleOrder.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")
    if order.status not in ("draft", "cancelled"):
        raise HTTPException(status_code=400, detail="仅草稿或已取消的订单可删除")
    db.query(SaleOrderItem).filter(SaleOrderItem.order_id == order_id).delete()
    db.delete(order)
    db.commit()
    return {"message": "删除成功"}


@router.post("/outbound")
def create_outbound(req: SaleOutboundCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """销售出库"""
    order = db.query(SaleOrder).filter(SaleOrder.id == req.order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="销售订单不存在")

    outbound_no = f"OUT{date.today().strftime('%Y%m%d')}{db.query(SaleOutbound).count() + 1:04d}"
    outbound = SaleOutbound(
        outbound_no=outbound_no,
        order_id=req.order_id,
        warehouse_id=req.warehouse_id,
        operator_id=user.id,
        remark=req.remark,
    )
    db.add(outbound)
    db.flush()

    items = db.query(SaleOrderItem).filter(SaleOrderItem.order_id == req.order_id).all()
    total_out = 0
    for item in items:
        qty = item.quantity - item.shipped_quantity
        if qty <= 0:
            continue

        inv = db.query(Inventory).filter(
            Inventory.product_id == item.product_id,
            Inventory.warehouse_id == req.warehouse_id,
        ).first()
        if not inv or inv.available_quantity < qty:
            raise HTTPException(status_code=400, detail=f"产品 {item.product_id} 库存不足")

        inv.quantity -= qty
        if inv.quantity < 0:
            raise HTTPException(status_code=400, detail=f"产品 {item.product_id} 库存不足，无法出库")
        inv.available_quantity = inv.quantity - inv.locked_quantity
        item.shipped_quantity += qty

        db.add(InventoryRecord(
            product_id=item.product_id,
            warehouse_id=req.warehouse_id,
            change_type="outbound",
            change_quantity=-qty,
            before_quantity=inv.quantity + qty,
            after_quantity=inv.quantity,
            ref_type="sale_outbound",
            ref_id=outbound.id,
            operator_id=user.id,
        ))
        total_out += qty * item.unit_price

    order.shipped_amount += total_out
    all_shipped = all(
        item.shipped_quantity >= item.quantity
        for item in items
    )
    order.status = "completed" if all_shipped else "partially_shipped"
    outbound.total_amount = total_out
    db.commit()
    return {"message": "出库成功", "outbound_no": outbound_no}
