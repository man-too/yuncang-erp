# ERP 系统

## 技术栈

| 层 | 技术 |
|---|---|
| 前端框架 | Vue 3 (Composition API, `<script setup lang="ts">`) |
| 状态管理 | Pinia |
| 路由 | Vue Router 4 (createWebHistory) |
| UI 组件库 | Element Plus |
| 图表面板 | ECharts 5 + vue-echarts 6 |
| HTTP 客户端 | Axios |
| 构建工具 | Vite 5 |
| 后端框架 | FastAPI (Python) |
| 数据库 ORM | SQLAlchemy 2.0 |
| 数据库 | MySQL 8.x (PyMySQL) |
| 迁移工具 | Alembic（已装未用，使用 create_all 自动建表） |
| 认证 | JWT (python-jose) + bcrypt (passlib) |
| AI 集成 | OpenAI Python SDK (GPT-4) |
| 任务队列 | Celery + Redis |
| 数据分析 | Pandas + NumPy |

## 项目结构

```
erp-system/
├── erp-frontend/          # Vue 3 前端
│   └── src/
│       ├── api/           # Axios API 封装
│       │   └── index.ts   # 所有 API 方法
│       ├── layouts/       # 布局组件
│       ├── router/        # Vue Router 配置
│       ├── stores/        # Pinia 状态管理
│       └── views/         # 页面组件
│           └── ai/        # AI 智能决策子组件
├── erp-backend/           # FastAPI 后端
│   └── app/
│       ├── models/        # SQLAlchemy 模型 (18张表)
│       ├── routers/       # FastAPI 路由
│       ├── schemas/       # Pydantic 请求/响应模型
│       ├── services/      # 业务逻辑 (AI 服务)
│       └── utils/         # 工具函数
```

## 数据库表 (18张)

| 表名 | 说明 | 状态 |
|------|------|------|
| users | 用户 | 有种子数据 |
| suppliers | 供应商 | 有种子数据 |
| supplier_contacts | 供应商联系人 | 有种子数据 |
| supplier_evaluations | 供应商评估 | 有种子数据 |
| products | 产品 | 有种子数据 |
| product_categories | 产品分类 | 有种子数据 |
| purchase_orders | 采购订单 | 有种子数据 |
| purchase_order_items | 采购订单明细 | 有种子数据 |
| purchase_inbounds | 采购入库 | 有种子数据 |
| warehouses | 仓库 | 有种子数据 |
| inventories | 库存 | 有种子数据 |
| inventory_records | 库存变更记录 | 有种子数据 |
| inventory_alerts | 库存预警 | 有种子数据 |
| customers | 客户 | 有种子数据 |
| sale_orders | 销售订单 | 有种子数据 |
| sale_order_items | 销售订单明细 | 有种子数据 |
| sale_outbounds | 销售出库 | 有种子数据 |
| ai_decision_records | AI 决策记录 | 有种子数据 |

## 启动方式

### 后端
```bash
cd erp-backend
# 安装依赖
pip install -r requirements.txt
# 配置 .env（参考 .env.example）
# 初始化数据库
python seed_data.py  # 或执行 seed_data.sql
# 启动
python run.py  # 默认 http://localhost:8000
```

### 前端
```bash
cd erp-frontend
npm install
npm run dev  # 默认 http://localhost:3000
```

## 数据库初始化
```bash
# 导入种子数据（已存在表将报错，可忽略）
mysql -u erp_user -p erp_db < erp-backend/init_db.sql
mysql -u erp_user -p erp_db < erp-backend/seed_data.sql
```

## API 路由

| 前缀 | 模块 |
|------|------|
| /api/auth | 认证 |
| /api/suppliers | 供应商管理 |
| /api/products | 产品管理 |
| /api/purchase | 采购管理 |
| /api/inventory | 库存管理 |
| /api/sales | 销售管理 |
| /api/ai | AI 智能决策 |

## AI 智能决策模块

页面位于 `/ai-decision`，包含三个可折叠子模块：

1. **库存预警** - ECharts 热力图展示各仓库×产品库存状态，AI 分析输出
2. **销售预测** - 历史销量折线图 + 预测折线图，AI 分析
3. **供应商分析** - 可切换指标（质量/交付/价格/服务/综合评分/交付率/收货率），AI 排名表

AI 服务需要配置 OPENAI_API_KEY，未配置时返回默认分析结果。
