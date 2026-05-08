"""供应商管理路由"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional

from app.database import get_db
from app.models.supplier import Supplier, SupplierEvaluation
from app.schemas.business import SupplierCreate, SupplierUpdate, SupplierResponse
from app.routers.auth import get_current_user
from app.models.user import User

router = APIRouter(prefix="/api/suppliers", tags=["供应商管理"])


@router.get("")
def list_suppliers(
    keyword: Optional[str] = Query(None, description="名称/编码模糊搜索"),
    contact: Optional[str] = Query(None, description="联系人模糊搜索"),
    status: Optional[str] = Query(None, description="状态：active/inactive/pending/blacklisted"),
    min_rating: Optional[float] = Query(None, ge=0, le=5, description="最低评分"),
    date_from: Optional[str] = Query(None, description="创建日期起始 YYYY-MM-DD"),
    date_to: Optional[str] = Query(None, description="创建日期截止 YYYY-MM-DD"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    query = db.query(Supplier)
    if keyword:
        query = query.filter(
            Supplier.name.ilike(f"%{keyword}%") | Supplier.code.ilike(f"%{keyword}%")
        )
    if contact:
        query = query.filter(Supplier.contact_person.ilike(f"%{contact}%"))
    if status:
        query = query.filter(Supplier.status == status)
    if min_rating is not None:
        query = query.filter(Supplier.rating >= min_rating)
    if date_from:
        query = query.filter(Supplier.created_at >= date_from)
    if date_to:
        query = query.filter(Supplier.created_at <= f"{date_to} 23:59:59")

    total = query.count()
    items = query.order_by(Supplier.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return {"total": total, "page": page, "page_size": page_size, "items": items}


@router.get("/{supplier_id}")
def get_supplier(supplier_id: int, db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    supplier = db.query(Supplier).filter(Supplier.id == supplier_id).first()
    if not supplier:
        raise HTTPException(status_code=404, detail="供应商不存在")
    return supplier


@router.post("", response_model=SupplierResponse)
def create_supplier(req: SupplierCreate, db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    if db.query(Supplier).filter(Supplier.code == req.code).first():
        raise HTTPException(status_code=400, detail="供应商编码已存在")
    supplier = Supplier(**req.model_dump())
    db.add(supplier)
    db.commit()
    db.refresh(supplier)
    return supplier


@router.put("/{supplier_id}")
def update_supplier(supplier_id: int, req: SupplierUpdate, db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    supplier = db.query(Supplier).filter(Supplier.id == supplier_id).first()
    if not supplier:
        raise HTTPException(status_code=404, detail="供应商不存在")
    for key, val in req.model_dump(exclude_unset=True).items():
        setattr(supplier, key, val)
    db.commit()
    db.refresh(supplier)
    return supplier


@router.delete("/{supplier_id}")
def delete_supplier(supplier_id: int, db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    supplier = db.query(Supplier).filter(Supplier.id == supplier_id).first()
    if not supplier:
        raise HTTPException(status_code=404, detail="供应商不存在")
    db.delete(supplier)
    db.commit()
    return {"message": "删除成功"}
