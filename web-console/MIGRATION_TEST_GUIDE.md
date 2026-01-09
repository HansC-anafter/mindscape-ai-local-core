# Playbook Surface 遷移測試指南

## 📋 概述

本指南說明如何測試新創建的 Playbook Surface 版本，同時保持現有頁面不變。

## ✅ 已完成的遷移工作

### 1. 後端 API
- ✅ `/api/v1/playbooks/{playbookCode}/ui-layout` API 端點已實現
- ✅ 支持從 playbook.json spec 和 capability pack UI 目錄載入 layout

### 2. 前端組件載入
- ✅ `component-loader.ts` - 組件動態載入器
- ✅ `PlaybookSurface.tsx` - 修正了 useEffect 依賴問題
- ✅ `api-loader.ts` - 字段名稱轉換（ui_layout ↔ uiLayout）

### 3. 遷移文件（不破壞現有頁面）
- ✅ UI Layout: `backend/app/capabilities/yogacoach/ui/yogacoach_teacher_upload_layout.json`
- ✅ 適配器組件: `web-console/src/app/capabilities/yogacoach/ui/components/TeacherVideoUpload.tsx`
- ✅ Playbook Surface 頁面: `web-console/src/app/workspaces/[workspaceId]/playbook/yogacoach_teacher_upload/page.tsx`

## 🔗 頁面對比

### 現有頁面（保持不變）
- **路徑**: `/capabilities/yogacoach/teacher-upload`
- **組件**: `app/capabilities/yogacoach/components/TeacherVideoUpload.tsx`
- **狀態**: ✅ 繼續正常工作，未修改

### 新 Playbook Surface 頁面（測試用）
- **路徑**: `/workspaces/{workspaceId}/playbook/yogacoach_teacher_upload`
- **組件**: `app/capabilities/yogacoach/ui/components/TeacherVideoUpload.tsx` (適配器)
- **狀態**: 🧪 可測試，但需要組件打包後才能完全工作

## 🧪 測試步驟

### 步驟 1: 測試 UI Layout API

```bash
# 測試 API 端點
curl http://localhost:8300/api/v1/playbooks/yogacoach_teacher_upload/ui-layout
```

預期響應：
```json
{
  "playbook_code": "yogacoach_teacher_upload",
  "ui_layout": {
    "type": "default",
    "main_surface": {
      "layout": "single_column",
      "components": [
        {
          "type": "TeacherVideoUpload",
          "position": "main",
          "config": {}
        }
      ]
    }
  },
  "uiLayout": { ... },
  "version": "1.0.0"
}
```

### 步驟 2: 訪問新頁面

1. 啟動開發服務器
2. 訪問: `http://localhost:8300/workspaces/{workspaceId}/playbook/yogacoach_teacher_upload`
3. 檢查瀏覽器控制台是否有載入錯誤

### 步驟 3: 組件打包（生產環境）

目前組件載入器會嘗試從靜態文件載入組件。要完全啟用，需要：

1. **編譯組件為 JavaScript bundle**
   - 使用 Vite/Webpack 將 `TeacherVideoUpload.tsx` 編譯為 UMD bundle
   - 輸出到: `backend/app/capabilities/yogacoach/ui/components/TeacherVideoUpload.js`

2. **配置靜態文件服務**
   - 確保後端可以服務 `/static/capabilities/yogacoach/ui/components/TeacherVideoUpload.js`

3. **組件導出格式**
   ```javascript
   // TeacherVideoUpload.js (UMD format)
   (function() {
     if (typeof window !== 'undefined') {
       if (!window.PlaybookComponents) window.PlaybookComponents = {};
       if (!window.PlaybookComponents.yogacoach) window.PlaybookComponents.yogacoach = {};
       window.PlaybookComponents.yogacoach.TeacherVideoUpload = TeacherVideoUpload;
     }
   })();
   ```

## 🔍 調試

### 檢查組件載入狀態

打開瀏覽器開發者工具，查看：
1. Network 標籤：檢查 `/api/v1/playbooks/yogacoach_teacher_upload/ui-layout` 請求
2. Console 標籤：查看組件載入日誌
3. 檢查 `window.PlaybookComponents` 對象

### 常見問題

1. **組件未載入**
   - 檢查組件是否已編譯並放置在正確路徑
   - 檢查靜態文件服務配置
   - 查看瀏覽器控制台錯誤

2. **UI Layout 404**
   - 確認 `yogacoach_teacher_upload_layout.json` 文件存在
   - 檢查 playbook code 是否正確

3. **組件渲染錯誤**
   - 檢查適配器組件的 props 傳遞
   - 確認原始組件的接口兼容性

## 📝 下一步

1. **完成組件打包流程**：設置 Vite/Webpack 配置，自動編譯組件
2. **測試完整流程**：從 UI Layout 載入到組件渲染
3. **遷移其他頁面**：將其他傳統頁面遷移到 Playbook Surface
4. **Site-Hub 整合**：實現 PlaybookSurfaceEmbed 組件

## ⚠️ 注意事項

- 現有頁面 `/capabilities/yogacoach/teacher-upload` **完全不受影響**
- 新頁面使用不同的路由和組件，可以並行測試
- 組件打包是生產環境必需的，開發環境可以暫時使用 fallback

