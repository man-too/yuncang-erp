# AI 决策模块 Bug 修复计划
> SUB-SKILL: subagent-driven-development
**Goal:** 修复采购决策向导双表格渲染、AI 智能推荐失效、问答框空白/加载失败等问题，共计 13 个修复任务。
**Architecture:** 后端 FastAPI + OpenAI SDK (DeepSeek) + Celery；前端 Vue 3 + Pinia + Element Plus。AI 对话走 chat_service.py 的流式/非流式 LLM 调用 + 工具链（tools/），前端 wizard 走 PurchaseDecisionWizard → StepInventory/StepSummary 组件。
**Tech Stack:** Python FastAPI, SQLAlchemy, OpenAI SDK, Vue 3 Composition API, Pinia, ECharts

---

## P0 — 阻断性问题（先修）

### Task 1: 修复 PurchaseDecisionWizard 双表格渲染（"两个表框"）
**文件:** `erp-frontend/src/views/ai/PurchaseDecisionWizard.vue:44-56`
**问题:** `currentChartComp` 和 `currentTableComp` 在步骤 0-3 都返回 `StepInventory`，导致左右面板各渲染一套完整的图表+表格。
**修复:** 左侧面板只渲染图表相关逻辑，右侧面板只渲染表格。将 `StepInventory` 拆分为两个独立组件 `StepChart` 和 `StepTable`，或通过 prop 控制 `StepInventory` 只显示图表/只显示表格。
**验证:** 打开采购决策向导 → 步骤 0-3 只看到一套表格 + 一套图表，不再出现两套表格。

### Task 2: 修复步骤 1-3 渲染回退问题 + 汇总步骤显示库存组件
**文件:** `erp-frontend/src/views/ai/PurchaseDecisionWizard.vue:46-56`
**问题:** 步骤 1-3（风险评估/供应商匹配/销量预测）没有对应组件，全部回退到 `StepInventory`。步骤 4 左侧仍渲染 `StepInventory`。
**修复:**
- `currentChartComp` 的 `case 4` 返回 `StepSummary`（或其他汇总图表组件）
- 步骤 1-3：左侧面板显示占位组件（含标题和描述，后续可扩展），右侧面板正常显示表格数据
**验证:** 步骤 1-3 看到不同的界面（非 StepInventory 重复），步骤 4 显示正确的汇总布局。

---

## P1 — 功能失效

### Task 3: 修复 AI 推荐按钮未调用 AI
**文件:** `erp-frontend/src/views/ai/steps/StepInventory.vue:152-168`
**问题:** `onRecommend()` 标签为"🤖 智能推荐"，但只调用 `inventoryApi.alerts()` 获取预警数据，完全没有调用 AI。Store 中有 `getRecommendation()` 但未被使用。
**修复:** `onRecommend()` 改为调用 `store.getRecommendation()`（`purchaseDecision.ts:76-95`），将实际库存数据传给 AI 获取推荐补货方案。
**验证:** 点击"智能推荐"→ 看到 AI 返回的补货建议，而非仅显示预警列表。

### Task 4: 修复聊天 store 中 isLoading 未在 finally 中重置
**文件:** `erp-frontend/src/stores/chat.ts:145-180`
**问题:** `sendQuickAction` 中 `isLoading.value = false` 不在 `finally` 块内。`fetchQuickActionBlocks` 若意外抛异常，`isLoading` 永久为 true。
**修复:** 将 `isLoading.value = false` 移入 `finally` 块。
**验证:** 模拟快速操作失败场景 → `isLoading` 仍能正确重置为 false。

### Task 5: 修复聊天出错时无助手反馈消息
**文件:** `erp-frontend/src/stores/chat.ts:69-72` 和 `sendQuickAction`
**问题:** API 调用失败只显示 `ElMessage.error`，用户消息悬空，无助手回复。
**修复:** 在 catch 块中 `addMessage({ role: 'assistant', content: '抱歉，请求失败，请重试。', blocks: [] })`。
**验证:** 模拟网络断开 → 用户消息下方显示错误提示的助手消息。

### Task 6: 修复后端 JSON 正则无法解析嵌套对象
**文件:** `erp-backend/app/services/chat_service.py:612`
**问题:** `re.finditer(r'\{[^{}]*\"content\"\s*:\s*\".+?\"[^{}]*\}', ...)` 的 `[^{}]` 排除嵌套大括号，导致 ECharts 等含嵌套配置的响应无法匹配。
**修复:** 改为递归括号匹配或使用 `json.loads` 的异常容错提取，依次尝试：整段 JSON 解析 → `\{.*\}` 贪婪匹配 → 逐个 `{...}` 提取并验证 JSON。
**验证:** 发送需要图表回复的问题 → AI 返回的图表数据能正确解析并在前端渲染。

### Task 7: 修复后端发送损坏数据给 AI
**文件:** `erp-backend/app/routers/ai_decision.py:71-74` 和 `:116`
**问题:** `ai_stock_alert` 中 `date` 字段填充的是 `order_id`（非日期）；`ai_sales_forecast` 中 `period` 填的是枚举索引 `i`（非实际时间）。
**修复:**
- `ai_stock_alert`：用 `SaleOrder` 的 `order_date` 替换 `order_id`
- `ai_sales_forecast`：用 `h.order_date` 替换 `str(i)`
**验证:** 调用对应 API，确认传给 AI 的数据中 date/period 是真实日期。

### Task 8: 修复默认模型名与 DeepSeek 不兼容
**文件:** `erp-backend/app/config.py:15`
**问题:** 默认 `OPENAI_MODEL: str = "gpt-4"` 但 `AI_BASE_URL` 指向 DeepSeek。DeepSeek 不识别 `gpt-4`。
**修复:** 默认 `OPENAI_MODEL` 改为 `"deepseek-chat"`，与默认 `AI_BASE_URL` 匹配。
**验证:** 使用默认配置（不设 OPENAI_MODEL 环境变量）→ AI 调用正常。

### Task 9: 修复 `response_format: json_object` 在 DeepSeek 下的兼容性
**文件:** `erp-backend/app/services/chat_service.py:470` 和 `services/ai_service.py:32`
**问题:** DeepSeek 早期版本不支持 `response_format={"type": "json_object"}`，会导致 400 错误。
**修复:** 将 `response_format` 参数包裹在 try/except 中，若 API 返回 400 且错误涉及 `response_format`，则移除该参数重试。或在 config 中增加 `AI_SUPPORTS_JSON_MODE: bool = False` 开关。
**验证:** 部署到 DeepSeek 环境 → AI 分析调用正常返回 JSON。

---

## P2 — 数据正确性

### Task 10: 修复 StepSummary 虚构的单价计算
**文件:** `erp-frontend/src/views/ai/steps/StepSummary.vue:79-80`
**问题:** `unit_price = max_stock / min_stock` 用库存阈值算单价，毫无财务意义。
**修复:** 改用产品的 `purchase_price` 字段（从 store 传入或从 API 获取）。
**验证:** 汇总确认步骤显示的单价和金额与实际采购价一致。

### Task 11: 修复仪表盘"库存异常"卡片数据错配
**文件:** `erp-frontend/src/views/AIDecision.vue:82`
**问题:** 卡片标签"库存异常"但数据来自 `total_inventory_items`（库存总项数）。
**修复:** 将标签改为"库存总项"或从后端获取真正的异常计数字段。
**验证:** 卡片标签与数值含义一致。

### Task 12: 修复 ChatMessage 中 isStatusValue 单字匹配过宽
**文件:** `erp-frontend/src/views/ai/ChatMessage.vue:180-183`
**问题:** 关键词含 `'高'`、`'中'`、`'低'` 等单字，导致包含这些字的商品名被误渲染为标签。
**修复:** 移除单字关键词，保留多字关键词（`'正常'`、`'告警'`、`'预警'`、`'偏低'`、`'偏高'`、`'缺货'` 等）。
**验证:** 包含"高"字的商品名（如"高露洁"）在表格中显示为纯文本，不被渲染为 el-tag。

---

## P3 — 体验优化

### Task 13: 修复 StepInventory 状态标签文字/颜色不匹配
**文件:** `erp-frontend/src/views/ai/steps/StepInventory.vue:40-44`
**问题:** 三目运算中后两个分支都显示"偏低"，但 color 分别为 warning 和 info。
**修复:** 第三个分支改为"正常"，color 保持 info。
**验证:** 库存充足的商品状态标签显示"正常"而非"偏低"。

---

## 执行顺序

```
P0: Task 1 → Task 2
P1: Task 3,4,5,6,7,8,9 （可并行）
P2: Task 10,11,12 （可并行）
P3: Task 13
```
