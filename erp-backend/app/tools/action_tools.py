"""可执行操作工具（需用户确认后调用）"""
from datetime import date, datetime
from sqlalchemy.orm import Session
from app.models.purchase import PurchaseOrder, PurchaseOrderItem
from app.models.inventory import Inventory, InventoryRecord
from app.models.product import Product


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "create_purchase_order",
            "description": "创建采购订单。仅在用户明确确认后由 /api/ai/execute 端点调用",
            "parameters": {
                "type": "object",
                "properties": {
                    "supplier_id": {"type": "integer", "description": "供应商ID"},
                    "items": {
                        "type": "array", "items": {
                            "type": "object",
                            "properties": {
                                "product_id": {"type": "integer"},
                                "quantity": {"type": "number"},
                                "unit_price": {"type": "number"},
                            },
                            "required": ["product_id", "quantity", "unit_price"]
                        }
                    },
                    "expected_delivery_date": {"type": "string", "description": "期望交期 YYYY-MM-DD"},
                    "remark": {"type": "string", "description": "备注"},
                },
                "required": ["supplier_id", "items"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_stock_transfer",
            "description": "创建库存调拨单。仅在用户明确确认后调用",
            "parameters": {
                "type": "object",
                "properties": {
                    "product_id": {"type": "integer", "description": "产品ID"},
                    "from_warehouse_id": {"type": "integer", "description": "调出仓库ID"},
                    "to_warehouse_id": {"type": "integer", "description": "调入仓库ID"},
                    "quantity": {"type": "number", "description": "调拨数量"},
                    "remark": {"type": "string", "description": "备注"},
                },
                "required": ["product_id", "from_warehouse_id", "to_warehouse_id", "quantity"]
            }
        }
    },
]


def execute(name: str, args: dict, db: Session) -> dict | None:
    if name == "create_purchase_order":
        return _create_purchase_order(args, db)
    if name == "create_stock_transfer":
        return _create_stock_transfer(args, db)
    return None


def _generate_order_no(db: Session, prefix: str) -> str:
    today = date.today().strftime("%Y%m%d")
    count = db.query(PurchaseOrder).filter(
        PurchaseOrder.order_no.like(f"{prefix}-{today}-%")
    ).count()
    return f"{prefix}-{today}-{count + 1:04d}"


def _create_purchase_order(args: dict, db: Session) -> dict:
    creator_id = args.get("creator_id", 0)
    order_no = _generate_order_no(db, "PO")

    total = 0.0
    for item in args["items"]:
        total += item["quantity"] * item["unit_price"]

    expected = None
    if args.get("expected_delivery_date"):
        try:
            expected = datetime.strptime(args["expected_delivery_date"], "%Y-%m-%d").date()
        except ValueError:
            pass

    po = PurchaseOrder(
        order_no=order_no,
        supplier_id=args["supplier_id"],
        status="draft",
        order_date=date.today(),
        expected_delivery_date=expected,
        total_amount=total,
        creator_id=creator_id,
        remark=args.get("remark", ""),
    )
    db.add(po)
    db.flush()

    for item in args["items"]:
        poi = PurchaseOrderItem(
            order_id=po.id,
            product_id=item["product_id"],
            quantity=item["quantity"],
            unit_price=item["unit_price"],
            total_price=item["quantity"] * item["unit_price"],
        )
        db.add(poi)

    db.commit()
    db.refresh(po)

    return {
        "order_id": po.id,
        "order_no": po.order_no,
        "total_amount": float(po.total_amount),
        "item_count": len(args["items"]),
        "message": f"采购订单 {po.order_no} 已生成，金额 ¥{po.total_amount:,.2f}，等待审批",
    }


def _create_stock_transfer(args: dict, db: Session) -> dict:
    product_id = args["product_id"]
    qty = float(args["quantity"])
    operator_id = args.get("creator_id", 0)

    # Deduct from source
    src_inv = db.query(Inventory).filter(
        Inventory.product_id == product_id,
        Inventory.warehouse_id == args["from_warehouse_id"],
    ).first()
    if not src_inv or src_inv.quantity < qty:
        return {"error": f"调出仓库库存不足（当前: {src_inv.quantity if src_inv else 0}，需调拨: {qty}）"}

    src_before = float(src_inv.quantity)
    src_inv.quantity -= qty
    src_inv.available_quantity = max(0, float(src_inv.available_quantity) - qty)

    # Add to target
    tgt_inv = db.query(Inventory).filter(
        Inventory.product_id == product_id,
        Inventory.warehouse_id == args["to_warehouse_id"],
    ).first()
    if not tgt_inv:
        tgt_inv = Inventory(
            product_id=product_id,
            warehouse_id=args["to_warehouse_id"],
            quantity=0,
            locked_quantity=0,
            available_quantity=0,
        )
        db.add(tgt_inv)
        db.flush()

    tgt_before = float(tgt_inv.quantity)
    tgt_inv.quantity += qty
    tgt_inv.available_quantity = float(tgt_inv.available_quantity) + qty

    # Records
    db.add(InventoryRecord(
        product_id=product_id, warehouse_id=args["from_warehouse_id"],
        change_type="transfer_out", change_quantity=-qty,
        before_quantity=src_before, after_quantity=float(src_inv.quantity),
        ref_type="stock_transfer", operator_id=operator_id,
        remark=args.get("remark", ""),
    ))
    db.add(InventoryRecord(
        product_id=product_id, warehouse_id=args["to_warehouse_id"],
        change_type="transfer_in", change_quantity=qty,
        before_quantity=tgt_before, after_quantity=float(tgt_inv.quantity),
        ref_type="stock_transfer", operator_id=operator_id,
        remark=args.get("remark", ""),
    ))

    db.commit()

    return {
        "message": f"已从仓库#{args['from_warehouse_id']}调拨 {qty} 件到仓库#{args['to_warehouse_id']}",
    }
