"""产品查询工具"""
from sqlalchemy.orm import Session
from app.models.product import Product

TOOLS = [{
    "type": "function",
    "function": {
        "name": "query_products",
        "description": "查询产品信息，包括价格、库存警戒线等。可按ID精确定位、按分类筛选或关键字搜索",
        "parameters": {
            "type": "object",
            "properties": {
                "product_id": {"type": "integer", "description": "产品ID，可选"},
                "category_id": {"type": "integer", "description": "分类ID，可选"},
                "keyword": {"type": "string", "description": "名称/编码关键词搜索"},
                "is_active": {"type": "boolean", "description": "仅活跃产品"},
                "limit": {"type": "integer", "description": "返回条数上限，默认50"},
            },
            "required": []
        }
    }
}]


def execute(name: str, args: dict, db: Session) -> dict | None:
    if name != "query_products":
        return None

    q = db.query(Product)
    if args.get("product_id"):
        q = q.filter(Product.id == args["product_id"])
    if args.get("category_id"):
        q = q.filter(Product.category_id == args["category_id"])
    if args.get("keyword"):
        kw = f"%{args['keyword']}%"
        q = q.filter((Product.name.like(kw)) | (Product.code.like(kw)))
    if args.get("is_active") is not None:
        q = q.filter(Product.is_active == args["is_active"])

    products = q.limit(args.get("limit", 50)).all()
    return {
        "products": [
            {
                "id": p.id, "code": p.code, "name": p.name,
                "category_id": p.category_id, "unit": p.unit,
                "purchase_price": p.purchase_price, "sale_price": p.sale_price,
                "min_stock": p.min_stock, "max_stock": p.max_stock,
                "is_active": p.is_active,
            }
            for p in products
        ],
        "total": len(products),
    }
