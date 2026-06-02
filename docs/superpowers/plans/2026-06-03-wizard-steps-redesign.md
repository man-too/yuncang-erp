# 采购决策向导 步骤1-3 实现计划
> SUB-SKILL: Use subagent-driven-development
**Goal:** 实现采购决策向导的步骤1(风险评估)、步骤2(供应商匹配)、步骤3(销量预测)，并简化步骤0，修复步骤4数据源
**Architecture:** 5步向导，上下布局(上部AI分析+图表，下部操作区)，Pinia store跨步骤传递数据
**Tech Stack:** Vue 3 + Pinia + Element Plus + ECharts 5 + vue-echarts

## 前置修改

### Task 0.1: 简化 StepInventory.vue
- 表格去掉"数量"列和"单价"列
- 弹窗去掉数量输入和单价输入，只保留选择产品+仓库
- 去掉 `quantities` 相关逻辑（数量留给步骤3）
- 文件: `erp-frontend/src/views/ai/steps/StepInventory.vue`

### Task 0.2: 精简 purchaseDecision store
- `addToProducts` 不再设 `suggested_qty`（简化为0）
- 新增 `riskResults` 状态存储步骤1结果
- 新增 `supplierChoices: Record<number, number>` 存储步骤2选择（product_id → supplier_id）
- 新增 `forecastQuantities: Record<number, number>` 存储步骤3调整后的数量
- 新增 `forecastPrices: Record<number, number>` 存储步骤2带入的价格
- 文件: `erp-frontend/src/stores/purchaseDecision.ts`

## 步骤1: 风险评估

### Task 1.1: 新建 StepRisk.vue
- 上部: 调用 `POST /api/ai/stock-alert` 对步骤0选中的每个产品逐个分析，显示 AI 汇总
- 中部: 产品风险卡片列表，按风险等级分组（严重/高/中/低）
- 每项显示: 产品名、当前库存、日均销量(从API获取)、缺货天数、风险等级
- 支持移除产品（从清单中去掉）
- 下部: 上一步/下一步按钮
- 文件: `erp-frontend/src/views/ai/steps/StepRisk.vue`

### Task 1.2: 后端新增批量风险分析接口
- 新增 `POST /api/ai/stock-alert-batch` 接收 `product_ids: list[int]`
- 一次性返回所有产品的风险分析结果
- 文件: `erp-backend/app/routers/ai_decision.py`

### Task 1.3: 前端 api/index.ts 新增接口
- 新增 `aiApi.stockAlertBatch(data: { product_ids: number[] })`

## 步骤2: 供应商匹配

### Task 2.1: 新建 StepSupplier.vue
- 上部: AI 供应商推荐分析（调用 `/api/ai/supplier-ranking`）
- 中部: 产品下拉选择器 + 供应商柱状图（评分对比）+ 排名表格（单选项）
- 下部: 已选供应商汇总条 + 上一步/下一步按钮
- 每个产品选一个供应商，系统自动记录该供应商的报价作为采购单价
- 复用 SupplierAnalysisPanel.vue 的柱状图和排名表逻辑
- 文件: `erp-frontend/src/views/ai/steps/StepSupplier.vue`

## 步骤3: 销量预测

### Task 3.1: 新建 StepForecast.vue
- 上部: AI 销量预测分析（调用 `/api/ai/sales-prediction`）
- 中部: 产品下拉选择器 + 历史销量折线图 + 预测虚线图（复用 SalesForecastPanel.vue 逻辑）
- 每项产品可调整采购数量，显示建议量（max_stock - current_qty）作为初始值
- 下部: 采购数量总览表（产品|供应商|建议量|采购量|单价|金额） + 上一步/下一步按钮
- 文件: `erp-frontend/src/views/ai/steps/StepForecast.vue`

## 步骤4: 汇总确认修复

### Task 4.1: 修复 StepSummary.vue 数据源
- supplier_id 从 store.supplierChoices 读取
- 数量和价格从 store.forecastQuantities / store.forecastPrices 读取
- 文件: `erp-frontend/src/views/ai/steps/StepSummary.vue`

## 向导路由

### Task 5.1: 更新 PurchaseDecisionWizard.vue
- currentStepComp 映射改为:
  - step 0 → StepInventory
  - step 1 → StepRisk
  - step 2 → StepSupplier
  - step 3 → StepForecast
  - step 4 → StepSummary
- 文件: `erp-frontend/src/views/ai/PurchaseDecisionWizard.vue`
