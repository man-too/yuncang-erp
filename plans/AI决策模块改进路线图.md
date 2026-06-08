# AI 决策模块 — 可执行实施计划

> 当前分支: claude/upbeat-lalande-408935

---

## ✅ 一、本分支已完成

文件: `erp-backend/app/tools/chart_tools.py`

| 改动 | 说明 |
|------|------|
| 热力图 >60 行降级为纯表格 | `_render_inventory_heatmap` 数据量判断 |
| 供应商三级渲染 | `_render_supplier_ranking` 重写（≤15垂直柱/16-50横向+zoom/>50 Top15+表格） |
| Bug: 热力图公式 ratio=1 不连续 | level 公式以 ratio=1 为界分段 |
| Bug: 单月数据预测序列长度 | `len(amounts) >= 3` |
| Bug: 低库存表未过滤已取消订单 | 加 `status != "cancelled"` |
| Bug: 供应商 N+1 查询 | 改为 `in_()` 批量查询 |
| Bug: 雷达图两个维度等价 | `stockout_risk_score` 改为加权计算（严重缺货 3× 权重） |

---

## 二、下一轮：数据基础 + 计算引擎

### 改什么

#### 2.1 `products` 表加字段

| 字段 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `weather_sensitive` | Boolean | False | 是否受天气影响 |
| `weather_type` | JSON | NULL | 影响类型：`["hot"]` / `["rain"]` / `["cold"]` / `["hot","rain"]` 等组合 |

作用：`query_weather` 被调用时，系统反向查 `weather_sensitive=True` 且 `weather_type` 命中天气类型的产品，输出受影响品类清单给 LLM。

> **谁来填：** seed data 按产品分类批量预填（几百个产品，一次性的活），保留后台可编辑。

#### 2.2 新建 `supplier_metrics` 表

新建表（而非在 `supplier_evaluations` 上加字段，因为标准差是跨多次评估的聚合指标，不属于单条评估记录）：

| 字段 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `id` | Integer | auto | PK |
| `supplier_id` | Integer | FK | 供应商 ID |
| `metric_date` | DateTime | now | 统计日期 |
| `delivery_delay_std` | Float | NULL | 近 6 个月交付延迟天数标准差 |
| `on_time_rate` | Float | NULL | 准时交付率（预留，后续扩展） |
| `quality_pass_rate` | Float | NULL | 质检通过率（预留，后续扩展） |

> **更新策略：** 每次新增 `supplier_evaluation` 记录时，触发后台任务重新计算该供应商近 6 个月的 `delivery_delay_std`，写入最新一条 metric 记录。

#### 2.3 新增 4 个纯 Python 函数（工具）

全部放在 `chart_tools.py` 或新建 `calculation_tools.py`，不依赖 LLM。

##### ① `calc_reorder_point`

```python
输入: product_id, supplier_id（可选，默认取最近供应商）
内部数据: 近 60 天销量、supplier.delivery_lead_time
公式: ROP = avg_daily_sales × lead_time + safety_stock
      safety_stock = z × σ_daily × √(lead_time)
      z 值由 ABC 分类决定（默认 95% → 1.65）
输出: { "rop": 175, "avg_daily_sales": 20, "lead_time": 7,
        "safety_stock": 35, "service_level": "95%" }
```

##### ② `calc_supplier_score`

```python
输入: supplier_id 或 批量
计算: 质量(30%) + 交付(25%) + 价格(20%) + 服务(15%) - 风险惩罚(10%)
      风险惩罚 = 单源依赖罚分 + 交付波动罚分
输出: { "total_score": 88, "risk_penalty": -5, "is_single_source": true, "suggested_share": "60%" }
```

##### ③ `query_weather`

```python
输入: city, days=7
API: Open-Meteo (https://api.open-meteo.com/v1/forecast)
     免费，无需 API Key
输出: { "city": "上海", "forecast": [{ "date": "2026-06-09", "temp_high": 32,
        "weather": "晴", "precip_prob": 5 }], "summary": "未来3天高温" }
```

##### ④ `calc_inventory_kpi`

```python
输入: 无（全量计算）
SQL: 按产品组聚合
输出: { "turnover_days": 45.2, "dead_stock_count": 3,
        "dead_stock_pct": 2.1, "capital_occupied": 128000 }
```

### 依赖

```
Phase 1 数据
  ├── products.weather_* ──→ query_weather 反向查询受影响品类
  └── supplier_metrics ────→ calc_supplier_score 风险惩罚输入

Phase 2 工具
  ├── calc_reorder_point ──→ Phase 3a generate_purchase_plan
  ├── calc_supplier_score ──→ Phase 3b audit_purchase_plan
  ├── query_weather ────────→ Phase 3b audit_purchase_plan
  └── calc_inventory_kpi ───→ Phase 3b audit_purchase_plan + Phase 4a 异常简报
```

### 改动文件

| 文件 | 操作 |
|------|------|
| `erp-backend/app/models/product.py` | 加 2 个字段（`weather_sensitive` Boolean, `weather_type` JSON） |
| `erp-backend/app/models/supplier.py` | 🆕 新增 `SupplierMetrics` 模型 |
| `erp-backend/app/models/product_category.py` | 加 1 个字段（`bullwhip_threshold` Float, default=1.5） |
| `erp-backend/app/services/calculation_service.py` | 🆕 新建（ROP/安全库存/库存KPI） |
| `erp-backend/app/services/supplier_scoring.py` | 🆕 新建（供应商评分+SupplierMetrics 更新） |
| `erp-backend/app/tools/weather_tools.py` | 🆕 新建（天气查询） |
| `erp-backend/app/services/chat_service.py` | 在 `ALL_TOOLS` 注册新工具 |
| `erp-frontend/src/api/index.ts` | 前端 API 封装（如果有前端独立调用） |

---

## 三、第三轮：决策 Pipeline

Phase 3 拆为两阶段，降低交付门槛：

### 3a：`generate_purchase_plan`（仅依赖 `calc_reorder_point`）

| 改动 | 文件 | 说明 |
|------|------|------|
| `generate_purchase_plan` 工具 | `chart_tools.py` | 三角联动：ROP→库存缺口→补货量→供应商分配 → 输出采购计划+action blocks |
| SYSTEM_PROMPT 强化 | `chat_service.py` | 要求每个结论附带数字、操作按钮 |

```
Phase 2 calc_reorder_point ──→ generate_purchase_plan 的补货算法
```

### 3b：`audit_purchase_plan`（依赖 `calc_supplier_score` + `query_weather` + `calc_inventory_kpi`）

| 改动 | 文件 | 说明 |
|------|------|------|
| `audit_purchase_plan` 工具 | `chart_tools.py` | 输入{产品+数量+供应商} → 并行调用库存/预测/天气/评分 → 输出风险矩阵表格 |

```
Phase 2 calc_supplier_score ──→ audit_purchase_plan 的供应商维度
Phase 2 query_weather ────────→ audit_purchase_plan 的天气因子
Phase 2 calc_inventory_kpi ───→ audit_purchase_plan 的库存维度
```

---

## 四、第四+第五轮：智能分析

### 4.1 异常简报

新增 `render_exception_report` 工具，自动扫描：
- 库存低于安全线 SKU（排序）
- 超期未到货采购单
- 质量评分环比下降 > 15% 的供应商
- 销量波动 > 2σ 的产品

依赖 Phase 2 的 `calc_inventory_kpi` + 已有的 `PurchaseOrder` 和 `SupplierEvaluation` 数据。

### 4.2 牛鞭效应检测

新增 `detect_bullwhip` 工具，按产品计算：

```python
weekly_sales CV / weekly_purchase CV → ratio
```

阈值从 `product_categories` 表的 `bullwhip_threshold` 字段读取（默认 1.5），不同品类可设不同阈值：
- 快消品（饮料、零食）→ 1.2
- 一般品 → 1.5
- 耐用品（家电）→ 2.0

输出按超标程度分三级：
- `ratio > threshold` → 轻度预警
- `ratio > threshold × 1.5` → 中度预警  
- `ratio > threshold × 2` → 严重预警

### 4.3 ABC-XYZ 分类矩阵

新增 `classify_products` 工具：
- ABC 按近 90 天出库金额排序
- XYZ 按近 90 天销量 CV
- 输出 3×3 策略矩阵

> **新产品降级：** 不足 90 天数据的新品，按实际天数计算，结果标记为「低置信度（仅 X 天）」并在矩阵中灰显，凑够 90 天后自动恢复正常。

### 4.4 Scenario Analysis

在 SYSTEM_PROMPT 中加识别规则 + 独立 Prompt 分支。不新增独立工具。

---

## 五、完整依赖关系

```
                    ┌─────────────────────────────────────┐
                    │  本轮 (Phase 2)                      │
                    │  products.weather_sensitive (JSON)   │
                    │  supplier_metrics (新表)              │
                    │  product_categories.bullwhip_        │
                    │    threshold                         │
                    │  calc_reorder_point                  │
                    │  calc_supplier_score                 │
                    │  query_weather (LLM 工具)            │
                    │  calc_inventory_kpi                  │
                    └──────────┬──────────────────────────┘
                               │
                    ┌──────────┴──────────────────────────┐
                    ▼                                     ▼
    ┌──────────────────────────┐     ┌──────────────────────────┐
    │ 第三轮 (Phase 3a)        │     │ 第三轮 (Phase 3b)        │
    │ generate_purchase_plan   │     │ audit_purchase_plan      │
    │ SYSTEM_PROMPT 强化       │     │ (需 Phase 2 全部工具)     │
    │ (仅需 calc_reorder_point)│     └────────────┬─────────────┘
    └──────────────────────────┘                  │
                                                  ▼
                                   ┌──────────────────────────┐
                                   │ 第四+五轮 (Phase 4)       │
                                   │ 异常简报 (4a)             │
                                   │ 牛鞭效应检测 (4a)          │
                                   │ ABC-XYZ 分类 (4b)         │
                                   │ Scenario Analysis (4b)    │
                                   └──────────────────────────┘
```
