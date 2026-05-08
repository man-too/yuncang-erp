-- ============================================
-- ERP 系统种子数据（补充空表）- 可重复运行版
-- 适用数据库: erp_db
-- ============================================

-- 1. 供应商联系人
INSERT IGNORE INTO supplier_contacts (supplier_id, name, position, phone, email, is_primary) VALUES
(1, '王经理', '销售总监', '13800138001', 'wang@steel.com', TRUE),
(1, '李助理', '客户经理', '13800138002', 'li@steel.com', FALSE),
(2, '张工', '技术主管', '13900139001', 'zhang@chem.com', TRUE),
(3, '刘总', '总经理', '13700137001', 'liu@shunda.com', TRUE),
(4, '陈经理', '业务经理', '13600136001', 'chen@dianzi.com', TRUE);

-- 2. 供应商评估 (由 admin 用户评估)
INSERT IGNORE INTO supplier_evaluations (supplier_id, evaluator_id, quality_score, delivery_score, price_score, service_score, total_score, comment) VALUES
(1, 1, 4.5, 4.0, 3.5, 4.0, 4.0, '质量稳定，价格适中'),
(1, 1, 4.0, 4.5, 3.0, 4.5, 4.0, '交货及时'),
(2, 1, 3.5, 3.0, 4.5, 3.5, 3.6, '价格有优势但交期较长'),
(3, 1, 4.8, 4.5, 3.0, 4.5, 4.2, '品质优良，值得长期合作'),
(4, 1, 4.0, 4.0, 4.0, 4.0, 4.0, '综合表现良好');

-- 3. 采购入库
INSERT IGNORE INTO purchase_inbounds (inbound_no, order_id, warehouse_id, operator_id, inbound_date, total_amount, remark) VALUES
('IN202605050001', 1, 1, 1, '2026-05-05', 115000, '首次入库'),
('IN202605050002', 1, 2, 1, '2026-05-05', 115000, '补充入库');

-- 4. 库存变更记录
INSERT IGNORE INTO inventory_records (id, product_id, warehouse_id, change_type, change_quantity, before_quantity, after_quantity, ref_type, ref_id, operator_id, remark) VALUES
(1, 1, 1, 'inbound', 20, 0, 20, 'purchase_inbound', 1, 1, '采购入库'),
(2, 3, 1, 'inbound', 3, 0, 3, 'purchase_inbound', 1, 1, '采购入库'),
(3, 2, 1, 'inbound', 100, 0, 100, 'purchase_inbound', 1, 1, '期初入库'),
(4, 5, 1, 'adjustment', 300, 0, 300, '', 0, 1, '期初调整'),
(5, 6, 1, 'adjustment', 600, 0, 600, '', 0, 1, '期初调整');

-- 5. 库存预警
INSERT IGNORE INTO inventory_alerts (product_id, warehouse_id, alert_type, current_quantity, threshold_value, level, is_resolved, ai_suggestion) VALUES
(5, 1, 'low_stock', 0, 50, 'critical', FALSE, '建议立即补货，库存已耗尽'),
(6, 1, 'low_stock', 5, 100, 'warning', FALSE, '库存低于安全线，建议采购'),
(4, 1, 'low_stock', 8, 30, 'warning', FALSE, '库存偏低，请关注'),
(2, 1, 'high_stock', 1500, 500, 'warning', TRUE, '库存积压，建议促销'),
(1, 1, 'low_stock', 12, 30, 'warning', TRUE, '已处理');

-- 6. 销售订单 + 明细 + 出库
INSERT IGNORE INTO sale_orders (id, order_no, customer_id, status, order_date, total_amount, creator_id) VALUES
(1, 'SO20260501001', 1, 'completed', '2026-05-01', 85000, 1),
(2, 'SO20260502001', 2, 'approved', '2026-05-02', 32000, 1),
(3, 'SO20260503001', 3, 'draft', '2026-05-03', 12800, 1);

INSERT IGNORE INTO sale_order_items (order_id, product_id, quantity, shipped_quantity, unit_price, total_price) VALUES
(1, 1, 10, 10, 3500, 35000),
(1, 3, 2, 2, 15000, 30000),
(1, 4, 10, 10, 2000, 20000),
(2, 2, 20, 0, 800, 16000),
(2, 5, 50, 0, 320, 16000),
(3, 6, 100, 0, 128, 12800);

INSERT IGNORE INTO sale_outbounds (outbound_no, order_id, warehouse_id, operator_id, outbound_date, total_amount) VALUES
('OUT20260505001', 1, 1, 1, '2026-05-05', 85000);

-- 更新已发货数量
UPDATE sale_orders SET shipped_amount = 85000 WHERE id = 1 AND shipped_amount = 0;

-- 7. AI 决策历史记录
INSERT IGNORE INTO ai_decision_records (id, decision_type, title, input_data, output_data, summary, confidence, related_id, is_applied) VALUES
(1, 'stock_alert', '钢材A3 库存预警分析', '{"product_id":1,"current_qty":12}', '{"alert_level":"warning","suggested_action":"建议补货","suggested_order_qty":30,"confidence":0.85}', '库存偏低，建议补货30件', 0.85, 1, TRUE),
(2, 'stock_alert', '电子元件 库存预警分析', '{"product_id":2,"current_qty":150}', '{"alert_level":"warning","suggested_action":"库存偏高","suggested_order_qty":0,"confidence":0.75}', '库存积压，建议暂缓采购', 0.75, 2, FALSE),
(3, 'sales_forecast', '机械零部件 销售预测', '{"product_id":3}', '{"forecast_next_30d":8,"trend":"上升","seasonal_factor":"Q2旺季","confidence":0.78}', '预测未来30天需求约8件，呈上升趋势', 0.78, 3, FALSE),
(4, 'supplier_recommend', '钢材采购 供应商推荐', '{"product_id":1}', '{"recommendations":[{"supplier_id":3,"score":92},{"supplier_id":1,"score":85}],"confidence":0.82}', '推荐钢材供应商：顺达贸易', 0.82, 1, TRUE);
