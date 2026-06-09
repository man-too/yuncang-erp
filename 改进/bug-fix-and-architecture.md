# Bug 修复记录（第二批）+ 架构问题分析

> 日期：2026-06-09
> 状态：已修复并推送

---

## 已修复的 Bug

### Bug 1：快捷操作映射错误 — safety_stock/transfer_advice 调出热力图

**根因**：`ai_chat.py` 的 `QUICK_ACTION_TOOLS` 硬编码 `"safety_stock"` 和 `"transfer_advice"` 都映射到 `render_inventory_heatmap`。快捷操作走 `/api/ai/quick-chart` 不经过 LLM，所以提示词改了也没用。

**修复**：
- 新建 `render_safety_stock_table`（chart_tools.py）：批量 ROP 计算，返回 table block
- 新建 `render_transfer_advice_table`（chart_tools.py）：仓库间库存差异分析，返回 table block
- 更新 `QUICK_ACTION_TOOLS` 映射
- `chat_service.py` render 工具白名单同步补充

### Bug 2：AI 回复图表大小不固定

**根因**：assistant 气泡无 max-width，图表 width: 100% 随容器变化。

**修复**：
- `.chat-message.assistant` max-width: 1200px
- `.chart-container` min-width: 600px
- `.chart-render` height: 400px, min-width: 600px
- `.block-table` 已有 overflow-x: auto，无需额外改动

### Bug 3：采购决策供应商验证失败 — fetchAuditPlan 数据流断裂

**根因**：`purchaseDecision.ts` 的 `fetchAuditPlan` 用 `selectedProducts`（复选框子集）而非 `allProducts`，数量取 `quantities`（Step0 总量）而非 `supplierQuantities`（Step1 分配量），只取第一个供应商，过滤掉 supplier_id=0 的项 → items 为空 → 弹警告 → auditResult=null。

**修复**：改用 `allProducts.value` 遍历，数量优先取 `supplierQuantities`，无供应商时 supplier_id=0 不过滤。

### Bug 4：风险预测不可用 — auditResult 为 null

**根因**：Bug 3 的直接后果。修复 Bug 3 后自动解决。

### Bug 5：AI 返回图表但不返回分析文字

**根因（两层）**：

1. **对话路径**：`_user_wants_chart(user_msg)` 判断用户没说"图"→ direct_blocks 被丢弃 → LLM 第二轮受 SYSTEM_PROMPT "blocks 可选" 影响也不放 blocks → 最终只有 parsed.blocks 为空
2. **快捷操作路径**：`/api/ai/quick-chart` 只返回 `{"blocks": blocks}` 没有 content → 前端 `fetchQuickActionBlocks` 也只取 blocks 丢弃 content → 用户只看到图没有分析

**修复**：
- SYSTEM_PROMPT 改为 "blocks 必须包含工具返回的结构化数据"
- direct_blocks 始终合并（删掉 `_user_wants_chart` 条件判断）
- render 工具 tool message 改为 `_summarize_render_result` 摘要（省 token + 防 LLM 重复输出 blocks）
- `ai_quick_chart` 端点新增 `_generate_quick_analysis` 生成基于数据的分析文字
- 前端 `fetchQuickActionBlocks` 返回 `{content, blocks}`
- 前端 `sendQuickAction` 用 `fallbackContent` 兜底 LLM 失败

---

## 待讨论的架构问题

### 当前架构：两条路径

#### 路径一：对话聊天（/api/ai/chat）

```
用户自由输入
    │
    ▼
LLM 第1轮：决定调哪些工具（tools=ALL_TOOLS, 23个）
    │
    ├─ render_* 工具 → 执行 → blocks存direct_blocks + 摘要喂LLM
    ├─ query_* 工具  → 执行 → 完整JSON喂LLM
    └─ action 工具   → 阻止执行 → 返回"需用户确认"
    │
    ▼
LLM 第2轮：看摘要/数据写分析文字（tools=ALL_TOOLS, 23个, response_format=json_object）
    │
    ├─ 可能再调工具（白烧token）
    └─ 返回 {content, blocks}
    │
    ▼
合并：direct_blocks + parsed.blocks → 去重 → 返回前端
```

#### 路径二：快捷操作（前端两步走）

```
用户点按钮 "安全库存"
    │
    ▼
Step 1: GET /api/ai/quick-chart?type=safety_stock
    → 后端直接执行 render_safety_stock_table
    → _generate_quick_analysis 生成分析文字
    → 返回 {content: "分析...", blocks: [table]}
    │
    ▼
Step 2: POST /api/ai/chat
    → 整个对话流程（LLM第1轮+可能调工具+LLM第2轮）
    → 前端加system hint: "图表已生成，只写分析"
    → 拿到 llmContent
    │
    ▼
合并：content = llmContent || fallbackContent
      blocks = directBlocks + llmBlocks
```

### 问题分析

| 问题 | 说明 |
|------|------|
| **快捷操作 Step 2 多余** | 后端 `_generate_quick_analysis` 已生成质量不错的分析，再花 3-8 秒 + 5000 token 调 LLM 写一段可能差不多的文字，性价比极低 |
| **LLM 第2轮传 23 个工具定义** | LLM 已有摘要，只需写文字，但还传 `tools=ALL_TOOLS` → LLM 可能再调一次工具 → 白烧 token + 增加延迟 |
| **SYSTEM_PROMPT 与 direct_blocks 矛盾** | Prompt 说"blocks必须包含工具数据"，但 direct_blocks 已从工具直达前端 → LLM 放 blocks 会重复，不放又违反 prompt |
| **_user_wants_chart 已删但函数还在** | 函数本身没删，只是不再被 chat 流程调用，可以清理 |
| **_dedup_chart_blocks 只对 chart 去重** | table block 不去重，格式不同时也可能漏 |

### 建议方向（待定）

**原则：图表确定性强走直出，分析文字能用模板就用模板，LLM 只用于开放性问题**

| 场景 | 当前做法 | 建议做法 |
|------|----------|----------|
| 用户自由输入"看库存图" | render→direct_blocks + 摘要→LLM第2轮(带tools)→分析 | render→direct_blocks + 摘要→LLM第2轮(**不带tools**)→只写文字 |
| 用户自由输入"库存怎么样" | query→LLM第2轮→分析+blocks | 不变，这是合理的 |
| 快捷操作"安全库存" | render+模板分析 + **LLM再走对话** | render+模板分析，**不调LLM** |
| 快捷操作+后续追问 | 只有模板分析 | 第1次用模板，后续追问走对话 |

### 需确认的决策

1. **快捷操作是否完全不走 LLM？** → 优点：秒级响应、省 token。缺点：分析文字是模板格式，不如 LLM 自然
2. **LLM 第2轮是否去掉 tools 参数？** → 优点：防止再调工具。缺点：如果 LLM 第1轮只调了 query_* 没调 render，第2轮就没机会补调了
3. **direct_blocks 是否完全删掉？** → 方案A：删掉，LLM统一输出 blocks。方案B（当前）：保留，始终合并。风险：方案A完全依赖LLM格式正确，格式出错图表就丢了

---

## 架构问题清单（待改进）

### 🔴 问题 1：LLM 输出格式不稳定 — `_parse_response` 层层打补丁

**现状**：要求 LLM 返回 `{"content": "...", "blocks": [...]}` 的严格 JSON，但 LLM 经常不听话：
- 返回 ```json ... ``` 包裹的代码块
- 在 JSON 前后加说明文字
- 在 content 里嵌入 chart JSON（`_extract_embedded_chart_json` 专门处理）
- 返回纯数组而非 dict（`try_parse` 的 list 分支）
- 返回非 JSON 纯文本

`_parse_response` 有 5 层解析：直接解析 → 去代码块 → 暴力搜索所有 `{}` → 提取 content 中嵌入的 chart JSON → 纯文本兜底。每层都是修一个 bug 加一层补丁。

**风险**：解析越复杂，边界 case 越多。比如 content 里的 chart JSON 提取如果匹配到用户说的 `{"type":"chart"}` 这几个字就会误提取。

**涉及文件**：`chat_service.py` 第 581-744 行

---

### 🔴 问题 2：LLM 第二轮仍传 `tools=ALL_TOOLS` — 可能再调工具

**现状**：LLM 第二轮传了全部 23 个工具定义 + `tool_choice="auto"`，LLM 可能再调一次工具（比如调 `query_inventory` 查一遍已经在 render 结果里有的数据），白烧 token + 增加延迟。

**最差路径**：用户说"看库存热力图" → LLM 第1轮调 render_heatmap → 第2轮 LLM 又调 query_inventory → 第3轮 LLM 才写分析 → **3 次 LLM 调用**。

**建议**：LLM 第二轮不传 tools，或 `tool_choice="none"`，只让它写分析文字。

**涉及文件**：`chat_service.py` 第 422-431 行、第 530-538 行

---

### 🟡 问题 3：SYSTEM_PROMPT 与 direct_blocks 指令矛盾

**现状**：
- SYSTEM_PROMPT 说 "blocks 必须包含工具返回的结构化数据"
- 但 `_summarize_render_result` 告诉 LLM "你不需要在 blocks 中重复输出这些数据"
- LLM 收到两条矛盾指令，行为不可预测

**建议**：统一指令，明确 LLM 第二轮只需输出 content 分析文字，blocks 由系统自动处理。

**涉及文件**：`chat_service.py` SYSTEM_PROMPT、`_summarize_render_result`

---

### 🟡 问题 4：`_dedup_chart_blocks` 只去重 chart，table 不去重

**现状**：只按 chart title 去重。如果 direct_blocks 和 LLM 都输出了同一张 table，会重复展示。

**建议**：对 table 也按列名+行数去重，或改为统一按内容 hash 去重。

**涉及文件**：`chat_service.py` 第 560-578 行

---

### 🟡 问题 5：重试逻辑重复了整个工具执行流程

**现状**：LLM 第1轮不调工具 → 检测是数据问题 → 加警告重试 → 重试后如果调了工具，**整个工具执行+LLM第2轮的代码又写了一遍**（line 499-544 几乎是 line 370-463 的复制粘贴）。

**建议**：抽取为 `_execute_tools_and_summarize(tool_calls, db, creator_id)` 函数，两处调用同一个函数。

**涉及文件**：`chat_service.py` 第 370-415 行 vs 第 499-528 行

---

### 🟡 问题 6：对话历史没有压缩 — token 越聊越多

**现状**：每次对话把 `messages.value` 全部传给后端，后端再全传给 LLM。query_* 工具返回的完整 JSON 也存在对话历史里。聊了 10 轮后，每轮 LLM 都要读前面所有轮的完整数据，token 可能从 2000 涨到 20000+。

**建议**：
- 保留最近 N 轮完整历史，更早的对话只保留摘要
- query_* 工具结果在存入历史时截断为摘要（类似 `_summarize_render_result` 的思路）
- 或设 token 上限，超过时自动截断早期消息

**涉及文件**：`chat.ts`、`chat_service.py`

---

### 🟢 问题 7：`_user_wants_chart` 函数残留

**现状**：函数还在（line 259-264），但不再被 chat 流程调用。死代码。

**建议**：删除。

**涉及文件**：`chat_service.py` 第 259-264 行

---

### 🟢 问题 8：render 工具白名单硬编码在多处

**现状**：`chat_service.py` 的 line 387-391 和 line 510 各有一份 render 工具名列表，`ai_chat.py` 的 `QUICK_ACTION_TOOLS` 又是一份。新增 render 工具要改三个地方。

**建议**：在 `chart_tools.py` 中定义 `RENDER_TOOL_NAMES = set(...)` 常量，其他地方引用这个常量。

**涉及文件**：`chat_service.py`、`ai_chat.py`、`chart_tools.py`

---

### 优先级排序

| 优先级 | 问题 | 影响 | 改动量 |
|--------|------|------|--------|
| **P0** | 问题 2：LLM 第2轮传 tools | 成本+延迟 | 小（删一个参数） |
| **P0** | 问题 3：SYSTEM_PROMPT 矛盾 | 输出不稳定 | 小（改 prompt） |
| **P1** | 问题 5：重试逻辑重复 | 维护性 | 中（抽取函数） |
| **P1** | 问题 8：白名单硬编码 | 维护性 | 小（抽常量） |
| **P1** | 问题 7：死代码 | 代码整洁 | 小（删几行） |
| **P2** | 问题 1：解析补丁 | 稳定性 | 大（重构 _parse_response） |
| **P2** | 问题 6：对话历史无压缩 | 成本 | 中（加截断逻辑） |
| **P2** | 问题 4：table 不去重 | 偶发重复展示 | 小（扩展去重） |