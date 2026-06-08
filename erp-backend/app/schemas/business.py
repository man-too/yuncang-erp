"""业务模块 Pydantic schemas"""
from datetime import date, datetime
from typing import Optional, Literal
from pydantic import BaseModel


# ========== 供应商 ==========
class SupplierCreate(BaseModel):
    code: str
    name: str
    contact_person: str = ""
    phone: str = ""
    email: str = ""
    address: str = ""
    tax_id: str = ""
    payment_terms: str = ""
    delivery_lead_time: int = 7
    remark: str = ""


class SupplierUpdate(BaseModel):
    name: Optional[str] = None
    contact_person: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    tax_id: Optional[str] = None
    status: Optional[Literal["active", "inactive", "pending", "blacklisted"]] = None
    payment_terms: Optional[str] = None
    delivery_lead_time: Optional[int] = None
    remark: Optional[str] = None


class SupplierResponse(BaseModel):
    id: int
    code: str
    name: str
    contact_person: str
    phone: str
    email: str
    status: str
    delivery_lead_time: int
    rating: float
    remark: str
    created_at: datetime

    class Config:
        from_attributes = True


# ========== 产品/物料 ==========
class ProductCreate(BaseModel):
    code: str
    name: str
    category_id: int = 0
    specification: str = ""
    unit: str = "个"
    purchase_price: float = 0.0
    sale_price: float = 0.0
    cost_price: float = 0.0
    min_stock: float = 0.0
    max_stock: float = 0.0
    barcode: str = ""
    remark: str = ""


class ProductUpdate(BaseModel):
    name: Optional[str] = None
    category_id: Optional[int] = None
    specification: Optional[str] = None
    unit: Optional[str] = None
    purchase_price: Optional[float] = None
    sale_price: Optional[float] = None
    cost_price: Optional[float] = None
    min_stock: Optional[float] = None
    max_stock: Optional[float] = None
    barcode: Optional[str] = None
    is_active: Optional[bool] = None
    remark: Optional[str] = None


class ProductResponse(BaseModel):
    id: int
    code: str
    name: str
    category_id: int
    specification: str
    unit: str
    purchase_price: float
    sale_price: float
    min_stock: float
    max_stock: float
    is_active: bool
    remark: str

    class Config:
        from_attributes = True


class ProductCategoryCreate(BaseModel):
    name: str
    parent_id: int = 0
    sort_order: int = 0
    remark: str = ""


# ========== 采购 ==========
class OrderItemCreate(BaseModel):
    product_id: int
    quantity: float = 1
    unit_price: float = 0


class PurchaseOrderCreate(BaseModel):
    supplier_id: int
    expected_delivery_date: Optional[date] = None
    remark: str = ""
    items: list[OrderItemCreate]


class PurchaseOrderResponse(BaseModel):
    id: int
    order_no: str
    supplier_id: int
    status: str
    order_date: date
    total_amount: float
    remark: str
    created_at: datetime

    class Config:
        from_attributes = True


class PurchaseInboundCreate(BaseModel):
    order_id: int
    warehouse_id: int
    remark: str = ""


# ========== 客户 ==========
class CustomerCreate(BaseModel):
    code: str
    name: str
    contact_person: str = ""
    phone: str = ""
    email: str = ""
    address: str = ""
    tax_id: str = ""
    credit_limit: float = 0.0
    remark: str = ""


class CustomerUpdate(BaseModel):
    name: Optional[str] = None
    contact_person: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    tax_id: Optional[str] = None
    is_active: Optional[bool] = None
    credit_limit: Optional[float] = None
    remark: Optional[str] = None


class CustomerResponse(BaseModel):
    id: int
    code: str
    name: str
    contact_person: str
    phone: str
    email: str
    is_active: bool
    credit_limit: float

    class Config:
        from_attributes = True


# ========== 销售 ==========
class SaleOrderCreate(BaseModel):
    customer_id: int
    expected_delivery_date: Optional[date] = None
    remark: str = ""
    items: list[OrderItemCreate]


class SaleOrderResponse(BaseModel):
    id: int
    order_no: str
    customer_id: int
    status: str
    order_date: date
    total_amount: float
    remark: str
    created_at: datetime

    class Config:
        from_attributes = True


class SaleOutboundCreate(BaseModel):
    order_id: int
    warehouse_id: int
    remark: str = ""


# ========== 仓库 & 库存 ==========
class WarehouseCreate(BaseModel):
    name: str
    code: str
    address: str = ""
    manager: str = ""
    remark: str = ""


class InventoryResponse(BaseModel):
    id: int
    product_id: int
    warehouse_id: int
    quantity: float
    locked_quantity: float
    available_quantity: float

    class Config:
        from_attributes = True


class InventoryAdjustment(BaseModel):
    product_id: int
    warehouse_id: int
    new_quantity: float
    remark: str = ""


# ========== AI 决策 ==========
class AIQueryRequest(BaseModel):
    query_type: str  # stock_alert, sales_forecast, supplier_recommend
    params: dict = {}


class AIAnalysisResponse(BaseModel):
    id: int
    decision_type: str
    title: str
    summary: str
    confidence: float
    created_at: datetime

    class Config:
        from_attributes = True
