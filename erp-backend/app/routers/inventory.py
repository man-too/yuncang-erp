"""库存管理路由"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional

from app.database import get_db
from app.models.inventory import Warehouse, Inventory, InventoryRecord, InventoryAlert
from app.models.product import Product
from app.schemas.business import WarehouseCreate, InventoryAdjustment
from app.routers.auth import get_current_user
from app.models.user import User
from app.utils.helpers import escape_ilike

router = APIRouter(prefix="/api/inventory", tags=["库存管理"])


# ========== 仓库 ==========
@router.get("/warehouses")
def list_warehouses(db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    return db.query(Warehouse).all()


@router.post("/warehouses")
def create_warehouse(req: WarehouseCreate, db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    wh = Warehouse(**req.model_dump())
    db.add(wh)
    db.commit()
    db.refresh(wh)
    return wh


@router.delete("/warehouses/{wh_id}")
def delete_warehouse(wh_id: int, db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    wh = db.query(Warehouse).filter(Warehouse.id == wh_id).first()
    if not wh:
        raise HTTPException(status_code=404, detail="仓库不存在")
    db.delete(wh)
    db.commit()
    return {"message": "删除成功"}


# ========== 库存 ==========
@router.get("/stock")
def list_stock(
    keyword: Optional[str] = Query(None, description="产品名称/编码模糊搜索"),
    warehouse_id: Optional[int] = Query(None, description="仓库ID精确匹配"),
    category_id: Optional[int] = Query(None, description="产品分类ID"),
    stock_status: Optional[str] = Query(None, description="库存状态: low_stock/overstock/normal"),
    qty_min: Optional[float] = Query(None, ge=0, description="库存量下限"),
    qty_max: Optional[float] = Query(None, ge=0, description="库存量上限"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    query = db.query(Inventory, Product).join(Product, Inventory.product_id == Product.id)
    if keyword:
        query = query.filter(
            Product.name.ilike(f"%{escape_ilike(keyword)}%") | Product.code.ilike(f"%{escape_ilike(keyword)}%")
        )
    if warehouse_id:
        query = query.filter(Inventory.warehouse_id == warehouse_id)
    if category_id is not None:
        query = query.filter(Product.category_id == category_id)
    if stock_status == "low_stock":
        query = query.filter(Inventory.quantity <= Product.min_stock)
    elif stock_status == "overstock":
        query = query.filter(Inventory.quantity >= Product.max_stock)
    elif stock_status == "normal":
        query = query.filter(
            Inventory.quantity > Product.min_stock,
            Inventory.quantity < Product.max_stock,
        )
    if qty_min is not None:
        query = query.filter(Inventory.quantity >= qty_min)
    if qty_max is not None:
        query = query.filter(Inventory.quantity <= qty_max)

    total = query.count()
    results = query.order_by(Inventory.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    items = []
    for inv, prod in results:
        items.append({
            "id": inv.id,
            "product_id": inv.product_id,
            "product_code": prod.code,
            "product_name": prod.name,
            "category_id": prod.category_id,
            "warehouse_id": inv.warehouse_id,
            "quantity": inv.quantity,
            "locked_quantity": inv.locked_quantity,
            "available_quantity": inv.available_quantity,
            "min_stock": prod.min_stock,
            "max_stock": prod.max_stock,
        })
    return {"total": total, "page": page, "page_size": page_size, "items": items}


@router.delete("/stock/{stock_id}")
def delete_stock(stock_id: int, db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    inv = db.query(Inventory).filter(Inventory.id == stock_id).first()
    if not inv:
        raise HTTPException(status_code=404, detail="库存记录不存在")
    db.delete(inv)
    db.commit()
    return {"message": "删除成功"}


@router.post("/adjust")
def adjust_stock(req: InventoryAdjustment, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """库存盘点调整"""
    inv = db.query(Inventory).filter(
        Inventory.product_id == req.product_id,
        Inventory.warehouse_id == req.warehouse_id,
    ).first()
    if not inv:
        inv = Inventory(
            product_id=req.product_id,
            warehouse_id=req.warehouse_id,
            quantity=0,
            locked_quantity=0,
            available_quantity=0,
        )
        db.add(inv)
        db.flush()

    old_qty = inv.quantity
    diff = req.new_quantity - old_qty
    inv.quantity = req.new_quantity
    inv.available_quantity = inv.quantity - inv.locked_quantity

    db.add(InventoryRecord(
        product_id=req.product_id,
        warehouse_id=req.warehouse_id,
        change_type="adjustment",
        change_quantity=diff,
        before_quantity=old_qty,
        after_quantity=req.new_quantity,
        operator_id=user.id,
        remark=req.remark,
    ))
    db.commit()
    return {"message": "调整成功"}


# ========== 库存记录 ==========
@router.get("/records")
def list_records(
    product_id: Optional[int] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    query = db.query(InventoryRecord)
    if product_id:
        query = query.filter(InventoryRecord.product_id == product_id)
    total = query.count()
    items = query.order_by(InventoryRecord.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return {"total": total, "page": page, "page_size": page_size, "items": items}


# ========== 预警 ==========
@router.get("/alerts")
def list_alerts(
    resolved: Optional[bool] = Query(None),
    keyword: Optional[str] = Query(None, description="产品名称/编码搜索"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    query = db.query(InventoryAlert, Product).join(
        Product, InventoryAlert.product_id == Product.id
    )
    if resolved is not None:
        query = query.filter(InventoryAlert.is_resolved == resolved)
    if keyword:
        query = query.filter(
            Product.name.ilike(f"%{escape_ilike(keyword)}%") | Product.code.ilike(f"%{escape_ilike(keyword)}%")
        )

    total = query.count()
    results = query.order_by(InventoryAlert.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    items = []
    for alert, prod in results:
        items.append({
            "id": alert.id,
            "product_id": alert.product_id,
            "product_name": prod.name,
            "product_code": prod.code,
            "warehouse_id": alert.warehouse_id,
            "alert_type": alert.alert_type,
            "current_quantity": alert.current_quantity,
            "threshold_value": alert.threshold_value,
            "level": alert.level,
            "is_resolved": alert.is_resolved,
            "max_stock": float(prod.max_stock),
            "min_stock": float(prod.min_stock),
            "unit": prod.unit,
        })
    return {"total": total, "page": page, "page_size": page_size, "items": items}


@router.delete("/alerts/{alert_id}")
def delete_alert(alert_id: int, db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    alert = db.query(InventoryAlert).filter(InventoryAlert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="预警记录不存在")
    db.delete(alert)
    db.commit()
    return {"message": "删除成功"}


@router.post("/alerts/{alert_id}/resolve")
def resolve_alert(alert_id: int, db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    alert = db.query(InventoryAlert).filter(InventoryAlert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="预警记录不存在")
    alert.is_resolved = True
    from datetime import datetime, timezone
    alert.resolved_at = datetime.now(timezone.utc)
    db.commit()
    return {"message": "已处理"}


# ========== 热力图 ==========
@router.get("/alerts/heatmap")
def alert_heatmap(
    warehouse_id: Optional[int] = Query(None, description="仓库ID筛选"),
    product_id: Optional[int] = Query(None, description="产品ID筛选"),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """库存热力图数据：实时计算各仓库×产品的库存状态"""
    query = db.query(Inventory, Product).join(Product, Inventory.product_id == Product.id)
    if warehouse_id:
        query = query.filter(Inventory.warehouse_id == warehouse_id)
    if product_id:
        query = query.filter(Inventory.product_id == product_id)

    warehouses = db.query(Warehouse).filter(Warehouse.is_active == True).all()
    wh_map = {w.id: w.name for w in warehouses}

    items = []
    for inv, prod in query.all():
        # alert_level: 0=正常, 0.3=偏高/偏低, 0.6=预警, 1.0=严重
        if prod.max_stock > 0 and prod.min_stock >= 0:
            if inv.quantity <= prod.min_stock:
                alert_level = round(1.0 - (inv.quantity / prod.min_stock if prod.min_stock > 0 else 1.0), 2)
            elif inv.quantity >= prod.max_stock:
                ratio = (inv.quantity - prod.max_stock) / prod.max_stock
                alert_level = min(1.0, round(0.6 + ratio * 0.4, 2))
            else:
                alert_level = 0.0
        else:
            alert_level = 0.0

        items.append({
            "warehouse_id": inv.warehouse_id,
            "warehouse_name": wh_map.get(inv.warehouse_id, f"仓库#{inv.warehouse_id}"),
            "product_id": inv.product_id,
            "product_name": prod.name,
            "product_code": prod.code,
            "quantity": inv.quantity,
            "min_stock": prod.min_stock,
            "max_stock": prod.max_stock,
            "alert_level": max(0.0, alert_level),
            "unit": prod.unit,
            "purchase_price": float(prod.purchase_price),
        })

    return items


# 兼容别名：更语义化的路径
@router.get("/heatmap")
def inventory_heatmap(
    warehouse_id: Optional[int] = Query(None, description="仓库ID筛选"),
    product_id: Optional[int] = Query(None, description="产品ID筛选"),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """库存热力图数据（语义化路径，推荐使用）"""
    # 复用 alert_heatmap 逻辑
    query = db.query(Inventory, Product).join(Product, Inventory.product_id == Product.id)
    if warehouse_id:
        query = query.filter(Inventory.warehouse_id == warehouse_id)
    if product_id:
        query = query.filter(Inventory.product_id == product_id)

    warehouses = db.query(Warehouse).filter(Warehouse.is_active == True).all()
    wh_map = {w.id: w.name for w in warehouses}

    items = []
    for inv, prod in query.all():
        if prod.max_stock > 0 and prod.min_stock >= 0:
            if inv.quantity <= prod.min_stock:
                alert_level = round(1.0 - (inv.quantity / prod.min_stock if prod.min_stock > 0 else 1.0), 2)
            elif inv.quantity >= prod.max_stock:
                ratio = (inv.quantity - prod.max_stock) / prod.max_stock
                alert_level = min(1.0, round(0.6 + ratio * 0.4, 2))
            else:
                alert_level = 0.0
        else:
            alert_level = 0.0

        items.append({
            "warehouse_id": inv.warehouse_id,
            "warehouse_name": wh_map.get(inv.warehouse_id, f"仓库#{inv.warehouse_id}"),
            "product_id": inv.product_id,
            "product_name": prod.name,
            "product_code": prod.code,
            "quantity": inv.quantity,
            "min_stock": prod.min_stock,
            "max_stock": prod.max_stock,
            "alert_level": max(0.0, alert_level),
            "unit": prod.unit,
            "purchase_price": float(prod.purchase_price),
        })

    return items


# ========== 低库存 ==========
@router.get("/low-stock")
def list_low_stock(
    keyword: Optional[str] = Query(None, description="产品名称/编码搜索"),
    warehouse_id: Optional[int] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=200),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """获取低库存产品列表（带产品信息和仓库名）"""
    query = db.query(Inventory, Product, Warehouse).join(
        Product, Inventory.product_id == Product.id
    ).join(
        Warehouse, Inventory.warehouse_id == Warehouse.id
    ).filter(
        Inventory.quantity <= Product.min_stock,
        Product.is_active == True,
    )
    if keyword:
        query = query.filter(
            Product.name.ilike(f"%{escape_ilike(keyword)}%") | Product.code.ilike(f"%{escape_ilike(keyword)}%")
        )
    if warehouse_id:
        query = query.filter(Inventory.warehouse_id == warehouse_id)

    total = query.count()
    results = query.order_by(Inventory.quantity.asc()).offset((page - 1) * page_size).limit(page_size).all()
    items = []
    for inv, prod, wh in results:
        suggested_qty = max(0, prod.max_stock - inv.quantity)
        items.append({
            "id": inv.id,
            "product_id": inv.product_id,
            "product_code": prod.code,
            "product_name": prod.name,
            "specification": prod.specification or "",
            "warehouse_id": inv.warehouse_id,
            "warehouse_name": wh.name,
            "current_qty": float(inv.quantity),
            "min_stock": float(prod.min_stock),
            "max_stock": float(prod.max_stock),
            "unit": prod.unit,
            "suggested_qty": float(suggested_qty),
            "purchase_price": float(prod.purchase_price),
        })
    return {"total": total, "page": page, "page_size": page_size, "items": items}
