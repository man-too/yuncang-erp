"""初始化测试数据脚本 - 在后端启动后运行一次"""
import sys
sys.path.insert(0, '.')

from app.database import SessionLocal, engine, Base
from app.models.user import User
from app.models.supplier import Supplier
from app.models.product import Product, ProductCategory
from app.models.purchase import PurchaseOrder, PurchaseOrderItem
from app.models.sale import Customer
from app.models.inventory import Warehouse, Inventory
from app.utils.auth import hash_password

db = SessionLocal()

# 1. 创建管理员
if not db.query(User).filter(User.username == 'admin').first():
    db.add(User(
        username='admin', email='admin@erp.com',
        hashed_password=hash_password('admin123'),
        display_name='系统管理员', role='admin',
    ))
    db.commit()
    print('管理员账号创建: admin / admin123')

# 2. 仓库
wh1 = Warehouse(name='主仓库', code='WH-001', address='公司总部一楼', city='上海', manager='张三')
wh2 = Warehouse(name='备用仓库', code='WH-002', address='工业园区B区3号', city='苏州', manager='李四')
db.add_all([wh1, wh2]); db.flush()

# 3. 产品分类
cats = [
    ProductCategory(name='原材料', sort_order=1),
    ProductCategory(name='半成品', sort_order=2),
    ProductCategory(name='成品', sort_order=3),
    ProductCategory(name='包装材料', sort_order=4),
]
db.add_all(cats); db.flush()

# 4. 产品
prods = [
    Product(code='MAT-001', name='钢材A型', category_id=1, unit='吨', purchase_price=3500, sale_price=4500, cost_price=3200, min_stock=10, max_stock=100),
    Product(code='MAT-002', name='塑料粒子', category_id=1, unit='公斤', purchase_price=8.5, sale_price=12, cost_price=7.5, min_stock=500, max_stock=5000),
    Product(code='PROD-001', name='机械臂基础版', category_id=3, unit='台', purchase_price=15000, sale_price=25000, cost_price=12000, min_stock=5, max_stock=50),
    Product(code='PROD-002', name='传感器模组', category_id=3, unit='个', purchase_price=120, sale_price=200, cost_price=100, min_stock=50, max_stock=500),
    Product(code='SEMI-001', name='电路板V2', category_id=2, unit='块', purchase_price=45, sale_price=80, cost_price=40, min_stock=100, max_stock=2000),
    Product(code='PKG-001', name='标准包装箱', category_id=4, unit='个', purchase_price=3, sale_price=5, cost_price=2.5, min_stock=200, max_stock=10000),
]
db.add_all(prods); db.flush()

# 5. 供应商
sups = [
    Supplier(code='SUP-001', name='华东钢铁集团', contact_person='王经理', phone='13800138001', status='active', delivery_lead_time=7, rating=4.5),
    Supplier(code='SUP-002', name='华南塑胶有限公司', contact_person='刘经理', phone='13800138002', status='active', delivery_lead_time=5, rating=4.2),
    Supplier(code='SUP-003', name='北方精密仪器厂', contact_person='陈经理', phone='13800138003', status='active', delivery_lead_time=10, rating=4.8),
    Supplier(code='SUP-004', name='西部电子科技', contact_person='赵经理', phone='13800138004', status='pending', delivery_lead_time=14, rating=3.5),
]
db.add_all(sups); db.flush()

# 6. 客户
custs = [
    Customer(code='CUS-001', name='华威集团', contact_person='周采购', phone='13900139001', credit_limit=500000),
    Customer(code='CUS-002', name='创新科技公司', contact_person='吴经理', phone='13900139002', credit_limit=200000),
    Customer(code='CUS-003', name='远洋贸易有限公司', contact_person='郑总', phone='13900139003', credit_limit=1000000),
]
db.add_all(custs); db.flush()

# 7. 库存（每个仓库放一些）
for prod in prods:
    db.add(Inventory(product_id=prod.id, warehouse_id=wh1.id, quantity=float(prod.min_stock * 3), locked_quantity=0))
    db.add(Inventory(product_id=prod.id, warehouse_id=wh2.id, quantity=float(prod.min_stock * 1.5), locked_quantity=0))

# 8. 一个示例采购订单
po = PurchaseOrder(
    order_no='PO202605050001', supplier_id=sups[0].id, status='approved',
    total_amount=3500 * 20 + 15000 * 3, creator_id=1,
)
db.add(po); db.flush()
db.add(PurchaseOrderItem(order_id=po.id, product_id=prods[0].id, quantity=20, unit_price=3500, total_price=70000))
db.add(PurchaseOrderItem(order_id=po.id, product_id=prods[2].id, quantity=3, unit_price=15000, total_price=45000))

db.commit()
for inv in db.query(Inventory).all():
    inv.available_quantity = inv.quantity - inv.locked_quantity
db.commit()

print('测试数据初始化完成！')
print('管理员: admin / admin123')
print('已创建: 4个供应商, 6个产品, 3个客户, 2个仓库, 库存数据, 1个采购订单')
db.close()
