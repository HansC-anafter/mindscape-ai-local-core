---
playbook_code: threejs_hero_adjustment
version: 1.0.0
name: Three.js Hero 區塊調整
description: 協助使用者分析並轉換 Gemini 生成的 Three.js + GSAP 程式碼至 Mindscape 元件架構，包含 React/three-fiber 結構轉換與整合任務規劃
tags:
  - webfx
  - threejs
  - gsap
  - animation
  - frontend
  - integration

kind: user_workflow
interaction_mode:
  - conversational
  - needs_review
visible_in:
  - workspace_tools_panel
  - workspace_playbook_menu

required_tools:
  - sandbox.write_file
  - sandbox.read_file
  - filesystem_write_file
  - filesystem_read_file

language_strategy: model_native
locale: zh-TW
supported_locales:
  - zh-TW
  - en
default_locale: zh-TW
auto_localize: true

entry_agent_type: reviewer
icon: 🎨
---

# Three.js Hero 區塊調整 - SOP

## 目標
協助使用者分析 Gemini 生成的 Three.js + GSAP 程式碼，並轉換成 Mindscape 的 React/three-fiber 元件架構。提供程式碼結構分析、轉換指引與整合任務規劃。

## 執行步驟

### Phase 1: 程式碼分析
- 分析提供的 Three.js + GSAP 程式碼結構
- 識別關鍵元件：場景、相機、光源、幾何體、材質、動畫
- 對應 GSAP 時間軸與滾動觸發器
- 記錄依賴套件與外部函式庫
- 識別潛在的整合挑戰

### Phase 2: 架構對應
- 將 Three.js 場景結構對應到 React 元件階層
- 轉換原生 Three.js 至 React Three Fiber (R3F) 模式
- 識別可重用元件與一次性設定程式碼
- 規劃狀態管理策略（React state vs. Three.js state）
- 對應 GSAP 動畫至 React 生命週期鉤子或 effects

### Phase 3: 元件結構設計
- 設計 React 元件結構：
  - 主要容器元件
  - 場景設定元件
  - 物件/網格元件
  - 動畫控制器元件
- 定義 props 與 state 介面
- 規劃元件通訊模式
- 識別共用工具函數與輔助函數

### Phase 4: 整合任務規劃
- 建立詳細的程式碼轉換任務清單
- 優先排序任務（關鍵路徑優先）
- 識別任務間的依賴關係
- 評估每個任務的複雜度
- 提供逐步轉換指引

### Phase 5: 程式碼轉換指引
- 提供 React Three Fiber 等效程式碼範例
- 示範如何轉換 Three.js 物件至 R3F 元件
- 展示 GSAP 與 React hooks 的整合方式
- 提供效能優化最佳實踐
- 包含錯誤處理與邊界情況

## 程式碼轉換模式

### Three.js 轉 React Three Fiber
- `new THREE.Scene()` → `<Canvas><Scene /></Canvas>`
- `new THREE.PerspectiveCamera()` → `<PerspectiveCamera />`
- `new THREE.Mesh(geometry, material)` → `<mesh geometry={...} material={...} />`
- `scene.add(object)` → JSX 中的元件組合
- `renderer.render(scene, camera)` → 由 R3F 自動處理

### GSAP 整合
- 在 `useEffect` 鉤子中建立時間軸
- 使用 `useScroll` 鉤子或 GSAP ScrollTrigger 的滾動觸發器
- 在 `useEffect` 返回函數中清理動畫
- 透過 React state 更新狀態，而非直接操作 DOM

## 個人化

基於使用者的 Mindscape 個人檔案：
- **技術等級**：若為「進階」，提供詳細的實作模式與優化技巧
- **詳細程度**：若偏好「高」，包含完整的程式碼範例與邊界情況處理
- **工作風格**：若偏好「結構化」，提供清晰的任務分解與逐步指引

## 與長期意圖的整合

若使用者有相關的活躍意圖（例如「建立互動式登陸頁面」），明確引用：
> "由於您正在進行「建立互動式登陸頁面」，我建議先專注於 hero 區塊的轉換，因為這是主要的視覺元素..."

### Phase 6: 文件生成與保存

#### 步驟 6.1: 保存調整後的組件
**必須**使用 `sandbox.write_file` 工具保存調整後的組件（首選）或 `filesystem_write_file`（需要人工確認）：

- 文件路徑: `{ComponentName}_adjusted.tsx`（相對路徑，相對於 sandbox 根目錄）
- 內容: 調整後的 React Three Fiber 組件代碼
- 格式: TypeScript/TSX 格式

#### 步驟 6.2: 保存調整說明
**必須**使用 `sandbox.write_file` 工具保存調整說明（首選）或 `filesystem_write_file`（需要人工確認）：

- 文件路徑: `adjustment_notes.md`（相對路徑，相對於 sandbox 根目錄）
- 內容: 程式碼結構分析、轉換指引和整合任務規劃
- 格式: Markdown 格式

## 成功標準
- 程式碼結構已完整分析並記錄
- React 元件架構已明確定義
- 轉換任務清單完整且可執行
- 使用者有清晰的指引可將程式碼整合至 Mindscape
- 效能考量已處理

## 注意事項
- 此 playbook 假設程式碼是外部生成（例如從 Gemini）且需要整合
- 專注於轉換模式而非從零生成新程式碼
- 強調可維護性與 React 最佳實踐
- 考量打包大小與效能影響

