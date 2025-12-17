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

### 🧱 可交換的「思維模組」，不只為 Cloud 預留

雖然這個 repo 叫做 *local-core*，但它並不限於「一台機器上的一個使用者」。

這裡的幾個核心概念 —— **Playbook**、**AI Team Member**、**Mind-Lens / Workspace Profile** ——
其實都被設計成可以交換、匯入、重用的 **思維模組**：

- 你可以為自己建立各種 Playbook、AI 角色與 Mind-Lens 設定。
- 也可以匯入別人公開的 Playbook / AI 團隊預設（例如從 GitHub、未來的套件 / Marketplace）。
- 一組 `AI Team Member + Mind-Lens + Playbooks` 可以被打包成某個領域的「工具包」
  （例如「寫書夥伴」、「SEO 顧問」、「設計顧問」）。

目前在 local-core 裡實作的 **身份與作用域模型**（owner_type、visibility、`effective_playbooks`）
就是用來支撐這種「交換 + 治理」的基礎：

- 在本地模式，它幫助你分清楚哪些是系統內建、哪些是 workspace 專用、哪些是你個人專用的 workflow。
- 當你匯入外部 Playbook 時，可以標記為 `external_provider`，當成範本使用或 fork 成自己的版本。
- 一旦進入 Cloud / 多租戶部署，同一套模型會自然延伸到租戶 / 團隊 / 共用模板的情境。

換句話說，`mindscape-ai-local-core` 定義的是一套用來承載「長期專案 + 可交換工作流」的世界觀。
Mindscape AI Cloud 只是其上一種可能的 SaaS 實作；其他開發者同樣可以在這個核心上，
發展自己的 Cloud / 商業版本。

---

## 🧩 核心概念一覽

* **Mindscape（心智空間 / 工作區）**：你正在運作的心智舞台，放專案、Intent、執行軌跡。
* **Intent（意圖卡）**：把「我現在想完成什麼」變成可追蹤的卡片，幫 LLM 將對話錨定在你的長期目標上。
* **Project（專案）**：把相關的 Intent 與 Playbook 收攏在一起，例如一個產品發佈、一整年的寫書計畫、一個客戶帳號。
* **Playbook**：同時給人看、也給機器跑的工作流腳本（Markdown + YAML frontmatter），是能力的載體。
  Playbook 不只是「可以跑的腳本」，在 local-core 中就已具備基本的歸屬與作用域邊界；在雲端版本會進一步延伸到租戶、團隊等層級，讓不同使用者、專案、租戶之間的 workflow 可以被治理。
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

在大多數 AI 工具仍停留在「聊天 + 單次工具呼叫」的情境下，`mindscape-ai-local-core` 專注在**長期專案、可視化思考、可治理的多步驟工作流**，更接近一個 AI 工作流作業系統，而不是單純的 chat 機器人。

Local Core 的重點放在：

* **本地優先的工作區引擎**

  * 透過 Docker 一鍵啟動
  * 所有資料預設保留在你的機器上

* **Playbook 執行核心**

  * YAML + Markdown Playbook（執行規格目前以 JSON 為主，未來可抽象成 YAML）
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

* **能力檔與分段換模型（staged model routing）**

  * 不再只靠一個全域 `chat_model`，而是透過多種 **能力檔（Capability Profile）** 來決定每一個階段用哪一種模型，
    例如：`FAST`、`STANDARD`、`PRECISE`、`TOOL_STRICT`、`SAFE_WRITE` 等。
  * 像 **意圖分析、工具候選篩選、規劃（planning）、安全寫入 / 嚴格工具呼叫** 等不同階段，可以各自使用不同能力檔，
    但彼此之間透過 **固定的 JSON 結構（中間 IR）** 串接。
  * 這讓你可以在不改 Playbook / 控制流程的前提下，更換模型或供應商，只要調整能力檔設定即可。
  * **成本治理**：每個能力檔都設有成本上限（例如 FAST: $0.002/1k tokens、STANDARD: $0.01/1k tokens、PRECISE: $0.03/1k tokens），
    系統會根據任務複雜度自動選擇符合成本限制的模型，在成本與成功率之間取得最佳平衡。

* **架構**

  * Port/Adapter 模式，清晰的邊界分離
  * 執行上下文抽象
  * 三層架構（Signal、Intent Governance、Execution）

雲端 / 多租戶功能透過其他倉庫提供，**不包含在此版本中**；這裡專注在本地核心。

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
  - Playbooks 與工作流（包含身份治理與權限控管）
  - Project + Flow + Sandbox（v2.0）

### Playbook 開發
- [Playbook 開發](./docs/playbook-development/README.md) - 建立與擴展 Playbook
- 想了解 Playbook 在系統內的完整設計與運作方式，可以參考：[Playbooks 與多步驟工作流架構](./docs/core-architecture/playbooks-and-workflows.md)

---

## 🔗 相關專案

* **Mindscape AI Cloud**（私有）：基於此核心構建的多租戶雲端版本。
* **Mindscape WordPress Plugin**：Mindscape AI 的 WordPress 整合。

---

### 2025-12 系統演進說明

截至 2025 年 12 月，local-core 已完成一輪針對 **能力檔＋分段換模型** 的重構，並穩定了各階段之間的中間表示（IR）：

- 核心階段（意圖分析、工具候選篩選、規劃、安全寫入／工具呼叫）現在都輸出 **固定結構的 JSON**，而不是臨時拼接的文字。
- 模型選擇不再寫死在 Playbook 或程式碼裡，而是透過高階的 **能力檔（Capability Profile）** 來表達。

這是一個偏「架構級」的里程碑：它本身不直接新增前端介面，但讓 local-core 更容易擴充，也更容易在其他倉庫中掛上遙測／治理層，而不會破壞既有工作區。

---

## 📝 狀態

這是 Mindscape AI 的 **開源、僅本地版本**：

* ✅ 適合：本地實驗、個人工作流、代理商內部沙盒。
* 🚧 雲端 / 多租戶功能：透過其他倉庫提供，**不包含在此版本中**。

---

**由 Mindscape AI 團隊用 ❤️ 構建**
