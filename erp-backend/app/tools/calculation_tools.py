"""计算工具 LLM 注册 — ROP / 供应商评分 / 库存 KPI

注册三个纯计算工具为 Function Calling 工具：
- calc_reorder_point: 再订货点计算
- calc_supplier_score: 供应商评分+风险
- calc_inventory_kpi: 库存 KPI
"""

from sqlalchemy.orm import Session

from app.services.calculation_service import calc_reorder_point, calc_inventory_kpi
from app.services.supplier_scoring import calc_supplier_score


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "calc_reorder_point",
            "description": "计算产品的再订货点(ROP)，包含安全库存、日均销量、交期天数。基于近60天销量数据和供应商交期，按ABC分类确定服务水平。当用户询问补货时机、再订货点、安全库存时应首先调用此工具。不指定product_id时计算所有产品的ROP",
            "parameters": {
                "type": "object",
                "properties": {
                    "product_id": {
                        "type": "integer",
                        "description": "产品ID（可选，不指定则计算所有产品）",
                    },
                    "supplier_id": {
                        "type": "integer",
                        "description": "供应商ID（可选，默认取最近采购的供应商）",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calc_supplier_score",
            "description": "计算供应商综合评分，包含质量/交付/价格/服务四维评分和风险惩罚（单源依赖+交付波动）。不传supplier_id则计算全部活跃供应商。当用户询问供应商评分、供应商对比、供应商风险时调用",
            "parameters": {
                "type": "object",
                "properties": {
                    "supplier_id": {
                        "type": "integer",
                        "description": "供应商ID（可选，不传则计算全部）",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calc_inventory_kpi",
            "description": "计算全量库存KPI：周转天数、呆滞SKU数及占比、资金占用。当用户询问库存效率、周转率、呆滞库存、资金占用时调用",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
]


def execute(name: str, args: dict, db: Session) -> dict | None:
    """执行计算工具"""
    if name == "calc_reorder_point":
        product_id = args.get("product_id")
        supplier_id = args.get("supplier_id")
        if product_id:
            return calc_reorder_point(product_id, db, supplier_id)
        # No product_id specified — calculate ROP for all products
        from app.models.product import Product
        products = db.query(Product).filter(Product.is_active == True).all()
        results = []
        for p in products:
            try:
                r = calc_reorder_point(p.id, db, supplier_id)
                results.append(r)
            except Exception:
                pass
        return {"total": len(results), "products": results}

    if name == "calc_supplier_score":
        supplier_id = args.get("supplier_id")
        return calc_supplier_score(supplier_id, db)

    if name == "calc_inventory_kpi":
        return calc_inventory_kpi(db)

    return None