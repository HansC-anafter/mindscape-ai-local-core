# Mindscape AI Local Core

> **Mindscape AI 的開源、本地版本**

[English](README.md) | [中文](README.zh.md)

這個倉庫（`mindscape-ai-local-core`）是一個乾淨、本地優先的 AI 工作區，透過智能對話介面幫助你整理想法、管理任務、執行工作流。

## 🧠 什麼是心智空間算法？

**心智空間算法（Mindscape Algorithm）** 是 Mindscape AI 的核心架構理念。

它把使用者的長期意圖、專案主線、創作主題，整理成一個**可治理、可導航的心智空間**，讓 LLM 不再只是回答單一問題，而是圍繞你的整體人生／工作主線一起思考與行動。

📖 了解更多：[心智空間算法](./docs/mindscape-algorithm.md) | [Mindscape AI 官網](https://mindscapeai.app)

## 🎯 什麼是 Mindscape AI Local Core？

`mindscape-ai-local-core` 倉庫是 Mindscape AI 的**開源基礎**。它提供：

- **意圖/工作流引擎**：AI 驅動的意圖提取和 Playbook 執行
- **Port/Adapter 架構**：核心與外部集成的清晰分離
- **本地優先設計**：所有數據存儲在本地，無雲端依賴
- **可擴展性**：通過 adapter 模式準備好雲端擴展

## ✨ 核心功能

- **意圖提取**：自動從用戶消息中提取意圖和主題
- **Playbook 執行**：基於意圖執行多步驟工作流（playbooks）
- **Project + Flow 架構**（v2.0）：專案容器內的多 playbook 協作
- **分層記憶系統**：Workspace 核心、專案和成員檔案記憶
- **時間軸視圖**：可視化工作區活動和執行歷史
- **文件處理**：分析和提取上傳文件的內容
- **Port 架構**：為未來雲端擴展提供清晰的抽象層

## 💡 適合誰用？

Mindscape AI 適合這樣的人：

- 常常同時有很多 side project、靈感、長期目標，但很難看清自己現在到底在推哪幾條線
- 想要的不只是「問 AI 一個問題就拿到一個答案」，而是讓 AI 真的理解：你這段時間在忙什麼、想成為什麼樣的人
- 喜歡用一步一步的方式改變生活：每次多一點覺知、多一點有意識的選擇，而不是追求一次性的大翻身

如果你覺得這聽起來像你，Mindscape AI Local Core 提供一個本地優先、開源的實驗空間，讓你打造屬於自己的「心智空間」。

## 🏗️ 架構

### 心智空間架構（三層結構）

Mindscape AI 不是只做一個聊天框，而是圍繞「意圖」設計了三層結構：

1. **Signal Layer — 收集一切線索**

   對話、文件、工具回傳、Playbook 執行結果，都會被轉成輕量的 **IntentSignal**，作為系統理解你在「忙些什麼」的底層訊號。

2. **Intent Governance Layer — 幫你整理主線**

   Signal 會被收斂成 **IntentCard**（長期意圖）與 **短期任務**，並聚成 **IntentCluster**（專案／主題）。這一層就是所謂的「心智空間」，負責維護你的工作與生活主線。

3. **Execution & Semantic Layer — 真的去幹活**

   當某條 Intent 準備好，就交給 Playbook、工具、以及各種語意引擎去執行，包含 RAG 查詢、文件生成、跨工具自動化工作流等。

### 技術架構

Mindscape AI Local Core 使用 **Port/Adapter 模式**（六邊形架構）來維護清晰的邊界：

- **核心領域**：ExecutionContext、Port 介面、核心服務
- **本地適配器**：單用戶、單工作區的實現
- **無雲端依賴**：核心完全獨立於雲端/租戶概念

此外，`mindscape-ai-local-core` 引入了基於 Playbook 的工作流層：

- 面向人類對話的 **Workspace LLM**
- 執行多步驟工作流的 **Playbook LLM + 工作流運行時**（`playbook.run = playbook.md + playbook.json`）

### Project + Flow + Sandbox 架構（v2.0）

從 v2.0 開始，Mindscape AI 引入了**基於專案的協作模型**：

- **Workspace**：團隊/客戶的長期協作房間
- **Project**：交付級別的容器，有自己的生命週期（open, closed, archived）
- **Playbook Flow**：多 playbook 協調，包含依賴關係解析
- **Project Sandbox**：專案內所有 playbook 共享的統一檔案空間
- **分層記憶**：Workspace 核心、專案和成員檔案記憶

**核心創新**：專案從對話中自然產生。當對話顯示需要專案時，系統會自動建議創建專案，讓多個 playbook 協作完成同一個交付物。

詳見 [架構文檔](./docs/architecture/) 和 [核心架構文檔](./docs/core-architecture/)。

## 🚀 快速開始

### 選項 1：Docker 部署（推薦）

最簡單的開始方式是使用 Docker：

```bash
# 克隆倉庫
git clone https://github.com/HansC-anafter/mindscape-ai-local-core.git
cd mindscape-ai-local-core

# （可選）創建 .env 文件並添加你的 API keys
# 你也可以在啟動服務後通過網頁介面配置 API keys
cp .env.example .env
# 編輯 .env 並添加你的 OPENAI_API_KEY 或 ANTHROPIC_API_KEY

# 啟動所有服務
docker compose up -d

# 查看日誌
docker compose logs -f
```

訪問應用：
- **前端**：http://localhost:3001（Docker 部署，類生產環境）
- **後端 API**：http://localhost:8000
- **API 文檔**：http://localhost:8000/docs

詳見 [Docker 部署指南](./docs/getting-started/docker.md)。

### 選項 2：手動安裝

#### 前置需求

- Python 3.9+
- Node.js 18+（用於前端）
- SQLite（Python 已包含）

#### 安裝

```bash
# 克隆倉庫
git clone https://github.com/HansC-anafter/mindscape-ai-local-core.git
cd mindscape-ai-local-core

# 安裝後端依賴
cd backend
pip install -r requirements.txt

# 安裝前端依賴
cd ../web-console
npm install
```

#### 運行

```bash
# 啟動後端（從 backend 目錄）
uvicorn app.main:app --reload

# 啟動前端（從 web-console 目錄，在新終端）
cd web-console
npm run dev
```

訪問 `http://localhost:3000` 來使用網頁介面（本地開發伺服器，前端 `npm run dev`）。

更詳細的設置指南，請參見 [QUICKSTART.md](./QUICKSTART.md) 或 [安裝指南](./docs/getting-started/installation.md)。

## 📚 文檔

### 開始使用
- [快速開始](./docs/getting-started/quick-start.md) - 安裝和設置指南
- [Docker 部署](./docs/getting-started/docker.md) - 使用 Docker Compose 部署
- [安裝指南](./docs/getting-started/installation.md) - 手動安裝說明

### 核心概念
- [心智空間算法](./docs/mindscape-algorithm.md) - 核心理念與三層架構
- [Mindscape AI 官網](https://mindscapeai.app) - 完整技術白皮書與理念介紹（即將推出）

### 技術架構
- [架構概覽](./docs/architecture/port-architecture.md) - 系統架構與設計模式
- [Playbooks 與多步驟工作流](./docs/architecture/playbooks-and-workflows.md) - Playbook 架構與工作流執行
- [記憶與意圖架構](./docs/architecture/memory-intent-architecture.md) - 事件、意圖和記憶層設計
- [本地/雲端邊界](./docs/architecture/local-cloud-boundary.md) - 架構分離原則
- [執行上下文](./docs/architecture/execution-context.md) - 執行上下文抽象

### 核心架構（v2.0）
- [核心架構文檔](./docs/core-architecture/README.md) - Project + Flow + Sandbox 架構

## 🧩 Port 架構

本地核心（`mindscape-ai-local-core`）使用 Port 介面來實現清晰的分離：

- **IdentityPort**：獲取執行上下文（本地適配器返回單用戶上下文）
- **IntentRegistryPort**：將用戶輸入解析為意圖（本地適配器使用 LLM）
- **PlaybookExecutorPort**：執行 Playbook 運行（`playbook.run = md + json`），針對本地或遠程工作流運行時（✅ 已實現）

**未來計劃**：
- 為 playbook 訂製情境 UI 面板

未來的雲端擴展可以實現這些 Port，而無需修改核心代碼。

詳見 [Port 架構](./docs/architecture/port-architecture.md)。

## 🔬 給開發者 / 研究者

Mindscape AI 把自己定位在「**intent-first 的 LLM agent 架構**」：

* 受 Conceptual Spaces & Cognitive Maps 啟發，我們把 IntentCard / IntentCluster 視為一張可導航的 **意圖地圖**。
* 受 BDI 與階層式強化學習（options）啟發，我們把 Intent Layer 視為高階決策層，Playbook 與執行引擎則專心做執行。
* 受 Active Inference 啟發，我們把使用者的偏好與長期目標，收斂成一組能引導「下一步最值得做什麼」的偏好分佈。

如果你對這些主題有興趣，可以參考 [Mindscape AI 官網](https://mindscapeai.app) 了解完整設計與技術白皮書（即將推出）。

## 🤝 貢獻

我們歡迎貢獻！請參見 [CONTRIBUTING.md](./CONTRIBUTING.md) 了解指南。

## 📧 聯絡與社群

維護者：[Hans Huang](https://github.com/HansC-anafter)

- 🐞 **錯誤報告或功能請求**
  → 請開啟 [GitHub Issue](/issues)。

- 💬 **問題 / 想法 / 分享使用案例**
  → 使用 [GitHub Discussions](/discussions)（推薦）。

- 🤝 **合作與商業使用**（代理商、團隊、硬體合作夥伴等）
  → 聯絡：`dev@mindscapeai.app`

> 請避免將支持請求發送到個人電子郵件或社交媒體。

> 使用 Issues/Discussions 有助於整個社群從答案中受益。

## 📄 授權

本專案採用 MIT 授權 - 詳見 [LICENSE](./LICENSE)。

## 🔗 相關專案

- **Mindscape AI Cloud**（私有）：基於此核心構建的多租戶雲端版本
- **Mindscape WordPress Plugin**：Mindscape AI 的 WordPress 整合

## 📝 狀態

這是 Mindscape AI 的**開源、僅本地版本**。雲端 / 多租戶功能通過單獨的倉庫提供，不包含在此版本中。

---

**由 Mindscape AI 團隊用 ❤️ 構建**

