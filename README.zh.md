# Mindscape AI Local Core

> **開源、本地優先、人類可治理的 AI 工作空間 —— 思維可視化工作流引擎**

[English](README.md) | [中文](README.zh.md)

`mindscape-ai-local-core` 是 **Mindscape AI** 的開源核心 —— 一個**本地優先**、**人類可治理**的 AI 工作空間。

它把你的長期意圖、專案主線、創作主題，整理成一個**可治理、可導航的心智空間（mindscape）**，讓 LLM 不再只是回應單一 prompt，而是**圍繞你的長線專案一起思考與行動** —— 並且每個產出都可追溯、可回滾、可人為介入。

### 🎯 兩個核心原則

| 原則 | 意義 |
|------|------|
| **本地優先 (Local-first)** | 資料留在你的機器上。可離線運作。你擁有一切。 |
| **人類可治理 (Human-governable)** | 每個 AI 產出都可追溯、可版本化、可回滾。你保有控制權。 |

> 多數 AI 工具專注在「把事情做完」。Mindscape AI 專注在**治理事情怎麼被做** —— 讓你能在**片段層級**追溯、比較、回滾任何 AI 生成的內容。

### 🎨 Mind-Lens：輸出的調色盤

> **Mind-Lens 是一個「渲染用的調色盤」** —— 一個由使用者定義的控制介面，把價值觀、美學偏好、工作風格**投射**到 AI 執行中。它不是「代表你」，而是幫你**在各種工作流中一致地導演輸出**。

Mind-Lens 採用**三層疊加**的設計：

1. **Global Preset（全域預設）** — 你的常態調色盤（你這個人/品牌大致長什麼樣）
2. **Workspace Override（工作區覆寫）** — 專案級的調整（同一個人，不同情境的偏移）
3. **Session Override（本次覆寫）** — 這輪任務的臨時旋鈕（對話結束後回彈）

無論是 **Mindscape Graph（作者模式）** 還是 **Workspace 執行（運行模式）**，都在操作同一份 Lens 合約 —— 只是編輯的作用域不同。

---

### 🤖 Mindscape Assistant（默默 AI）

> **默默 AI 是你心智空間裡的常駐協作者** —— 它檢查配置、整理資訊、協調你的 AI 工具。但它不替你做決定，不代表你發言。控制權始終在你手上。

**三個「不」**：

| 邊界 | 意義 |
|------|------|
| ❌ **不替你做決定** | 默默會提出選項和建議，但每個最終決定都由你來做。 |
| ❌ **不代表你發言** | 默默會起草內容，但不會在沒有你明確批准的情況下發布或發送任何東西。 |
| ❌ **不聲稱是你的延伸** | 默默明確是一個 AI 助手，而不是你身份的延伸。 |

**默默做什麼**：
- **配置協助 (Configuration Assistance)**：系統設定的健康檢查、驗證與提醒
- **資訊整理 (Information Organization)**：將你的意圖、Playbook、知識整理成可導航的結構
- **工具協調 (Tool Coordination)**：代你協調其他 AI 工具與服務

這個設計哲學確保 Mindscape AI 始終是一個**治理優先**的平台，讓人類保有真正的控制權。

---

## 🧠 AI 驅動的思維可視化工作流

Mindscape AI 並不是一個「打一句話 → 回一句話」的 chat app，而是一套 **AI 驅動的思維可視化工作流**：

> **Signal → Intent Governance → Mind-Model VC → Project/Flow → Playbooks → Sandbox → Memory**

1. **收攏你的心智空間**

   - 把人生主題、長期專案、反覆出現的工作，變成工作區裡的 **Intent 卡片** 和 **Project**。

2. **版本控管你的心智狀態**

   - **Mind-Model VC** 將你願意提供的線索整理成可回顧、可調整、可回滾的心智狀態配方，並保留版本歷史。詳見 [Mind-Model VC 架構](./docs/core-architecture/mind-model-vc.md)。

3. **為每個 Intent 接上 Playbook**

   - 透過可讀又可執行的 **Playbook（Markdown + YAML）**，描述「AI 小隊應該怎麼幫你」。

4. **讓 AI 小隊實際跑起來、看得見過程**

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

## 🔌 Skills 與 MCP 兼容性

Mindscape AI 原生支援 **Agent Skills 開放標準** 與 **Model Context Protocol (MCP)**，確保與更廣泛的 AI 生態系統兼容：

### 這意味著什麼

| 標準 | 整合程度 |
|-----|---------|
| **Agent Skills** | SKILL.md 索引、語意搜尋、格式轉換 |
| **MCP** | 原生 MCP Server + IDE Bridge + 伺服器端 Sampling |
| **LangChain** | LangChain 生態系統的工具適配器 |

### MCP Gateway 架構

**MCP Gateway**（`mcp-mindscape-gateway/`）透過 MCP 協議將 Mindscape 能力暴露給外部 AI 工具：

| 元件 | 職責 |
|------|------|
| **MCP Gateway** | TypeScript MCP 伺服器，向 Claude Desktop、Cursor 等暴露工具 |
| **MCP Bridge** | 後端 API（`/api/v1/mcp/*`），提供同步聊天、意圖提交、專案偵測 |
| **Event Hook Service** | 冪等的副作用執行器，具備治理不變量（事件化、冪等、回執驗證、政策閘門） |
| **Sampling Gate** | 伺服器端向 IDE 發起的 LLM 呼叫，三層降級（Sampling -> WS LLM -> 待處理卡片） |

核心能力：
- **回執驗證覆蓋**：IDE 提供已驗證的執行回執，可跳過冗餘的 Hook 執行
- **MCP Sampling**：伺服器透過 `createMessage()` 向 IDE 的 LLM 發送結構化提示，降低 WS 端 LLM 成本
- **安全控制**：範本白名單、每 Workspace 頻率限制、PII 去識別化

詳見 [MCP Gateway 架構](./docs/core-architecture/mcp-gateway.md)。

### Mindscape 的定位：Skill-compatible Workflow Layer

> **Skills = Leaf Node**（可移植的能力模組）
> **Playbooks = Graph**（編排層：DAG、狀態、復原、人類審批、成本護欄）

Skills 定義 AI **能做什麼**，而 Mindscape Playbooks 定義這些能力在企業場景中**如何被編排、治理與執行**：

- **Skill 導入 (Skill Intake)**：從 Capability Pack 索引並發現 SKILL.md 檔案
- **格式橋接 (Format Bridging)**：透過 `skill_ir_adapter` 在 SKILL.md 與 Playbook 格式之間轉換
- **治理疊加 (Governance Overlay)**：在 Skills 之上加入 checkpoint/resume、審計軌跡、權限控制
- **多 Skill 編排 (Multi-Skill Orchestration)**：將多個 Skills 組合成具有依賴關係的 DAG 工作流

這意味著你可以從 Anthropic 生態系統匯入 Skills，包裝上 Mindscape 的治理層，並以完整的可追溯性執行它們。

---

## 🤖 外部 Agent 整合 (External Agents Integration)

Mindscape 提供**可插拔架構**來整合外部 AI Agent 於其治理層內：

### 核心特點

- **可插拔適配器**：將新 Agent 放入 `agents/` 目錄，啟動時自動發現
- **統一 API**：所有 Agent 透過 `BaseAgentAdapter` 共享 `execute()` 介面
- **Workspace 沙箱綁定**：所有 Agent 在 Workspace 邊界內的隔離沙箱執行
- **完整可追溯**：所有執行記錄到 Asset Provenance
- **Agent WebSocket**：即時任務派遣通道（`/ws/agent`），支援認證、多客戶端路由、心跳監控和待處理任務佇列

### 🔒 Workspace 沙箱安全

> **關鍵**：所有外部 Agent 執行現已綁定至 Workspace。

```text
<workspace_storage_base>/
└── agent_sandboxes/
    └── <agent_id>/           # 例如 claude_code, langgraph
        └── <execution_id>/   # 每次執行的 UUID
            └── ...           # 所有 Agent 檔案隔離於此
```

| 要求 | 執行 |
|------|------|
| `workspace_id` | **必填** - 缺少則拒絕執行 |
| `workspace_storage_base` | **必填** - 必須配置存儲 |
| 沙箱路徑 | 自動生成，無法手動指定 |

### Agent WebSocket

Agent WebSocket 端點（`/ws/agent`）實現後端與 IDE Agent 之間的即時雙向通訊：

- **HMAC-SHA256 認證**：使用 nonce 挑戰-回應機制
- **多客戶端路由**：支援多個 IDE 客戶端同時連線，任務自動派遣至最佳可用客戶端
- **待處理任務佇列**：客戶端離線時提交的任務會排隊，客戶端重新連線後自動派送
- **心跳監控**：自動清理過期的客戶端連線

### Workspace 協作模式

```text
Workspace A (規劃)    →    Workspace C (Agent 執行區)    →    Workspace B (審核)
   定義 Intent                外部 Agent                    品質檢查
   配置 Lens                  在隔離 sandbox 運行             審核產出
```

這使您可以將一個 Workspace 作為專用的「AI 工人」，而其他 Workspace 處理規劃和審核，全程保持完整治理和審計軌跡。

詳見 [外部 Agent 架構](./docs/core-architecture/external-agents.md)。

---

## ☁️ Cloud Connector（雲端連接器）

Mindscape Local-Core 提供**可插拔的 Cloud Connector** —— 一個通用的 WebSocket 橋接器，將本地實例連接到任何相容的雲端平台：

| 元件 | 職責 |
|------|------|
| **CloudConnector** | 管理 WebSocket 連線，支援自動重連與指數退避 |
| **TransportHandler** | 處理執行請求（playbook、tool、chain）並回報事件、用量和錯誤 |
| **MessagingHandler** | 接收雲端連接通道的訊息事件，派發給本地 Agent 處理 |
| **HeartbeatMonitor** | 維持連線活躍，偵測斷線 |

### 設計原則

- **平台無關**：連接器定義的是傳輸協議，不繫結特定雲端供應商。任何實作此協議的平台都能連接。
- **裝置身份**：每個 local-core 實例擁有持久的裝置 ID；認證使用裝置 token。
- **雙向通訊**：雲端可派發執行請求至 local-core；local-core 回報事件和結果。
- **優雅降級**：雲端連線中斷時，local-core 繼續獨立運作，並自動重連。

### 連線流程

```text
Local-Core                        雲端平台
    │                                  │
    ├── GET /device-token ────────────►│  （認證）
    │◄── token ────────────────────────┤
    │                                  │
    ├── WebSocket connect ────────────►│  （持久連線）
    │◄── execution_request ────────────┤  （雲端 → 本地）
    ├── execution_event ──────────────►│  （本地 → 雲端）
    ├── usage_report ─────────────────►│  （計量）
    │◄── messaging_event ──────────────┤  （通道訊息）
    ├── messaging_reply ──────────────►│  （回覆）
    └───────────────────────────────────┘
```

詳見 [Cloud Connector 架構](./docs/core-architecture/cloud-connector.md)。

---

## ⚙️ 執行環境 (Runtime Environments)

Mindscape 支援**多執行環境** —— 獨立的後端，Playbook 和工具可在其中執行：

| 執行環境 | 說明 |
|---------|------|
| **Local-Core**（內建） | 你機器上的預設執行環境，永遠可用 |
| **雲端執行環境** | 透過 Cloud Connector 連接的遠端執行環境（如 GPU 伺服器、專用服務） |
| **使用者自訂執行環境** | 透過 Settings UI 或 API 新增的自訂執行環境 |

### Runtime Environment API

- `GET /api/v1/runtime-environments/` — 列出所有已註冊的執行環境
- `POST /api/v1/runtime-environments/` — 註冊新的執行環境
- `GET /api/v1/runtime-environments/{id}` — 取得執行環境詳情
- `PUT /api/v1/runtime-environments/{id}` — 更新執行環境配置
- `DELETE /api/v1/runtime-environments/{id}` — 移除執行環境
- `POST /api/v1/runtime-environments/scan` — 自動掃描本地資料夾以發現執行環境配置

每個執行環境可配置認證方式、能力旗標（`supports_dispatch`、`supports_cell`）和狀態指示。Capability Pack 可以註冊**設定擴充面板**，出現在「執行環境」設定頁面中。

---

## 🛡️ 人類治理層 (Human Governance Layer)

不同於一般專注在「執行」的 AI 自動化工具，Mindscape AI 在執行之上提供了一個**治理層**：

| 層級 | 治理什麼？ | 核心能力 |
|------|-----------|----------|
| **意圖治理 (Intent)** | 「為什麼要做這個？」 | 意圖版本化、成功標準、禁止事項 |
| **視角治理 (Lens)** | 「AI 該怎麼表現？」 | Mind-Lens 版本化、A/B 測試、風格一致性 |
| **信任治理 (Trust)** | 「這個執行安全嗎？」 | 預檢查、風險標籤、審計軌跡 |
| **資產治理 (Asset)** | 「這個內容怎麼演化的？」 | 片段級溯源、Take/Selection 回滾 |

這意味著你永遠可以回答：
- **「AI 為什麼這樣說？」** → 追溯到 Intent + Lens + 編譯後的 prompt
- **「能不能回到上週的版本？」** → 片段層級的回滾，不只是檔案層級
- **「改了什麼？」** → Diff Intent v1.1 vs v1.2、Lens A vs B

詳見 [治理決策與風控層](./docs/core-architecture/governance-decision-risk-control-layer.md)。

---

## 🧩 核心概念一覽

* **Mindscape（心智空間 / 工作區）**：你正在運作的心智舞台，放專案、Intent、執行軌跡。
* **Intent（意圖卡）**：把「我現在想完成什麼」變成可追蹤的卡片，幫 LLM 將對話錨定在你的長期目標上。**可版本化、可回滾。**
* **Mind-Lens**：AI 輸出的調色盤；控制語調、風格、行為。**可版本化、可組合、可 A/B 測試。**
* **Mind-Model VC（心智建模版本控管）**：心智模型的版本控管系統；將使用者提供的線索整理成可回顧、可調整、可回滾的心智狀態配方，並保留版本歷史。詳見 [Mind-Model VC 架構](./docs/core-architecture/mind-model-vc.md)。
* **Project（專案）**：把相關的 Intent 與 Playbook 收攏在一起，例如一個產品發佈、一整年的寫書計畫、一個客戶帳號。
* **Playbook**：同時給人看、也給機器跑的工作流腳本（Markdown + YAML frontmatter），是能力的載體。
* **治理層 (Governance Layer)**：意圖、視角、信任治理，確保每個 AI 行動都可追溯、可控制。
* **Port/Adapter 架構**：核心與外部集成的清晰分離，實現本地優先設計並支援可選的雲端擴展。
* **[事件、意圖治理與記憶架構](./docs/core-architecture/memory-intent-architecture.md)**：事件、意圖分析與長期記憶如何協作。

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

在大多數 AI 工具仍停留在「聊天 + 單次工具呼叫」的情境下，`mindscape-ai-local-core` 專注在**長期專案、可視化思考、人類可治理的 AI 工作流**。它更接近一個 **AI 工作流作業系統**，而不是單純的 chat 機器人 —— 內建治理機制讓你可以追溯、版本化、回滾任何 AI 產出。

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

### 一行指令安裝（推薦）

最快的安裝方式，一個指令搞定所有事：

**Linux/macOS:**
```bash
curl -fsSL https://raw.githubusercontent.com/HansC-anafter/mindscape-ai-local-core/master/install.sh | bash
```

**Windows PowerShell:**
```powershell
# 如有需要請以管理員身份執行
irm https://raw.githubusercontent.com/HansC-anafter/mindscape-ai-local-core/master/install.ps1 | iex
```

這會自動：
1. Clone 倉庫
2. 安裝所有依賴
3. 啟動所有服務（包含 Device Node）
4. 開啟網頁控制台

> **自訂目錄名稱**：加上 `--dir 我的專案`（Linux/Mac）或 `-Dir 我的專案`（Windows）

### 使用 Docker 快速啟動

最簡單的方式是使用 Docker Compose。**克隆後即可立即啟動** - API 金鑰是可選的，可以稍後透過網頁介面配置。

**Windows PowerShell:**
```powershell
# 1. 導航到用戶目錄（不要在 system32 或 Program Files 目錄下）
cd C:\Users\$env:USERNAME\Documents
# 或：cd C:\Projects

# 2. 克隆倉庫（這會創建 mindscape-ai-local-core 資料夾）
git clone https://github.com/HansC-anafter/mindscape-ai-local-core.git

# 3. 進入專案目錄（現在您已經在專案根目錄了）
cd mindscape-ai-local-core

# 4. 啟動所有服務（包含 Docker 健康檢查）
# 如果遇到執行策略錯誤，請執行：
#   powershell -ExecutionPolicy Bypass -File .\scripts\start.ps1
.\scripts\start.ps1
```

> **💡 提示**：執行 `cd mindscape-ai-local-core` 後，您已經在專案根目錄了。不要再執行一次 `cd mindscape-ai-local-core`！

**Linux/macOS:**
```bash
# 1. 克隆倉庫
git clone https://github.com/HansC-anafter/mindscape-ai-local-core.git
cd mindscape-ai-local-core

# 2. 啟動所有服務（包含 Docker 健康檢查）
./scripts/start.sh
```

**或手動執行:**
```bash
# 1. 克隆倉庫
git clone https://github.com/HansC-anafter/mindscape-ai-local-core.git
cd mindscape-ai-local-core

# 2. 啟動所有服務
docker compose up -d

# 3. 訪問網頁控制台
# 前端：http://localhost:8300
# 後端 API：http://localhost:8200
```

> **💡 提示**：API 金鑰（OpenAI 或 Anthropic）在初始啟動時是**可選的**。系統可以在沒有 API 金鑰的情況下成功啟動，您可以稍後透過網頁介面配置它們。在配置 API 金鑰之前，某些 AI 功能將不可用。

詳細說明請參考：
- **Docker 部署** – [Docker 部署指南](./docs/getting-started/docker.md)
- **手動安裝** – [安裝指南](./docs/getting-started/installation.md)
- **快速開始** – [快速開始指南](./QUICKSTART.md)
- **故障排除** – [故障排除指南](./docs/getting-started/troubleshooting.md) - 常見問題和解決方案

### ⚠️ 重要：PostgreSQL 環境變數配置（必須）

**Sonic Space 能力需要 PostgreSQL**（用於向量儲存和音訊資產管理）。以下環境變數**必須配置**：

| 環境變數 | 預設值 | 說明 | 狀態 |
|---------|--------|------|------|
| `POSTGRES_HOST` | `postgres` | PostgreSQL 服務主機名 | ✅ docker-compose.yml 已配置 |
| `POSTGRES_PORT` | `5432` | PostgreSQL 端口 | ✅ docker-compose.yml 已配置 |
| `POSTGRES_DB` | `mindscape_vectors` | 資料庫名稱 | ✅ docker-compose.yml 已配置 |
| `POSTGRES_USER` | `mindscape` | 資料庫用戶名 | ✅ docker-compose.yml 已配置 |
| `POSTGRES_PASSWORD` | `mindscape_password` | 資料庫密碼 | ⚠️ **生產環境請修改** |

**⚠️ 如果未配置**：
- `engine_postgres` 會初始化為 `None`
- 所有 Sonic Space API 會返回 503 錯誤
- 應用可以啟動，但 Sonic Space 功能不可用
- 啟動日誌會顯示錯誤訊息

**驗證 PostgreSQL 配置**：
```bash
# 1. 檢查 PostgreSQL 服務狀態
docker ps | grep postgres

# 2. 檢查環境變數（必須全部存在）
docker exec mindscape-ai-local-core-backend env | grep POSTGRES

# 3. 驗證連接 URL
docker exec mindscape-ai-local-core-backend python3 -c "from app.database.config import get_postgres_url; print(get_postgres_url())"

# 4. 檢查 Engine 初始化狀態
docker exec mindscape-ai-local-core-backend python3 -c "from app.database import engine_postgres; print(f'Engine: {engine_postgres}')"

# 5. 檢查啟動日誌（應該看到 "PostgreSQL engine initialized successfully"）
docker logs mindscape-ai-local-core-backend | grep -i "postgresql engine"
```

**如果 PostgreSQL 未正確配置**：
- 檢查 `docker-compose.yml` 中的 `POSTGRES_*` 環境變數
- 檢查 `.env` 文件（如果使用）
- 檢查 PostgreSQL 服務是否健康：`docker exec mindscape-ai-local-core-postgres pg_isready -U mindscape`

### 🦙 本地模型與 Ollama（推薦）

Mindscape AI 設計為可透過 **Ollama** 使用本地 LLM 完全離線運行。

1. **安裝 Ollama**：從 [ollama.com](https://ollama.com) 下載。
2. **執行模型**：
   ```bash
   ollama run llama3
   ```
3. **連接**：Mindscape 會自動連接你主機上的 Ollama 實例，無需額外設定！

> **💡 提示**：如果使用 Ollama，API 金鑰（OpenAI 或 Anthropic）是**可選的**。系統會優先使用本地模型。

啟動完成之後，你可以：

1. 在瀏覽器開啟 web console。
2. 建立一個工作區與第一個 **Project**（例如「2026 年寫書計畫」）。
3. 在該 Project 底下新增幾張 **Intent 卡**。
4. 觸發或掛載一個 **Playbook**（如 `daily_planning` 或 `content_drafting`），讓 AI 小隊開始運作。
5. 檢視執行軌跡和產出的 Artifacts。

### 🔄 更新

1. **拉取最新程式碼**：
   ```bash
   cd mindscape-ai-local-core
   git pull origin master
   ```

2. **重新建置並啟動服務**：
   ```bash
   docker compose up -d --build
   ```

3. **確認更新成功**：
   - 檢查日誌是否有錯誤：`docker compose logs backend`
   - 資料庫 schema 遷移會在啟動時自動執行
   - 如果你之前使用 SQLite（PostgreSQL 之前的版本），資料會在首次啟動時**自動遷移**到 PostgreSQL

**注意**：資料庫遷移是自動且冪等的，只會新增缺少的欄位，不影響現有資料。SQLite 資料遷移也是自動的 —— 你的設定、工作區和所有配置都會被保留。如果自動遷移遇到問題，可以手動執行遷移腳本：
```bash
docker compose exec backend python /app/backend/scripts/migrate_all_data_to_postgres.py
```
如有其他問題，請參考[故障排除指南](./docs/getting-started/troubleshooting.md)。

---

## 📚 文檔

### 開始使用
- [快速開始](./docs/getting-started/quick-start.md) - 安裝和設置指南
- [Docker 部署](./docs/getting-started/docker.md) - 使用 Docker Compose 部署
- [安裝指南](./docs/getting-started/installation.md) - 手動安裝說明
- [故障排除](./docs/getting-started/troubleshooting.md) - 常見問題和解決方案

### 核心概念
- [心智空間算法](./docs/mindscape-algorithm.md) - 核心理念與三層架構

### 架構文檔
- [架構文檔](./docs/core-architecture/README.md) - 完整系統架構，包括：
  - Port/Adapter 架構
  - 記憶與意圖架構
  - Mind-Model VC 架構
  - 執行上下文
  - 本地/雲端邊界
  - Playbooks 與工作流（包含身份治理與權限控管）
  - Project + Flow + Sandbox（v2.0）
  - [MCP Gateway 架構](./docs/core-architecture/mcp-gateway.md) - MCP Bridge、Event Hooks、Sampling Gate
  - [Cloud Connector 架構](./docs/core-architecture/cloud-connector.md) - WebSocket 橋接、傳輸、訊息處理
  - [執行環境架構](./docs/core-architecture/runtime-environments.md) - 多執行環境管理

### Playbook 開發
- [Playbook 開發](./docs/playbook-development/README.md) - 建立與擴展 Playbook
- 想了解 Playbook 在系統內的完整設計與運作方式，可以參考：[Playbooks 與多步驟工作流架構](./docs/core-architecture/playbooks-and-workflows.md)

---

## 🔗 相關專案

* **Mindscape AI Cloud**（私有）：基於此核心構建的多租戶雲端版本。
* **Mindscape WordPress Plugin**：Mindscape AI 的 WordPress 整合。

---

## 📦 Capability Packs（能力包）

Mindscape AI 支援 **Capability Packs** —— 自包含的擴充套件：

- **Playbooks**：工作流定義
- **Tools**：可執行的功能函式
- **Services**：背景服務
- **Bootstrap hooks**：自動初始化鉤子
- **設定擴充面板**：注入到 Settings 頁面的 UI 面板（如執行環境配置）

### Capability 熱更新

Capability Pack 可以**不重啟後端**即安裝和更新：

- 透過 `ENABLE_CAPABILITY_HOT_RELOAD=1` 開啟功能旗標
- 以執行緒安全方式移除舊 Pack 路由、重新載入能力註冊表、重新註冊新路由
- 可選的允許清單：`CAPABILITY_ALLOWLIST` 環境變數
- 可透過程式觸發，或在雲端部署新 Pack 時透過 Cloud Connector 觸發

詳見 [Capability Pack 開發指南](./docs/capability-pack-development-guide.md)。

---

## 🖥️ Device Node（設備節點）

**Device Node** 是一個輕量級的 sidecar 程序，與後端一起運行，提供系統層級操作：

- **HTTP Transport**：暴露本地 HTTP API，用於健康檢查和系統命令
- **Docker 管理**：以程式化方式重啟容器（例如安裝 Capability Pack 後）
- **服務協調**：與啟動腳本（`scripts/start.sh`、`scripts/start.ps1`）協作，編排多容器環境

Device Node 會由一行安裝指令和 `scripts/start.sh` / `scripts/start.ps1` 啟動腳本自動啟動。

---

### 2025-12 系統演進說明

截至 2025 年 12 月，local-core 已完成一輪針對 **能力檔＋分段換模型** 的重構，並穩定了各階段之間的中間表示（IR）：

- 核心階段（意圖分析、工具候選篩選、規劃、安全寫入／工具呼叫）現在都輸出 **固定結構的 JSON**，而不是臨時拼接的文字。
- 模型選擇不再寫死在 Playbook 或程式碼裡，而是透過高階的 **能力檔（Capability Profile）** 來表達。

這是一個偏「架構級」的里程碑：它本身不直接新增前端介面，但讓 local-core 更容易擴充，也更容易在其他倉庫中掛上遙測／治理層，而不會破壞既有工作區。

---

## 📝 狀態

這是 Mindscape AI 的 **開源、本地優先、人類可治理** 版本：

* ✅ 適合：本地實驗、個人工作流、代理商內部沙盒、**品牌內容治理**。
* ✅ 內建：意圖治理、Lens 版本化、執行軌跡、片段級溯源。
* 🚧 雲端 / 多租戶功能：透過其他倉庫提供，**不包含在此版本中**。

---

**由 Mindscape AI 團隊用 ❤️ 構建**
