# 供应链ERP管理系统

> 进销存 + 供应商管理 + AI 智能决策，Vue3 + FastAPI + MySQL 全栈项目

## 技术栈

| 层级 | 技术 |
|------|------|
| 前端 | Vue 3 + TypeScript + Element Plus + Vite |
| 后端 | Python FastAPI + SQLAlchemy ORM |
| 数据库 | MySQL 8.0 |
| 认证 | JWT + bcrypt |
| AI | OpenAI / Claude API（大模型智能决策） |

## 功能模块

| 模块 | 说明 |
|------|------|
| 工作台 | 数据概览、AI 决策时间线、快速入口 |
| 供应商管理 | 档案 CRUD、模糊搜索、状态筛选、评分筛选 |
| 产品管理 | 物料/商品档案、分类管理、价格区间筛选、库存阈值 |
| 采购管理 | 采购订单创建/审批/入库、金额/日期筛选 |
| 库存管理 | 多仓库、库存盘点、变动流水、预警（库存不足/过多） |
| 销售管理 | 客户管理 + 销售订单创建/出库 |
| AI 智能决策 | 库存预警分析、销售预测、供应商推荐（大模型驱动） |
| 批量操作 | 表格勾选批量删除 |
| 编辑回显 | 编辑时通过主键重新查询最新数据 |

## 数据库表（17 张）

### 基础数据
| 表名 | 说明 | 核心字段 |
|------|------|---------|
| `users` | 用户 | username, email, role(admin/manager/operator/viewer) |
| `suppliers` | 供应商 | code, name, status, delivery_lead_time, rating |
| `product_categories` | 产品分类 | name, parent_id, sort_order |
| `products` | 产品/物料 | code, name, purchase_price, sale_price, min_stock, max_stock |
| `customers` | 客户 | code, name, credit_limit |
| `warehouses` | 仓库 | code, name, address, manager |

### 业务数据
| 表名 | 说明 |
|------|------|
| `purchase_orders` | 采购订单 (PO单号) |
| `purchase_order_items` | 采购订单明细 |
| `purchase_inbounds` | 采购入库单 |
| `sale_orders` | 销售订单 (SO单号) |
| `sale_order_items` | 销售订单明细 |
| `sale_outbounds` | 销售出库单 |

### 库存
| 表名 | 说明 |
|------|------|
| `inventories` | 库存 (按产品+仓库) |
| `inventory_records` | 库存变动记录 (出入库流水) |
| `inventory_alerts` | 库存预警记录 |

### AI 与辅助
| 表名 | 说明 |
|------|------|
| `ai_decision_records` | AI 决策记录 (含输入/输出/置信度) |
| `supplier_evaluations` | 供应商评估 |
| `supplier_contacts` | 供应商联系人 |

## API 接口

所有 API 文档自动生成：`http://localhost:8000/docs`

### 路由一览

| 前缀 | 模块 | 主要接口 |
|------|------|---------|
| `/api/auth` | 认证 | POST /login, /register, GET /me |
| `/api/suppliers` | 供应商 | 支持 keyword/contact/status/min_rating/日期 筛选 |
| `/api/products` | 产品 | 支持 keyword/category/unit/价格区间/is_active 筛选 |
| `/api/purchase` | 采购 | 支持 keyword/status/supplier/金额/日期 筛选 |
| `/api/inventory` | 库存 | 支持 keyword/warehouse/category/stock_status/数量 筛选 |
| `/api/sales` | 销售 | 客户支持 keyword/contact/credit 筛选；订单支持 keyword/status/customer/金额/日期 筛选 |
| `/api/ai` | AI决策 | POST /stock-alert, /sales-forecast, /supplier-recommend, GET /history, /dashboard |

## 快速启动

### 环境要求
- Python 3.10+
- Node.js 18+
- MySQL 8.0+

### 1. 启动 MySQL

确保 MySQL 服务已启动（phpStudy / MySQL Workbench / 命令行均可）。

### 2. 启动后端

```bash
cd erp-backend

# 安装依赖（仅首次）
pip install -r requirements.txt

# 后端启动时会自动创建表
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 3. 初始化数据（仅首次）

后端启动后，新开命令行，执行：

```bash
cd erp-backend
python seed_data.py
```

### 4. 启动前端

```bash
cd erp-frontend

# 安装依赖（仅首次）
npm install

# 启动
npm run dev
```

### 5. 访问系统

浏览器打开 `http://localhost:3000`

**默认管理员**：`admin` / `admin123`

（也可在登录页自行注册）

### 6. AI 功能配置（可选）

在 `erp-backend/.env` 中配置：

```env
OPENAI_API_KEY=sk-your-key-here
OPENAI_MODEL=gpt-4
```

不配置不影响业务模块使用。

## 项目结构

```
erp-system/
├── README.md
├── erp-backend/
│   ├── .env                    # 环境变量（数据库连接、AI Key）
│   ├── requirements.txt        # Python 依赖
│   ├── seed_data.py           # 测试数据初始化脚本
│   └── app/
│       ├── main.py             # FastAPI 入口
│       ├── config.py           # 配置
│       ├── database.py         # 数据库连接
│       ├── models/             # 17 张数据表模型
│       ├── schemas/            # Pydantic 请求/响应验证
│       ├── routers/            # 8 个 API 路由模块
│       ├── services/
│       │   └── ai_service.py   # AI 大模型调用服务
│       └── utils/
│           └── auth.py         # JWT + bcrypt 密码
└── erp-frontend/
    ├── index.html
    ├── package.json
    ├── vite.config.ts          # Vite + API 代理配置
    ├── tsconfig.json
    └── src/
        ├── main.ts             # Vue 入口
        ├── App.vue
        ├── api/index.ts        # Axios + 所有 API 封装
        ├── router/index.ts     # 路由（懒加载）
        ├── layouts/
        │   └── MainLayout.vue  # 主布局（侧边栏 + 顶栏）
        └── views/              # 8 个页面组件
            ├── Login.vue       # 登录/注册
            ├── Dashboard.vue   # 工作台
            ├── Supplier.vue    # 供应商管理
            ├── Product.vue     # 产品管理
            ├── Purchase.vue    # 采购管理
            ├── Inventory.vue   # 库存管理
            ├── Sales.vue       # 销售管理
            └── AIDecision.vue  # AI 智能决策中心
```

## 页面布局规范

每个业务页面采用统一四区布局：

```
┌──────────────────────────────────────────┐
│  📌 模块标题                               │  ← 顶部标题区
├──────────────────────────────────────────┤
│  🔍 [筛选1] [筛选2] [筛选3] [搜索] [重置]   │  ← 筛选区（搜索/重置各占一格）
├──────────────────────────────────────────┤
│  [批量删除(N)] [导入] [新增]               │  ← 功能按钮区
├──────────────────────────────────────────┤
│  ☑  ☐  列1  列2  列3  ...    [编辑][删除]  │  ← 表格区（带勾选列）
│                  ◀ 1 2 3 ▶               │  ← 分页（居中）
└──────────────────────────────────────────┘
```

筛选规则：输入框模糊查询，下拉框精准匹配。编辑时通过主键调用 GET 接口获取最新数据回显。

## 常见问题

| 问题 | 解决 |
|------|------|
| 登录卡住 | 确认后端已启动在 8000 端口 |
| 无数据 | 执行 `python seed_data.py` |
| bcrypt 报错 | `pip install bcrypt==4.0.1` |
| 端口被占用 | 改后端 `--port 8001`，前端 `vite.config.ts` 改 proxy target |
| npm 安装慢 | `npm config set registry https://registry.npmmirror.com` |
