-- 供应链ERP系统 数据库初始化脚本 (MySQL)
CREATE DATABASE IF NOT EXISTS erp_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS 'erp_user'@'localhost' IDENTIFIED BY 'erp_password';
GRANT ALL PRIVILEGES ON erp_db.* TO 'erp_user'@'localhost';
FLUSH PRIVILEGES;

USE erp_db;

-- 插入测试数据
INSERT INTO `users` (`username`, `email`, `hashed_password`, `display_name`, `role`, `is_active`)
VALUES ('admin', 'admin@erp.com', '$2b$12$LJ3m4ys3LgX3Yx5Z6p7Q8O9a0b1c2d3e4f5g6h7i8j9k0l1m2n3o4p5q', '系统管理员', 'admin', 1);

INSERT INTO `warehouses` (`name`, `code`, `address`, `city`, `manager`)
VALUES ('主仓库', 'WH-001', '公司总部一楼', '上海', '张三'),
       ('备用仓库', 'WH-002', '工业园区B区3号', '苏州', '李四');

INSERT INTO `product_categories` (`name`, `sort_order`)
VALUES ('原材料', 1), ('半成品', 2), ('成品', 3), ('包装材料', 4);

INSERT INTO `products` (`code`, `name`, `category_id`, `unit`, `purchase_price`, `sale_price`, `cost_price`, `min_stock`, `max_stock`)
VALUES ('MAT-001', '钢材A型', 1, '吨', 3500, 4500, 3200, 10, 100),
       ('MAT-002', '塑料粒子', 1, '公斤', 8.5, 12, 7.5, 500, 5000),
       ('PROD-001', '机械臂基础版', 3, '台', 15000, 25000, 12000, 5, 50),
       ('PROD-002', '传感器模组', 3, '个', 120, 200, 100, 50, 500);

INSERT INTO `suppliers` (`code`, `name`, `contact_person`, `phone`, `status`, `delivery_lead_time`, `rating`)
VALUES ('SUP-001', '华东钢铁集团', '王经理', '13800138001', 'active', 7, 4.5),
       ('SUP-002', '华南塑胶有限公司', '刘经理', '13800138002', 'active', 5, 4.2),
       ('SUP-003', '北方精密仪器厂', '陈经理', '13800138003', 'active', 10, 4.8);

INSERT INTO `customers` (`code`, `name`, `contact_person`, `phone`, `credit_limit`)
VALUES ('CUS-001', '华威集团', '周采购', '13900139001', 500000),
       ('CUS-002', '创新科技公司', '吴经理', '13900139002', 200000),
       ('CUS-003', '远洋贸易有限公司', '郑总', '13900139003', 1000000);
