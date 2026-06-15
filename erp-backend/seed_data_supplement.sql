-- ============================================
-- ERP 系统补充种子数据（大量销售+库存数据）
-- 可重复运行，不覆盖已有数据
-- ============================================

-- 1. 补充产品（若不存在）
INSERT IGNORE INTO products (id, code, name, category_id, unit, purchase_price, sale_price, cost_price, min_stock, max_stock)
VALUES (5, 'MAT-003', '塑料粒子', 1, '公斤', 8.5, 12, 7.5, 500, 5000),
       (6, 'MAT-004', '辅料', 1, '个', 2, 3.5, 1.5, 100, 1000);

-- 2. 补充供应商
INSERT IGNORE INTO suppliers (id, code, name, contact_person, phone, status, delivery_lead_time, rating)
VALUES (4, 'SUP-004', '南方电子科技', '陈经理', '13600136001', 'active', 6, 4.0);

-- 3. 补充客户
INSERT IGNORE INTO customers (id, name, contact_person, phone, credit_limit)
VALUES (4, '九州实业', '林总', '13900139004', 300000);

-- 4. 初始化库存表（关键！低库存查询依赖此表）
REPLACE INTO inventories (id, product_id, warehouse_id, quantity, locked_quantity, available_quantity)
VALUES
(1, 1, 1, 8, 0, 8),      -- 钢材A型 库存8 < min_stock=10 → 低库存
(2, 2, 1, 3000, 0, 3000), -- 塑料粒子 正常
(3, 3, 1, 3, 0, 3),       -- 机械臂 库存3 < min_stock=5 → 低库存
(4, 4, 1, 20, 0, 20),     -- 传感器模组 库存20 < min_stock=50 → 低库存
(5, 5, 1, 0, 0, 0),       -- 塑料粒子 库存0 → 严重低库存
(6, 6, 1, 50, 0, 50);     -- 辅料 库存50 < min_stock=100 → 低库存

-- 5. 批量销售订单（1月-6月，让 AI 有数据可分析）
-- 1月
INSERT IGNORE INTO sale_orders (id, order_no, customer_id, status, order_date, total_amount, creator_id) VALUES
(10, 'SO20260105001', 1, 'completed', '2026-01-05', 42500, 1),
(11, 'SO20260115001', 2, 'completed', '2026-01-15', 28000, 1),
(12, 'SO20260125001', 3, 'completed', '2026-01-25', 15600, 1);
INSERT IGNORE INTO sale_order_items (order_id, product_id, quantity, shipped_quantity, unit_price, total_price) VALUES
(10, 1, 5, 5, 4500, 22500), (10, 4, 50, 50, 200, 10000),
(11, 2, 2000, 2000, 12, 24000), (11, 5, 200, 200, 80, 16000),
(12, 6, 300, 300, 5, 1500);

-- 2月
INSERT IGNORE INTO sale_orders (id, order_no, customer_id, status, order_date, total_amount, creator_id) VALUES
(13, 'SO20260203001', 1, 'completed', '2026-02-03', 52000, 1),
(14, 'SO20260214001', 2, 'completed', '2026-02-14', 31000, 1),
(15, 'SO20260220001', 1, 'completed', '2026-02-20', 18000, 1);
INSERT IGNORE INTO sale_order_items (order_id, product_id, quantity, shipped_quantity, unit_price, total_price) VALUES
(13, 1, 6, 6, 4500, 27000), (13, 3, 1, 1, 25000, 25000),
(14, 2, 2500, 2500, 12, 30000), (14, 4, 60, 60, 200, 12000),
(15, 5, 150, 150, 80, 12000), (15, 6, 200, 200, 5, 1000);

-- 3月
INSERT IGNORE INTO sale_orders (id, order_no, customer_id, status, order_date, total_amount, creator_id) VALUES
(16, 'SO20260305001', 1, 'completed', '2026-03-05', 68000, 1),
(17, 'SO20260312001', 3, 'completed', '2026-03-12', 42000, 1),
(18, 'SO20260322001', 2, 'completed', '2026-03-22', 22000, 1);
INSERT IGNORE INTO sale_order_items (order_id, product_id, quantity, shipped_quantity, unit_price, total_price) VALUES
(16, 1, 8, 8, 4500, 36000), (16, 4, 80, 80, 200, 16000),
(17, 2, 3000, 3000, 12, 36000), (17, 5, 100, 100, 80, 8000),
(18, 3, 1, 1, 25000, 25000), (18, 6, 400, 400, 5, 2000);

-- 4月
INSERT IGNORE INTO sale_orders (id, order_no, customer_id, status, order_date, total_amount, creator_id) VALUES
(19, 'SO20260402001', 2, 'completed', '2026-04-02', 55000, 1),
(20, 'SO20260410001', 1, 'completed', '2026-04-10', 35000, 1),
(21, 'SO20260418001', 3, 'completed', '2026-04-18', 28000, 1),
(22, 'SO20260428001', 1, 'completed', '2026-04-28', 19000, 1);
INSERT IGNORE INTO sale_order_items (order_id, product_id, quantity, shipped_quantity, unit_price, total_price) VALUES
(19, 1, 7, 7, 4500, 31500), (19, 3, 1, 1, 25000, 25000), (19, 4, 30, 30, 200, 6000),
(20, 2, 2800, 2800, 12, 33600), (20, 5, 120, 120, 80, 9600),
(21, 4, 100, 100, 200, 20000), (21, 6, 500, 500, 5, 2500),
(22, 1, 3, 3, 4500, 13500), (22, 5, 80, 80, 80, 6400);

-- 5月（已有订单1-3, 再补充）
INSERT IGNORE INTO sale_orders (id, order_no, customer_id, status, order_date, total_amount, creator_id) VALUES
(23, 'SO20260510001', 2, 'approved', '2026-05-10', 46000, 1),
(24, 'SO20260520001', 1, 'approved', '2026-05-20', 32000, 1);
INSERT IGNORE INTO sale_order_items (order_id, product_id, quantity, shipped_quantity, unit_price, total_price) VALUES
(23, 1, 5, 3, 4500, 22500), (23, 4, 60, 30, 200, 12000), (23, 5, 200, 100, 80, 16000),
(24, 2, 3000, 1500, 12, 36000), (24, 6, 350, 150, 5, 1750);

-- 6月（本月已有，再加一些近期数据）
INSERT IGNORE INTO sale_orders (id, order_no, customer_id, status, order_date, total_amount, creator_id) VALUES
(25, 'SO20260601001', 1, 'approved', '2026-06-01', 38000, 1),
(26, 'SO20260602001', 3, 'pending_approval', '2026-06-02', 15000, 1);
INSERT IGNORE INTO sale_order_items (order_id, product_id, quantity, shipped_quantity, unit_price, total_price) VALUES
(25, 1, 4, 0, 4500, 18000), (25, 3, 1, 0, 25000, 25000), (25, 5, 100, 0, 80, 8000),
(26, 4, 50, 0, 200, 10000), (26, 6, 200, 0, 5, 1000);

-- 更新出库数据
UPDATE sale_orders SET shipped_amount = total_amount WHERE status = 'completed' AND shipped_amount = 0;

-- 6. 库存变更记录（更多出入库历史）
INSERT IGNORE INTO inventory_records (id, product_id, warehouse_id, change_type, change_quantity, before_quantity, after_quantity, ref_type, ref_id, operator_id, remark) VALUES
(10, 1, 1, 'outbound', 5, 20, 15, 'sale_outbound', 10, 1, '销售出库'),
(11, 1, 1, 'outbound', 6, 15, 9, 'sale_outbound', 13, 1, '销售出库'),
(12, 1, 1, 'outbound', 8, 9, 1, 'sale_outbound', 16, 1, '销售出库'),
(13, 1, 1, 'inbound', 20, 1, 21, 'purchase_inbound', 2, 1, '补货入库'),
(14, 1, 1, 'outbound', 7, 21, 14, 'sale_outbound', 19, 1, '销售出库'),
(15, 1, 1, 'outbound', 3, 14, 11, 'sale_outbound', 22, 1, '销售出库'),
(16, 2, 1, 'outbound', 2000, 3000, 1000, 'sale_outbound', 11, 1, '销售出库'),
(17, 2, 1, 'inbound', 5000, 1000, 6000, 'purchase_inbound', 1, 1, '补货'),
(18, 2, 1, 'outbound', 2500, 6000, 3500, 'sale_outbound', 14, 1, '销售出库'),
(19, 4, 1, 'outbound', 50, 100, 50, 'sale_outbound', 10, 1, '销售出库');

-- 7. 库存预警更新
INSERT IGNORE INTO inventory_alerts (product_id, warehouse_id, alert_type, current_quantity, threshold_value, level, is_resolved, ai_suggestion) VALUES
(1, 1, 'low_stock', 8, 10, 'high', FALSE, '钢材A型库存8吨，低于安全库存10吨'),
(3, 1, 'low_stock', 3, 5, 'high', FALSE, '机械臂库存3台，建议尽快补货'),
(4, 1, 'low_stock', 20, 50, 'warning', FALSE, '传感器模组库存偏低');

-- 8. AI 决策补充记录
INSERT IGNORE INTO ai_decision_records (id, decision_type, title, input_data, output_data, summary, confidence, related_id, is_applied) VALUES
(10, 'stock_alert', '钢材A型 库存预警', '{"product_id":1,"current_qty":8}', '{"alert_level":"high","suggested_action":"急需补货","suggested_order_qty":20,"confidence":0.82}', '钢材A型库存8吨，低于安全库存，建议补货20吨', 0.82, 1, FALSE),
(11, 'sales_forecast', '钢材A型 销售预测', '{"product_id":1,"period":"2026-01~2026-05"}', '{"forecast_next_30d":35,"trend":"上升","confidence":0.75}', '钢材销量呈上升趋势，预计未来30天需求35吨', 0.75, 1, FALSE);
