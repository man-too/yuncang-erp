-- Additional sale order items for products 2-6 to provide enough data points for charts
-- Each product gets 8-10 data points spread across April 6 - May 3, 2026

-- Product 2 (塑料粒子, unit_price=800) - 9 data points
INSERT IGNORE INTO sale_order_items (order_id, product_id, quantity, shipped_quantity, unit_price, total_price) VALUES
(4,  2, 25, 25, 800, 20000),
(7,  2, 20, 20, 800, 16000),
(10, 2, 18, 18, 800, 14400),
(13, 2, 30, 30, 800, 24000),
(16, 2, 22, 22, 800, 17600),
(19, 2, 16, 16, 800, 12800),
(22, 2, 28, 28, 800, 22400),
(25, 2, 20, 20, 800, 16000),
(1,  2, 24, 24, 800, 19200);

-- Product 3 (机械臂基础版, unit_price=15000) - 9 data points
INSERT IGNORE INTO sale_order_items (order_id, product_id, quantity, shipped_quantity, unit_price, total_price) VALUES
(5,  3, 2, 2, 15000, 30000),
(8,  3, 1, 1, 15000, 15000),
(11, 3, 3, 3, 15000, 45000),
(14, 3, 1, 1, 15000, 15000),
(17, 3, 2, 2, 15000, 30000),
(20, 3, 1, 1, 15000, 15000),
(23, 3, 2, 2, 15000, 30000),
(26, 3, 1, 1, 15000, 15000),
(2,  3, 3, 3, 15000, 45000);

-- Product 4 (传感器模组, unit_price=2000) - 10 data points
INSERT IGNORE INTO sale_order_items (order_id, product_id, quantity, shipped_quantity, unit_price, total_price) VALUES
(4,  4, 12, 12, 2000, 24000),
(6,  4, 15, 15, 2000, 30000),
(9,  4, 10, 10, 2000, 20000),
(12, 4, 18, 18, 2000, 36000),
(15, 4, 14, 14, 2000, 28000),
(18, 4, 16, 16, 2000, 32000),
(21, 4, 12, 12, 2000, 24000),
(24, 4, 20, 20, 2000, 40000),
(27, 4, 10, 10, 2000, 20000),
(1,  4, 15, 15, 2000, 30000);

-- Product 5 (电路板V2, unit_price=320) - 9 data points
INSERT IGNORE INTO sale_order_items (order_id, product_id, quantity, shipped_quantity, unit_price, total_price) VALUES
(5,  5, 60, 60, 320, 19200),
(7,  5, 80, 80, 320, 25600),
(10, 5, 50, 50, 320, 16000),
(13, 5, 90, 90, 320, 28800),
(16, 5, 70, 70, 320, 22400),
(19, 5, 55, 55, 320, 17600),
(22, 5, 85, 85, 320, 27200),
(25, 5, 65, 65, 320, 20800),
(2,  5, 75, 75, 320, 24000);

-- Product 6 (包装材料, unit_price=128) - 9 data points
INSERT IGNORE INTO sale_order_items (order_id, product_id, quantity, shipped_quantity, unit_price, total_price) VALUES
(6,  6, 150, 150, 128, 19200),
(9,  6, 120, 120, 128, 15360),
(12, 6, 180, 180, 128, 23040),
(15, 6, 100, 100, 128, 12800),
(18, 6, 160, 160, 128, 20480),
(21, 6, 140, 140, 128, 17920),
(24, 6, 200, 200, 128, 25600),
(27, 6, 130, 130, 128, 16640),
(3,  6, 170, 170, 128, 21760);
