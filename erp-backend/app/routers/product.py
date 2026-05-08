"""产品/物料管理路由"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional

from app.database import get_db
from app.models.product import Product, ProductCategory
from app.schemas.business import ProductCreate, ProductUpdate, ProductResponse, ProductCategoryCreate
from app.routers.auth import get_current_user
from app.models.user import User

router = APIRouter(prefix="/api/products", tags=["产品管理"])


@router.get("")
def list_products(
    keyword: Optional[str] = Query(None, description="名称/编码/规格模糊搜索"),
    category_id: Optional[int] = Query(None, description="分类ID精确匹配"),
    is_active: Optional[bool] = Query(None, description="启用状态"),
    price_min: Optional[float] = Query(None, ge=0, description="采购价下限"),
    price_max: Optional[float] = Query(None, ge=0, description="采购价上限"),
    sale_price_min: Optional[float] = Query(None, ge=0, description="销售价下限"),
    sale_price_max: Optional[float] = Query(None, ge=0, description="销售价上限"),
    unit: Optional[str] = Query(None, description="单位精确匹配"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    query = db.query(Product)
    if keyword:
        query = query.filter(
            Product.name.ilike(f"%{keyword}%")
            | Product.code.ilike(f"%{keyword}%")
            | Product.specification.ilike(f"%{keyword}%")
        )
    if category_id is not None:
        query = query.filter(Product.category_id == category_id)
    if is_active is not None:
        query = query.filter(Product.is_active == is_active)
    if price_min is not None:
        query = query.filter(Product.purchase_price >= price_min)
    if price_max is not None:
        query = query.filter(Product.purchase_price <= price_max)
    if sale_price_min is not None:
        query = query.filter(Product.sale_price >= sale_price_min)
    if sale_price_max is not None:
        query = query.filter(Product.sale_price <= sale_price_max)
    if unit:
        query = query.filter(Product.unit == unit)
    total = query.count()
    items = query.order_by(Product.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return {"total": total, "page": page, "page_size": page_size, "items": items}


@router.get("/{product_id}")
def get_product(product_id: int, db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="产品不存在")
    return product


@router.post("")
def create_product(req: ProductCreate, db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    if db.query(Product).filter(Product.code == req.code).first():
        raise HTTPException(status_code=400, detail="产品编码已存在")
    product = Product(**req.model_dump())
    db.add(product)
    db.commit()
    db.refresh(product)
    return product


@router.put("/{product_id}")
def update_product(product_id: int, req: ProductUpdate, db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="产品不存在")
    for key, val in req.model_dump(exclude_unset=True).items():
        setattr(product, key, val)
    db.commit()
    db.refresh(product)
    return product


@router.delete("/{product_id}")
def delete_product(product_id: int, db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="产品不存在")
    db.delete(product)
    db.commit()
    return {"message": "删除成功"}


# ========== 产品分类 ==========
@router.get("/categories/list")
def list_categories(db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    return db.query(ProductCategory).order_by(ProductCategory.sort_order).all()


@router.post("/categories")
def create_category(req: ProductCategoryCreate, db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    cat = ProductCategory(**req.model_dump())
    db.add(cat)
    db.commit()
    db.refresh(cat)
    return cat
