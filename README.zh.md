# Mindscape AI Local Core

> **AI 驅動的思維可視化工作流引擎 —— Mindscape AI 的開源、本地版本**

[English](README.md) | [中文](README.zh.md)

`mindscape-ai-local-core` 是 **Mindscape AI** 的開源、本地核心。

它把你的長期意圖、專案主線、創作主題，整理成一個**可治理、可導航的心智空間（mindscape）**，讓 LLM 不再只是回應單一 prompt，而是圍繞你的長線專案一起思考與行動。

---

## 🧠 AI 驅動的思維可視化工作流

Mindscape AI 並不是一個「打一句話 → 回一句話」的 chat app，而是一套 **AI 驅動的思維可視化工作流**：

1. **收攏你的心智空間**

   - 把人生主題、長期專案、反覆出現的工作，變成工作區裡的 **Intent 卡片** 和 **Project**。

2. **為每個 Intent 接上 Playbook**

   - 透過可讀又可執行的 **Playbook（Markdown + YAML）**，描述「AI 小隊應該怎麼幫你」。

3. **讓 AI 小隊實際跑起來、看得見過程**

   - Playbook 執行時會留下 **Execution Trace**、中間筆記與成果，讓思考與決策過程可回顧、可再利用。

這個 repo 就是把上述這些元件（工作區狀態、Intent、Playbook 執行器、AI 角色、工具連結）包成一個可在本機啟動的核心引擎。

---

## 🔄 Project / Playbook Flow：從專案到可重複的工作流

在這個倉庫裡，我們刻意用 **Project / Playbook flow** 作為預設心智模型：

```text
Project  →  Intents  →  Playbooks  →  AI Team Execution  →  Artifacts & Decisions
```

* **Project**：一條較長期的主線，例如「2026 年產品發佈」、「每年為自己寫一本書」、「經營內容工作室」。
* **Intents**：專案底下較具體的目標，例如「整理章節大綱」、「研究競品」、「撰寫募資頁」。
* **Playbooks**：描述 AI 要怎麼幫你的可重複工作流（步驟、角色、工具）。
* **AI Team Execution**：多個 AI 角色（planner / writer / analyst …）協作、調用工具，產生草稿 / 計畫 / 清單。
* **Artifacts & Decisions**：結果被寫回工作區，成為日後可以重用與決策的素材。

內建的系統 Playbook 範例：

* `daily_planning` – 每日規劃與優先順序
* `content_drafting` – 內容 / 文案起稿

你可以新增自己的 Playbook，將個人 workflow、客戶 SOP、代理商服務流程全部變成可複用的 AI 工作流。

---

## 🧩 核心概念一覽

* **Mindscape（心智空間 / 工作區）**：你正在運作的心智舞台，放專案、Intent、執行軌跡。
* **Intent（意圖卡）**：把「我現在想完成什麼」變成可追蹤的卡片，幫 LLM 將對話錨定在你的長期目標上。
* **Project（專案）**：把相關的 Intent 與 Playbook 收攏在一起，例如一個產品發佈、一整年的寫書計畫、一個客戶帳號。
* **Playbook**：同時給人看、也給機器跑的工作流腳本（Markdown + YAML frontmatter），是能力的載體。
* **Port/Adapter 架構**：核心與外部集成的清晰分離，實現本地優先設計並支援可選的雲端擴展。

---

## 📖 想了解更底層的「心智空間算法」？

**心智空間算法（Mindscape Algorithm）** 是這個專案背後的架構理念，用來描述：

* 如何把長期意圖 / 專案主線整理成可治理的「心智空間」
* AI 如何在這個空間裡「看見」你的上下文，而不是只看單一對話

你可以在這裡看到更完整的說明與設計稿：

* [心智空間算法](./docs/mindscape-algorithm.md)
* [架構文檔](./docs/core-architecture/README.md) - 完整系統架構
* Mindscape AI 官網：[https://mindscapeai.app](https://mindscapeai.app)

---

## 📦 這個倉庫包含什麼？

Local Core 的重點放在：

* **本地優先的工作區引擎**

  * 透過 Docker 一鍵啟動
  * 所有資料預設保留在你的機器上

* **Playbook 執行核心**

  * YAML + Markdown Playbook
  * AI 角色、工具與 Execution Trace

* **Project + Flow + Sandbox 架構（v2.0）**

  * Project 生命週期管理
  * 多 Playbook 協調，支援依賴關係解析
  * 每個 Project 的獨立 Sandbox（工作區級隔離）
  * 自動 Artifact 追蹤與註冊

* **工具與記憶層**

  * 向量搜尋與語意能力
  * 記憶 / Intent 架構
  * 工具註冊與執行

* **架構**

  * Port/Adapter 模式，清晰的邊界分離
  * 執行上下文抽象
  * 三層架構（Signal、Intent Governance、Execution）

雲端 / 多租戶 Console（Console-Kit、Site-Hub 等）**不在此倉庫**；這裡專注在本地核心。

---

## 🚀 安裝與快速上手

完整步驟請參考：

1. **安裝與環境需求**： [安裝指南](./docs/getting-started/installation.md)

2. **使用 Docker 啟動**： [Docker 部署指南](./docs/getting-started/docker.md) 或 [快速開始](./docs/getting-started/quick-start.md)

啟動完成之後，你可以：

1. 在瀏覽器開啟 web console。
2. 建立一個工作區與第一個 **Project**（例如「2026 年寫書計畫」）。
3. 在該 Project 底下新增幾張 **Intent 卡**。
4. 觸發或掛載一個 **Playbook**（如 `daily_planning` 或 `content_drafting`），讓 AI 小隊開始運作。
5. 檢視執行軌跡和產出的 Artifacts。

---

## 📚 文檔

### 開始使用
- [快速開始](./docs/getting-started/quick-start.md) - 安裝和設置指南
- [Docker 部署](./docs/getting-started/docker.md) - 使用 Docker Compose 部署
- [安裝指南](./docs/getting-started/installation.md) - 手動安裝說明

### 核心概念
- [心智空間算法](./docs/mindscape-algorithm.md) - 核心理念與三層架構

### 架構文檔
- [架構文檔](./docs/core-architecture/README.md) - 完整系統架構，包括：
  - Port/Adapter 架構
  - 記憶與意圖架構
  - 執行上下文
  - 本地/雲端邊界
  - Playbooks 與工作流
  - Project + Flow + Sandbox（v2.0）

### Playbook 開發
- [Playbook 開發](./docs/playbook-development/README.md) - 建立與擴展 Playbook

---

## 🔗 相關專案

* **Mindscape AI Cloud**（私有）：基於此核心構建的多租戶雲端版本。
* **Mindscape WordPress Plugin**：Mindscape AI 的 WordPress 整合。

---

## 📝 狀態

這是 Mindscape AI 的 **開源、僅本地版本**：

* ✅ 適合：本地實驗、個人工作流、代理商內部沙盒。
* 🚧 雲端 / 多租戶功能：透過其他倉庫提供，**不包含在此版本中**。

---

**由 Mindscape AI 團隊用 ❤️ 構建**
