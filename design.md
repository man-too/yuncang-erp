# 领星ERP Design System

> 来源：https://erp.lingxing.com/ — 通过抓取编译后的 `lingxing-ui@4.60.8/theme-chalk/index.css` (467KB) + 登录页CSS 提取真实Token

---

## 1. Visual Theme & Atmosphere

领星ERP采用**高密度信息型**设计。字体偏小（12px body），色彩克制但蓝调鲜明（`#005BF5`），白底为主辅以浅灰面版。整体追求**高效、低视觉噪音、专业可靠**的跨境ERP体验。登录页同样白底，logo区域居中，无装饰图。

**keyCharacteristics**:
- 高信息密度，12px基础字号
- 蓝白灰三色体系，无渐变/毛玻璃等装饰
- 4px统一圆角，2px紧凑型
- 阴影极克制 — 仅popover/dialog使用
- 菜单图标18px，用 `#A0A4A7` 灰色，hover反白
- 侧边栏推测为深色（基于 `rgba(11,16,25,0.8)` 的菜单hover规则）
- 状态色鲜明但不过饱和

---

## 2. Color Palette & Roles

### Primary — Blue

| Hex | Role | Where seen | Source |
|-----|------|------------|--------|
| `#005BF5` | 主色 | 图标、链接、按钮、选中态 | CSS: 191次出现 |
| `#0748b8` | 主色深 | primary按钮focus/active | CSS: `.el-button--primary:focus` |
| `#2e7bff` | 主色浅 | 部分hover变体 | CSS: 13次 |
| `rgba(0,91,245,0.06)` | 主色hover底 | bg-default hover | CSS: `.bg-default:hover` |
| `rgba(0,91,245,0.1)` | 主色active底 | bg-default active | CSS: `.bg-default:active` |
| `#E9F1FC` | 主色调浅底 | bg-default hover替代色 | CSS |

### Semantic

| Hex | Role | Source |
|-----|------|--------|
| `#00941E` | 成功 | CSS: 32次 |
| `#36C249` | 成功浅 | CSS: 9次 |
| `#F27A00` | 警告 | CSS: 28次 |
| `#FF9B29` | 警告浅 | CSS: 9次 |
| `#E52E2E` | 危险 | CSS: 52次 |

### Neutral — Warm Gray System

| Hex | Role | Where seen |
|-----|------|------------|
| `#0b1019` | 最深色（文字/深底） | icon hover bg, text color |
| `#33363C` | 主文字色 | 大量出现 |
| `#55585F` | 常规文字/Info色 | info色 + 默认icon色 |
| `#888c94` | 辅助文字 | disabled, append text |
| `#A0A4A7` | 菜单icon/placeholder | menu icon default |
| `#A6ABB4` | 浅灰文字 | 82次 |
| `#ABB5C7` | 浅灰文字变体 | 8次 |

### Surfaces & Backgrounds

| Hex | Role | Source |
|-----|------|--------|
| `#fff` | 主背景/卡片 | `body{background:#fff}` |
| `#F0F2F5` | 次级背景 | 27次 — hover bg, dialog close hover |
| `#f5f6f9` | 禁用/提示背景 | 19次 — tooltip bg, disabled |
| `#ebedf0` | 滚动条/footer背景 | 15次 |
| `#EBEEF5` | popover边框 | 24次 |

### Borders

| Hex | Role | Source |
|-----|------|--------|
| `#cad2e0` | 主边框 | 104次 — 最高频边框色 |
| `#e6e8eb` | 浅边框 | 46次 |
| `#EBEEF5` | popover边框 | 24次 |

---

## 3. Typography Rules

字体族: `element-icons` (iconfont), 系统默认中文字体

| Role | Font | Size | Weight | Line height | Letter spacing |
|------|------|------|--------|-------------|----------------|
| Body | 系统默认 | 12px | 400 | unset | 0 |
| Content | 系统默认 | 14px | 400 | 1.4 | 0 |
| Menu Icon | iconfont | 18px | 400 | 36px | 0 |
| Small/Helper | 系统默认 | 12px | 400 | — | 0 |

**关键**: 字体极小（12px body），信息密度极高。这是领星区别于常规ERP的核心特征。

---

## 4. Component Stylings

### Buttons
- **Primary**: `background-color:#005BF5; color:#fff` → focus: `#0748b8`
- **Default**: `background-color:#F0F2F5` → hover: `#E9F1FC` → active: `rgba(0,91,245,0.1)`
- Border-radius: 4px
- Font-size: 12px（与body一致）

### Cards
- Background: `#fff`
- No visible shadow in default state
- Border: 推测 `#EBEEF5` or none

### Inputs / Forms
- Border: `#cad2e0`
- Border-radius: 4px
- Append bg: `#ebedf0` with text `#888c94`

### Navigation / Menu
- Icon default: 18px, `#A0A4A7`
- Icon hover: `#fff` on `rgba(11,16,25,0.8)`
- Active state: primary blue `#005BF5`

### Tags
- Simple styling, no strong shadows
- Default bg: likely `#F0F2F5`

### Tables
- Header: likely `#f5f6f9` background
- Border: `#cad2e0` or `#e6e8eb`

### Popover
- Background: `#fff`
- Border: `1px solid #EBEEF5`
- Border-radius: 4px (standard) / 2px (body popover)
- Box-shadow: `0 4px 16px -4px rgba(0,0,0,0.2)`

---

## 5. Layout Principles

- **Spacing**: tight — 8px 12px 16px are the main steps
- **Max-width**: full-width app (not centered), sidebar + content layout
- **Whitespace**: minimal, high density
- Body `overflow-y: hidden` — full-height app shell
- Sidebar icons 48×48px with 36px line-height
- Filter bars: no special bg, integrated into page flow

---

## 6. Depth & Elevation

| Level | Shadow | Use |
|-------|--------|-----|
| 0 | none | Cards, buttons, inputs (flat default) |
| 1 | `0 2px 12px 0 rgba(0,0,0,0.1)` | Light popover |
| 2 | `0 4px 16px -4px rgba(0,0,0,0.2)` | Popover/dialog |
| 3 | `0 8px 16px 0 rgba(0,0,0,0.16)` | Dropdown/popover max |

**哲学**: 极度克制。大多数元素无阴影，仅在浮层使用。

---

## 7. Interaction & Motion

- **Hover**: 浅蓝底 `rgba(0,91,245,0.06)` 或 `#E9F1FC`
- **Active**: `rgba(0,91,245,0.1)` + primary文字色
- **Focus**: 与active相似，无额外outline
- **Transition**: Element UI默认 `0.3s`
- **Disabled**: `#f5f6f9` 底 + `#888c94` 文字 + `#cad2e0` 边框

---

## 8. Responsive Behavior

- 非响应式 — ERP系统以桌面端为主
- 全屏布局，`overflow-y:hidden`
- 无媒体查询（CSS中未发现breakpoint定义）

---

## 9. Agent Prompt Guide

### Quick Color Reference
```
Primary: #005BF5 | #0748b8 (dark) | #E9F1FC (light bg)
Success: #00941E | Warning: #F27A00 | Danger: #E52E2E
Text: #0b1019 → #33363C → #55585F → #888c94 → #A0A4A7
BG: #fff → #F0F2F5 → #f5f6f9 → #ebedf0
Border: #cad2e0 → #e6e8eb → #EBEEF5
Radius: 4px (standard), 2px (compact)
Font: 12px body / 14px content
Shadow: minimal — popover only
```

### 3 Example Prompts
1. "Build a data table page with LingXing ERP style: white background, #F0F2F5 filter bar area, #cad2e0 borders, 12px body text, 4px radius buttons with #005BF5 primary"
2. "Create a sidebar navigation matching 领星ERP: 48×48 icons, #A0A4A7 default color, white on dark hover (#0b1019 at 80% opacity), 18px icon font"
3. "Design a dashboard card in LingXing style: white card, no shadow, 12px stats text, #005BF5 for highlighted numbers, #F0F2F5 for secondary areas"

### 4-6 Iteration Tips
1. Start with font-size 12px for body — LingXing's signature is high density
2. Never use `#409EFF` — it's `#005BF5` (brighter, more vibrant)
3. Most backgrounds are white; `#F0F2F5` is the only gray surface
4. Shadows are ONLY for floating elements — cards and buttons are flat
5. Icons use the warm gray scale: `#55585F` default, `#A0A4A7` for menu
6. No rounded pills, no gradients, no backdrop blurs — flat, clean, professional
