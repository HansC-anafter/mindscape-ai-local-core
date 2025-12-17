---
playbook_code: threejs_hero_landing
version: 1.0.0
name: Three.js Hero 登陸頁面生成器
description: 生成互動式 Three.js + GSAP hero 區塊用於登陸頁面，包含完整的 HTML+JS 程式碼與 React/three-fiber 轉換指引
tags:
  - webfx
  - threejs
  - gsap
  - landing
  - animation
  - frontend

kind: user_workflow
interaction_mode:
  - conversational
  - needs_review
visible_in:
  - workspace_tools_panel
  - workspace_playbook_menu

required_tools: []

language_strategy: model_native
locale: zh-TW
supported_locales:
  - zh-TW
  - en
default_locale: zh-TW
auto_localize: true

entry_agent_type: webfx_coder
icon: 🎨
---

# Three.js Hero 登陸頁面生成器 - SOP

## 目標
生成完整、可直接使用的 Three.js + GSAP hero 區塊用於登陸頁面。先輸出獨立的 HTML+JS 程式碼，然後提供 React/three-fiber 轉換指引以便整合到 Mindscape。

## 執行步驟

### Phase 0: 檢查 Project Context

#### 步驟 0.1: 檢查是否有活躍的 web_page project
- 檢查 execution context 中是否有 `project_id`
- 如果有，確認 project type 為 `web_page` 或 `website`
- 如果沒有，使用現有流程（獨立生成到 artifacts）

#### 步驟 0.2: 獲取 Project Sandbox 路徑（如果有 project）
- 如果有 project context，使用 `project_sandbox_manager.get_sandbox_path()` 獲取 sandbox 路徑
- Sandbox 路徑結構：`sandboxes/{workspace_id}/{project_type}/{project_id}/`
- 確保 `hero/` 目錄存在

#### 步驟 0.3: 讀取頁面規格（如果有 project）
- 如果有 project context，嘗試讀取 `spec/page.md`（從 `page_outline` playbook）
- 如果存在，使用 page.md 中的 hero 規劃作為設計參考
- 如果不存在，使用現有流程（獨立需求收集）

### Phase 1: 需求收集

#### 如果有 Project Context 且存在 `spec/page.md`：
- **讀取頁面規格**：從 `spec/page.md` 中提取 hero 區塊的規劃
- **使用規格中的設計**：使用 page.md 中定義的 hero 類型、內容、風格
- **補充細節**：如果需要，詢問額外的技術細節（相機行為、互動風格等）

#### 如果沒有 Project Context 或不存在 `spec/page.md`：
- **設計參考**：詢問設計靈感、情緒板或參考網站
- **相機行為**：了解期望的相機移動方式（軌道、基於滾動、互動式）
- **互動風格**：確定使用者互動（滑鼠移動、滾動觸發、點擊事件）
- **目標平台**：識別部署目標（網頁、行動響應式、特定瀏覽器）
- **效能需求**：了解效能限制與目標裝置
- **內容元素**：識別文字、圖片、3D 模型或其他需要包含的資產

### Phase 2: 架構設計
- **場景結構**：設計 Three.js 場景階層
  - 相機設定（PerspectiveCamera 與適當的 FOV 和位置）
  - 光源策略（環境光、方向光、點光源）
  - 渲染器配置（抗鋸齒、像素比、陰影貼圖）
- **GSAP 時間軸策略**：規劃動畫序列
  - 進入動畫（淡入、滑入、放大）
  - 滾動觸發動畫
  - 互動懸停/點擊動畫
  - 退出或過渡動畫
- **滾動觸發策略**：設計基於滾動的互動
  - 視差效果
  - 與滾動綁定的相機移動
  - 元素顯示動畫
  - 進度指示器
- **效能優化**：規劃優化技術
  - 重複物件的幾何體實例化
  - 紋理壓縮與 LOD（細節層級）
  - 動畫幀率管理
  - 記憶體清理策略

### Phase 3: 程式碼生成

#### 步驟 3.1: 生成 React Three Fiber 組件（主要）
**優先級**：直接生成 React Three Fiber 組件以整合到 site-brand

生成組件包含：
- **TypeScript 介面**：正確的 props 型別定義
- **React Three Fiber 結構**：使用 R3F JSX 語法
- **GSAP 整合**：使用 `useEffect` 或 `useLayoutEffect` 設定時間軸
- **狀態管理**：互動元素的 React state
- **效能優化**：useFrame, useMemo, 適當的清理
- **錯誤處理**：優雅的降級與錯誤邊界
- **註釋**：英文註釋，符合程式碼規範

#### 步驟 3.2: 獨立 HTML+JS 輸出（可選）
如使用者要求獨立版本用於測試：
- 生成完整、可運行的 HTML+JS 程式碼
- 包含 Three.js 與 GSAP 的 CDN 連結
- 提供測試指引
- 註：此為可選，主要輸出為 React Three Fiber 組件

### Phase 4: 整合說明
- **依賴清單**：完整的 npm 套件列表
  - `three`, `@react-three/fiber`, `@react-three/drei`
  - `gsap`, `@gsap/react`
  - 其他函式庫（載入器、後處理等）
- **安裝指引**：逐步設定指南
- **檔案結構**：建議的專案組織方式
- **整合步驟**：如何整合到 Mindscape 元件系統
- **故障排除**：常見問題與解決方案
  - 效能問題
  - 動畫故障
  - 瀏覽器相容性
  - 行動響應式
- **優化技巧**：進一步的效能改進
- **測試檢查清單**：部署前需要驗證的事項

## 程式碼品質標準

### Three.js 最佳實踐
- 使用 BufferGeometry 以獲得更好的效能
- 實作幾何體、材質、紋理的正確清理
- 使用 Object3D 群組進行組織
- 使用實例化優化繪製調用
- 在適用的地方實作視錐剔除

### GSAP 最佳實踐
- 使用 `gsap.context()` 進行適當的清理
- 利用 ScrollTrigger 進行基於滾動的動畫
- 使用 `will-change` CSS 屬性提升效能
- 實作動畫暫停/恢復以提升效能
- 清理事件監聽器與時間軸

### React/Three-Fiber 最佳實踐
- 使用 `useMemo` 處理昂貴的計算
- 在 `useEffect` 中實作適當的清理
- 高效使用 `useFrame`（避免繁重計算）
- 利用 R3F 的自動渲染優化
- 使用 `Suspense` 進行異步資產載入

## 個人化

基於使用者的 Mindscape 個人檔案：
- **技術等級**：若為「進階」，包含進階優化技術與自訂著色器
- **詳細程度**：若偏好「高」，提供廣泛的程式碼註釋與架構說明
- **工作風格**：若偏好「結構化」，分解為較小、可測試的元件

## 與長期意圖的整合

若使用者有相關的活躍意圖（例如「建立公司登陸頁面」），明確引用：
> "由於您正在進行「建立公司登陸頁面」，我將專注於創建與您的品牌識別和轉換目標一致的 hero 區塊..."

## 成功標準
- React Three Fiber 組件無 TypeScript 編譯錯誤
- 所有動畫流暢運行（目標 60fps）
- 程式碼文檔完整且可維護（英文註釋）
- 組件符合專案程式碼規範與風格
- 整合到 site-brand 後正常運行
- 效能符合目標需求
- 響應式設計在目標裝置上正常運作

### Phase 4: Site-Brand 整合

#### 步驟 4.1: 分析 Site-Brand 結構
- 檢視現有組件結構：`site-brand/sites/mindscape-ai/src/components/Home/`
- 了解組件模式（DissolvePlane, IntentCards, SharedFogLayer）
- 識別整合點（要添加到哪個頁面）
- 檢視專案使用的 TypeScript 與 React Three Fiber 慣例

#### 步驟 4.2: 生成 React Three Fiber 組件
**優先級**：直接生成 React Three Fiber 組件（而非獨立 HTML+JS）

**組件結構**：
```typescript
import { useRef, useMemo } from 'react'
import { useFrame, useThree } from '@react-three/fiber'
import * as THREE from 'three'
import { gsap } from 'gsap'

interface ComponentNameProps {
  // Define props
}

export default function ComponentName({ ...props }: ComponentNameProps) {
  const meshRef = useRef<THREE.Mesh>(null)
  const { gl, scene, camera } = useThree()

  useFrame((state) => {
    // Animation loop
  })

  useEffect(() => {
    // GSAP timeline setup
    return () => {
      // Cleanup
    }
  }, [])

  return (
    <mesh ref={meshRef}>
      {/* Three.js objects as JSX */}
    </mesh>
  )
}
```

**要求**：
- 使用 TypeScript 與正確的型別定義
- 遵循 React Three Fiber 模式（JSX 語法）
- 使用 `useEffect` 或 `useLayoutEffect` 整合 GSAP
- 實作適當的清理邏輯
- 使用英文註釋（符合程式碼規範）
- 符合現有組件風格與結構

#### 步驟 4.3: 組件整合
- 確定目標頁面（例如 `src/pages/index.tsx`）
- 生成組件導入語句
- 更新頁面以在 Canvas 中包含新組件
- 確保使用 WebGLContextGuard（如需要）
- 處理組件 props 與狀態管理

### Phase 5: Site-Brand 部署

#### 步驟 5.1: 準備組件檔案
- 生成組件檔案：`site-brand/sites/mindscape-ai/src/components/Home/{ComponentName}.tsx`
- 確保檔案遵循專案結構與命名慣例
- 驗證 TypeScript 語法與導入
- 檢查是否有缺少的依賴

#### 步驟 5.2: 透過檔案系統 + Git 部署
**方式**：使用檔案系統工具寫入檔案，然後透過 Git 提交

**步驟**：
1. 使用檔案系統工具將組件檔案寫入正確路徑
2. 更新頁面檔案以導入並使用新組件
3. 提交變更到 Git 倉庫（如權限允許）
4. 或提供手動提交指引

**檔案路徑**：
- 組件：`site-brand/sites/mindscape-ai/src/components/Home/{ComponentName}.tsx`
- 頁面更新：`site-brand/sites/mindscape-ai/src/pages/index.tsx`（或目標頁面）

#### 步驟 5.3: 構建與部署
- 觸發 Next.js 構建（`next build`）
- 驗證構建成功無錯誤
- 透過 Docker Compose 部署靜態檔案
- 或提供部署指引

#### 步驟 5.4: 驗證部署
- 檢查組件檔案是否存在於正確位置
- 驗證頁面正確導入並渲染組件
- 測試 Three.js 場景無錯誤載入
- 驗證 GSAP 動畫流暢運行
- 檢查響應式設計在行動裝置上的表現
- 驗證效能（目標 60fps）

#### 步驟 5.5: 返回部署結果
- 提供組件檔案路徑
- 提供 Git commit hash（如已提交）
- 提供預覽連結（如已部署）
- 提供部署摘要：
  - 組件檔案位置
  - 頁面整合狀態
  - 構建狀態
  - 任何警告或錯誤
- 提供後續步驟：
  - 需要手動審查
  - 測試建議
  - 優化建議

## 自然語言輸入處理

當使用者提供自然語言描述時，提取：
- **組件名稱**：建議的組件名稱（例如 "TechHero", "ParticleBackground"）
- **設計風格**：現代、復古、科技、極簡等
- **動畫效果**：滾動視差、滑鼠互動、自動播放、溶解過渡等
- **3D 元素**：粒子、幾何體、3D 模型、著色器效果等
- **色彩方案**：特定顏色或配色方案
- **互動方式**：滑鼠移動、滾動觸發、點擊事件等
- **整合目標**：要整合到哪個頁面（首頁、特定路由等）

**自然語言輸入範例**：
- "我想要一個科技風格的 hero 區塊，有粒子效果，滑鼠移動時有視差效果，整合到首頁"
- "創建一個復古風格的登陸頁面 hero，使用滾動觸發動畫，添加到 index 頁面"
- "生成一個極簡的 hero 區塊，有 3D 幾何體和溶解過渡效果，整合到 site-brand"

### Phase 6: 組件輸出與保存

#### 步驟 6.1: 確定輸出路徑
**根據是否有 Project Context**：

**如果有 Project Context**：
- **輸出路徑**：`hero/Hero.tsx`（在 Project Sandbox 中）
- **完整路徑**：`sandboxes/{workspace_id}/{project_type}/{project_id}/hero/Hero.tsx`
- **註冊 Artifact**：使用 `artifact_registry.register_artifact` 註冊
  - `artifact_id`: `hero_component`
  - `artifact_type`: `react_component`
  - `path`: `hero/Hero.tsx`

**如果沒有 Project Context**：
- **輸出路徑**：`artifacts/threejs_hero_landing/{{execution_id}}/ParticleNetworkHero.tsx`
- 使用現有流程（獨立生成）

#### 步驟 6.2: 保存生成的組件代碼
**必須**使用 `sandbox.write_file` 工具保存生成的 React Three Fiber 組件（首選）或 `filesystem_write_file`（需要人工確認）：

- **文件路徑**：根據步驟 6.1 確定的路徑
- **內容**：完整的組件代碼（包含所有導入、類型定義、組件邏輯）
- **確保文件可以直接在項目中使用**

#### 步驟 6.3: 保存對話歷史
**必須**使用 `sandbox.write_file` 工具保存完整的對話歷史（首選）或 `filesystem_write_file`（需要人工確認）：

- **文件路徑**：
  - 如果有 Project Context：`artifacts/threejs_hero_landing/{{execution_id}}/conversation_history.json`
  - 如果沒有 Project Context：`artifacts/threejs_hero_landing/{{execution_id}}/conversation_history.json`
- **內容**：完整的對話歷史（包含所有 user 和 assistant 消息）
- **格式**：JSON 格式，包含時間戳和角色信息

#### 步驟 6.4: 保存執行摘要
**必須**使用 `sandbox.write_file` 工具保存執行摘要（首選）或 `filesystem_write_file`（需要人工確認）：

- **文件路徑**：`artifacts/threejs_hero_landing/{{execution_id}}/execution_summary.md`
- **內容**:
  - 執行時間
  - 執行 ID
  - Playbook 名稱
  - 主要輸入參數（設計需求、互動風格等）
  - 執行結果摘要
  - 生成的組件名稱和路徑
  - 整合說明和依賴清單
  - 是否有 Project Context（如果有，記錄 project_id）

#### 步驟 6.5: 保存使用範例（如已生成）
如果生成了使用範例，保存到：

- **文件路徑**：`artifacts/threejs_hero_landing/{{execution_id}}/usage-example.tsx`
- **內容**：完整的使用範例代碼

## 注意事項
- 始終首先生成獨立程式碼以便測試
- 提供原生 Three.js 與 React 版本
- 包含完整的錯誤處理
- 記錄所有依賴與版本
- 考量無障礙性（鍵盤導航、螢幕閱讀器）
- 在多個瀏覽器與裝置上測試
- **部署**：程式碼生成後，自動提供部署到 site-brand 的選項
- **確認**：部署到生產環境前始終與使用者確認
- **版本控制**：保留部署歷史以便回滾
- **執行記錄**：必須保存完整的對話歷史和執行摘要，方便後續查閱和改進

