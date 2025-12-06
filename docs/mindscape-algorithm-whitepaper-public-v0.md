# 心智空間算法技術白皮書

**版本**: v0.9（草稿）
**日期**: 2025-12-05
**維護者**: Mindscape AI 開發團隊
**狀態**: 技術白皮書（公開版）

> **說明**: 本文件是心智空間算法（Mindscape Algorithm）的技術白皮書，面向希望了解 Mindscape AI 架構設計理念的開發者、研究者和合作夥伴。部分理論對齊（例如 Active Inference、變分推論機制）目前作為設計靈感與未來研究方向，尚未在程式碼層完全實作。

---

## 執行摘要

心智空間算法（Mindscape Algorithm）是 Mindscape AI 的核心架構理念，它將使用者的長期意圖、專案主線、創作主題組織成一個可治理、可導航的認知空間，並在此基礎上構建了一整套 LLM Agent 的意圖治理與執行框架。

本文檔從理論根基與架構設計兩個層面，系統性地闡述心智空間算法的設計理念，並與現有的認知科學、AI 架構研究脈絡對齊，為希望在實務中採用 Mindscape AI 的開發者與團隊提供一個可參照的架構藍圖。

---

## 目錄

1. [理論根基](#一理論根基)
   - [1.1 Conceptual Spaces 與認知地圖](#11-conceptual-spaces-與認知地圖)
   - [1.2 BDI 架構與階層式強化學習](#12-bdi-架構與階層式強化學習)
   - [1.3 Active Inference 與自由能原理](#13-active-inference-與自由能原理)
   - [1.4 現代 LLM Agent 架構脈絡](#14-現代-llm-agent-架構脈絡)

2. [架構設計](#二架構設計)
   - [2.1 三層心智空間模型](#21-三層心智空間模型)
   - [2.2 Intent Layer：意圖治理層](#22-intent-layer意圖治理層)
   - [2.3 執行層與語義引擎](#23-執行層與語義引擎)
   - [2.4 雙向數據流與集成模式](#24-雙向數據流與集成模式)

3. [技術對齊與定位](#三技術對齊與定位)
   - [3.1 理論對齊總結](#31-理論對齊總結)
   - [3.2 架構對齊總結](#32-架構對齊總結)
   - [3.3 產品語境與應用場景](#33-產品語境與應用場景)

4. [未來方向](#四未來方向)

5. [參考文獻](#五參考文獻)

6. [附錄](#附錄)
   - [A. 術語表](#a-術語表)
   - [B. 架構圖表](#b-架構圖表)

---

## 一、理論根基

### 1.1 Conceptual Spaces 與認知地圖

#### 1.1.1 Conceptual Spaces 理論

**理論來源**: Peter Gärdenfors 的 Conceptual Spaces 理論（Gärdenfors, 2000, 2014）

**核心主張**:
- 心智是「空間化」地組織經驗，而不是僅以符號（symbol）或純向量（vector）的形式存儲
- 概念被視為在多維「品質維度」（quality dimensions）上的區域
  - 例如：顏色概念在「色相-亮度-飽和度」空間中的區域
  - 例如：味道概念在「酸甜苦鹹鮮」等維度上的分佈
- 概念之間的幾何距離直接代表語義相似度
- 區域的大小與邊界反映概念的範圍與模糊性

**對心智空間算法的映射**:

```
Conceptual Space (理論)
    ↓
Intent Conceptual Space (實作)
    ├─ IntentCard：空間中的節點（具體目標/專案）
    ├─ IntentCluster：空間中的語義區域（主題線/專案線）
    └─ 幾何距離 → 語義相似度 → 意圖治理引擎判斷依據
```

**架構層面的對應**:
- **IntentCard** 作為空間中的節點，每個卡片代表一個具體的長期目標或專案
- **IntentCluster** 作為空間中的語義區域，將相關的 IntentCard 聚合為主題線
- **Embedding 向量** 提供品質維度的數學表示，通過 cosine similarity 計算概念距離
- **意圖治理引擎** 在此空間上執行「收斂與佈局」操作，決定節點的創建、更新、聚合

#### 1.1.2 Cognitive Maps / Cognitive Graphs

**理論來源**: 海馬體認知地圖研究（O'Keefe & Nadel, 1978; Bellmund et al., 2018）

**核心發現**:
- 海馬體不只為物理空間建立導航地圖，也為抽象空間（社會地位、價值、任務結構）建立認知地圖
- 這些 cognitive map / cognitive graph 是人類學習新任務、知識遷移、靈活行為的基礎
- 抽象認知地圖具有與空間導航相似的結構特性：路徑規劃、距離計算、區域劃分

**對心智空間算法的映射**:

```
Cognitive Map (理論)
    ↓
Intent Cognitive Map (實作)
    ├─ 多個 Workspace 對應多個「任務空間」
    ├─ IntentCluster 作為「區域劃分」
    ├─ 執行決策管線作為「路徑規劃」
    └─ 語義執行引擎作為「局部導航引擎」
```

**架構層面的對應**:
- **Mindscape** = 使用者的 Intent Cognitive Map，記錄所有長期目標與專案主線
- **IntentCluster** = 地圖上的「區塊 / subgraph」，將相關意圖聚合為主題線
- **語義執行引擎** = 在這張地圖上動態計算局部區域與路徑的引擎
- **Workspace** = 多個 AI 成員在同一張認知地圖上導航，而非每次都從零開始對話

**理論引用**:
- Gärdenfors, P. (2000). *Conceptual spaces: The geometry of thought*. MIT Press.
- Gärdenfors, P. (2014). *The geometry of meaning: Semantics based on conceptual spaces*. MIT Press.
- Bellmund, J. L. S., Gärdenfors, P., Moser, E. I., & Doeller, C. F. (2018). Navigating cognition: Spatial codes for human thinking. *Science*, 362(6415).

---

### 1.2 BDI 架構與階層式強化學習

#### 1.2.1 BDI 架構：Belief-Desire-Intention

**理論來源**: BDI（Belief-Desire-Intention）Agent 架構（Bratman, 1987; Rao & Georgeff, 1995）

**核心框架**:
- **Beliefs（信念）**: Agent 對世界的認知，包括事實、狀態、歷史記錄
- **Desires（慾望）**: Agent 想達成的目標集合，可能相互衝突或不完整
- **Intentions（意圖）**: 從 Desires 中選出並 commit 的目標子集，代表實際要執行的計畫

**關鍵設計原則**:
- 「選 plan」與「執行 plan」是分離的活動
- Intentions 具有持續性（persistence），一旦 commit 就會持續執行直到達成或失敗
- 需要在資源限制下，從大量 Desires 中選擇有限的 Intentions

**對心智空間算法的映射**:

```
BDI 架構 (理論)
    ↓
Intent Layer (實作)
    ├─ Beliefs ≈ 工作區記憶、事件歷史、語義特徵
    ├─ Desires ≈ IntentSignal（候選意圖集合）
    ├─ Intentions ≈ IntentCard（已確認意圖）
    └─ Plan Execution ≈ Playbook runtime / 語義執行引擎
```

**架構層面的對應**:
- **Beliefs**:
  - Event Layer 記錄所有 message/tool/playbook 歷史
  - Memory/Embedding Layer 存儲穩定成果與重要內容
  - 語義執行引擎提供語義特徵

- **Desires**:
  - IntentSignal 代表候選意圖
  - 允許大量、碎片化，完全內部使用

- **Intentions**:
  - IntentCard 代表已確認並 commit 的長期目標
  - 數量受控，確保系統穩定運行

- **Plan Execution**:
  - 執行決策管線決定「是否啟動 playbook」
  - Playbook runtime / 語義執行引擎負責具體執行

**理論引用**:
- Bratman, M. E. (1987). *Intention, plans, and practical reason*. Harvard University Press.
- Rao, A. S., & Georgeff, M. P. (1995). BDI agents: From theory to practice. *ICMAS*, 95, 312-319.

#### 1.2.2 Hierarchical RL & Options Framework

**理論來源**: 階層式強化學習（Hierarchical Reinforcement Learning）與 Options Framework（Sutton et al., 1999; Bacon et al., 2017）

**核心框架**:
- **Primitive Actions（原子動作）**: 最底層的單步動作
- **Options（選項）**: 帶起點/終點條件的高階動作，可展開為多步驟行為序列
- **Hierarchical Policy**:
  - 高階 policy（meta-controller）選擇哪個 option 要執行
  - 低階 policy（option internal policy）負責 option 內部的動作序列

**關鍵優勢**:
- 解決長期目標、稀疏回饋問題
- 實現行為抽象與重用
- 支持跨任務的知識遷移

**對心智空間算法的映射**:

```
Hierarchical RL / Options (理論)
    ↓
Intent Layer 架構 (實作)
    ├─ High-level Policy ≈ 意圖治理引擎 / 執行決策管線
    ├─ Options ≈ Playbooks（高階行為模板）
    ├─ Option Selection ≈ 決定啟動哪個 Playbook
    └─ Low-level Policy ≈ 語義執行引擎 / Playbook runtime
```

**架構層面的對應**:
- **高階 Policy**:
  - 意圖治理引擎決定哪些 IntentSignal 升級為 IntentCard（意圖治理）
  - 執行決策管線決定是否啟動 playbook（執行決策）

- **Options**:
  - Playbook 作為高階行為模板，對應特定的任務領域（grant proposal writing, course creation 等）
  - 每個 Playbook 可展開為多步驟的 tool calls 與 agent interactions

- **Low-level Policy**:
  - 語義執行引擎作為執行面集群，負責語義理解、RAG、agent 執行
  - Playbook runtime 負責具體的步驟執行與狀態管理

**理論引用**:
- Sutton, R. S., Precup, D., & Singh, S. (1999). Between MDPs and semi-MDPs: A framework for temporal abstraction in reinforcement learning. *Artificial intelligence*, 112(1-2), 181-211.
- Bacon, P. L., Harb, J., & Precup, D. (2017). The option-critic architecture. *AAAI*, 31(1).

---

### 1.3 Active Inference 與自由能原理

#### 1.3.1 Free Energy Principle（自由能原理）

**理論來源**: Karl Friston 的 Free Energy Principle（Friston, 2010）

**核心主張**:
- 有機體（包括大腦）傾向選擇能降低「驚訝/不確定性」的狀態
- 等價於在做變分 Bayesian 推論，持續調整內在模型和行為以最小化預測誤差
- 「自由能」作為變分邊界，同時涵蓋感知（perception）與行動（action）

**關鍵機制**:
- **生成模型（Generative Model）**: 大腦維持一個對世界的內部模型
- **變分推論（Variational Inference）**: 通過調整內部狀態來最小化預測誤差
- **偏好狀態（Preferred States）**: 定義 agent 想待在的狀態、要避免的狀態

#### 1.3.2 Active Inference

**核心框架**:
- 把行為、知覺、學習都視為「在生成模型下最小化變分自由能」的過程
- 用先驗偏好（priors on preferred states）取代傳統 RL 的 reward
- Agent 的行為是在「主動採集信息」與「維持偏好狀態」之間平衡

**對心智空間算法的映射**:

```
Active Inference (理論)
    ↓
心智空間算法 (實作)
    ├─ Preferred States ≈ 長期意圖偏好分佈（IntentCard + IntentCluster）
    ├─ Generative Model ≈ Workspace 對世界的認知（Event + Memory Layer）
    ├─ Variational Inference ≈ 意圖治理引擎的收斂與佈局
    └─ Action Selection ≈ 執行決策管線 + Playbook execution
```

**架構層面的對應**:
- **偏好狀態（Preferred States）**:
  - IntentCard 代表使用者的長期偏好與目標
  - IntentCluster 定義「主題線 / 專案線」的偏好分佈
  - 這些偏好狀態持續更新，反映使用者意圖的演進

- **生成模型（Generative Model）**:
  - Event Layer 記錄世界狀態（對話、工具調用、playbook 執行）
  - Memory/Embedding Layer 提供長期記憶與語義表示
  - 語義執行引擎提供實時的語義理解與聚類

- **變分推論（Variational Inference）**:
  - 意圖治理引擎分析每輪對話，判斷哪些 IntentSignal 應該升級為 IntentCard
  - 使用語義聚類特徵提升判斷準確度
  - 在「減少混亂」與「維持偏好狀態」之間做平衡

- **行動選擇（Action Selection）**:
  - 執行決策管線決定是否啟動 playbook（減少預測誤差）
  - Playbook / 語義執行引擎執行具體動作，採集信息並推進目標

**理論引用**:
- Friston, K. (2010). The free-energy principle: a unified brain theory? *Nature reviews neuroscience*, 11(2), 127-138.
- Friston, K., FitzGerald, T., Rigoli, F., Schwartenbeck, P., & Pezzulo, G. (2017). Active inference: a process theory. *Neural computation*, 29(1), 1-49.

---

### 1.4 現代 LLM Agent 架構脈絡

#### 1.4.1 LLM Agent 標準架構

**當前趨勢**: Planning + Memory + Tool Use + Environment Interaction

**核心組件**:
- **Planning**: 決定下一步要做什麼（如 ReAct, Plan-and-Solve）
- **Memory**: 長期記憶存儲與檢索（如 vector database, reflection）
- **Tool Use**: 調用外部工具與 API
- **Environment Interaction**: 與外部環境交互，獲取反饋

**現有架構示例**:
- **Generative Agents** (Park et al., 2023): LLM + 長期記憶 + 反思來模擬虛擬小鎮中的日常行為
- **AutoGPT / BabyAGI**: 結合規劃、記憶、工具使用的通用 agent 框架
- **LangChain / LlamaIndex**: 提供 Memory、Tool、Agent 的標準抽象

#### 1.4.2 當前痛點

**問題 1: 記憶爆炸、缺乏治理**
- 向量數據庫變成巨大垃圾場，沒有明確的治理策略
- 缺乏對「哪些記憶重要、哪些可以丟棄」的判斷機制

**問題 2: 缺乏清晰的 Goal / Intent 層**
- Planner 難以將「今天在幹嘛」與「長期專案」對齊
- 沒有明確的意圖治理層，導致行為碎片化

**問題 3: 執行與治理耦合**
- 語義理解、執行、意圖治理混在一起，難以擴展與優化

#### 1.4.3 心智空間算法的定位

**核心主張**:

> 心智空間算法 = 我們給 LLM-Agent 多加的一層「Intent-aware Cognitive Map」，負責管理目標、專案主線與記憶，並驅動底下所有語義聚類、RAG、Playbook、工具調用。

**對標準架構的增強**:

```
標準 LLM Agent 架構
    ├─ Planning
    ├─ Memory
    ├─ Tool Use
    └─ Environment Interaction

心智空間算法增強
    ├─ Intent Governance Layer（新增）
    │   ├─ IntentSignal → IntentCard 的生命週期管理
    │   ├─ IntentCluster 主題線聚合
    │   └─ 意圖治理引擎自動收斂與佈局
    ├─ Cognitive Map Layer（新增）
    │   ├─ Intent Cognitive Space（Conceptual Space）
    │   ├─ Intent Cognitive Map（Cognitive Maps）
    │   └─ Preferred States Distribution（Active Inference）
    └─ 驅動標準組件
        ├─ Planning: 執行決策管線決定是否啟動 playbook
        ├─ Memory: Episode Memory 基於 IntentCluster 選擇高價值內容
        ├─ Tool Use: Playbook 定義工具調用序列
        └─ Environment: 語義執行引擎執行語義理解與 agent 任務
```

**理論引用**:
- Park, J. S., O'Brien, J. C., Cai, C. J., Morris, M. R., Liang, P., & Bernstein, M. S. (2023). Generative agents: Interactive simulacra of human behavior. *arXiv preprint arXiv:2304.03442*.
- Weng, L. (2023). LLM-powered autonomous agents. *Lil'Log*. https://lilianweng.github.io/posts/2023-06-23-agent/

---

## 二、架構設計

### 2.1 三層心智空間模型

#### 2.1.1 整體架構圖

```
┌─────────────────────────────────────────────────────────────┐
│                 心智空間算法三層架構                           │
└─────────────────────────────────────────────────────────────┘

Layer 0: Signal Collector (Telemetry Layer)
├─ 意圖抽取器（從對話、文件、工具輸出中提取意圖信號）
├─ 多源信號收集（支持多種信號來源）
└─ Output: IntentSignal
    └─ 允許大量、碎片化，純內部使用

           ↓ (每輪對話後)

Layer 1: Intent Steward LLM (Layout / Governance Layer)
├─ 意圖治理引擎
├─ Input:
│   ├─ 最近對話歷史
│   ├─ 最近 IntentSignal
│   ├─ 當前可見 IntentCard
│   └─ 語義聚類特徵
├─ Output: IntentLayoutPlan
│   ├─ 長期意圖（CREATE/UPDATE IntentCard）
│   ├─ 短期任務（只寫 log）
│   └─ 信號映射（每個 signal 的處理決定）
└─ 自動觸發 + 自動紀錄，不要求用戶逐一確認

           ↓ (週期性，跨輪/跨日)

Layer 2: Embedding Clustering (Cluster / Theme Layer)
├─ 意圖聚類服務
├─ 調用語義執行引擎執行聚類
├─ Output: IntentCluster
│   ├─ cluster label (LLM 命名)
│   ├─ cluster-level metadata
│   └─ 關聯到 IntentCard
└─ 對應「專案 / 主題」分欄
```

#### 2.1.2 三層對應關係

| 理論層面 | 架構層面 | 核心組件 | 數據模型 |
|---------|---------|---------|---------|
| **Signal Layer**<br/>（訊號級） | Layer 0: Signal Collector | 意圖抽取器<br/>語義種子抽取器 | IntentSignal |
| **Layout Layer**<br/>（佈局級） | Layer 1: Intent Steward | 意圖治理引擎 | IntentCard<br/>IntentLayoutPlan |
| **Cluster Layer**<br/>（聚類級） | Layer 2: Embedding Clustering | 意圖聚類服務<br/>語義執行引擎 | IntentCluster |

---

### 2.2 Intent Layer：意圖治理層

#### 2.2.1 設計目標

**核心問題**:
- IntentSignal 爆量（每輪對話可能產生幾十、上百條信號）
- IntentSignal 粒度太細，需要用戶逐一確認，不可行
- 缺乏專職治理層，無法自動收斂與佈局

**解決方案**:
- 承認 IntentSignal 爆量是合理且有價值的，但降級為內部信號
- 引入意圖治理引擎 LLM 作為專職治理層，負責收斂與佈局
- 實現自動化：從「需要用戶逐一確認」改為「自動觸發 + 自動紀錄」
- 建立語義骨架：Embedding 聚類負責跨輪、跨日的 Intent 收斂

#### 2.2.2 架構組件

**組件 1: 意圖抽取器（Intent Extractor）**
- 從對話消息、文件上傳、語義種子任務中提取 IntentSignal
- 創建 IntentSignal 作為候選意圖
- 記錄 metrics：每輪對話的 IntentSignal 數量

**組件 2: 意圖治理引擎（Intent Steward Service）**
- 每輪對話後自動分析，決定 Intent 面板的變化
- 兩階段處理：
  - Stage A: Heuristic + 小模型預篩（減少信號量）
  - Stage B: 大模型意圖治理（輸出 IntentLayoutPlan）
- 使用語義聚類特徵提升判斷準確度

**組件 3: 意圖聚類服務（Intent Cluster Service）**
- 週期性對 IntentCard 進行聚類（每晚 / 每完成大 playbook）
- 調用語義執行引擎執行聚類算法
- 生成 cluster label，回寫到 IntentCard.metadata.cluster_id

**組件 4: 執行決策管線（Intent Pipeline）**
- 保留三層分析邏輯
- Layer 1: Interaction Type (QA / START_PLAYBOOK / MANAGE_SETTINGS)
- Layer 2: Task Domain
- Layer 3: Playbook Selection + 自動觸發 playbook
- **與意圖治理引擎分離**：執行決策管線負責「要不要啟動 playbook」，意圖治理引擎負責「Intent 面板與長期記憶」

#### 2.2.3 平行管線設計

```
┌─────────────────────────────────────────────────────────────┐
│                   兩條平行管線                               │
└─────────────────────────────────────────────────────────────┘

管線 A: Action 決策管線
├─ 執行決策管線分析
│   ├─ Layer 1: Interaction Type
│   ├─ Layer 2: Task Domain
│   └─ Layer 3: Playbook Selection
├─ 回答：「要不要啟動 playbook？啟動哪個？」
└─ 觸發 playbook execution

管線 B: Intent 佈局管線
├─ 意圖治理引擎分析
├─ 回答：「這一輪對話對 Intent 面板造成什麼變化？」
├─ 管理：
│   ├─ 哪些主題升級為 IntentCard
│   ├─ 哪些 IntentCard 狀態/進度要更新
│   └─ 哪些主題是長期專案 vs 短期任務
└─ 自動更新 IntentCard，寫入 intent_logs

兩條管線都吃同一批 events / signals，但輸出完全不同
```

---

### 2.3 執行層與語義引擎

#### 2.3.1 定位與職責

**定位**: 執行面集群（Execution Layer）

**核心職責**:
- **語義理解**: 理解用戶輸入的語義
- **內容聚類**: 對內容進行語義聚類分析
- **上下文管理**: 管理對話上下文
- **Agent 執行**: 執行 Agent 任務

**架構特點**:
- **無狀態執行**: 不存儲配置，依賴傳遞的 payload
- **請求級緩存**: 使用 request-scoped cache 優化性能
- **多輪對話支持**: 支持 Agentic RAG 等多輪調用場景

#### 2.3.2 與 Intent Layer 的關係

**職責分離**:
- **語義執行引擎**: 負責語義計算（聚類、RAG、embedding）
- **Intent Layer**: 負責治理決策（IntentCard 創建/更新、生命週期管理）

**集成方式**:
- 通過明確的 API 接口和數據格式，避免架構耦合
- 支持雙向數據流：IntentCluster → 語義執行引擎（目標導向），語義執行引擎 → 意圖治理引擎（語義特徵）

---

### 2.4 雙向數據流與集成模式

#### 2.4.1 數據流方向

**方向 1: IntentCluster → 語義執行引擎（目標導向）**
- IntentCluster 作為 context gate，驅動語義執行引擎的檢索與聚類
- 提高檢索精準度，只檢索與當前 IntentCluster 相關的內容
- 實現方式：Combo A（IntentCluster 驅動的目標導向選源）

**方向 2: 語義執行引擎 → 意圖治理引擎（語義特徵）**
- 語義執行引擎的對話聚類結果作為意圖治理引擎判斷依據
- 提升 IntentCard 創建/更新的準確度
- 實現方式：Combo B（語意集群作為意圖治理引擎的語義特徵提供者）

**方向 3: Intent Layer ↔ 語義執行引擎（實體引擎）**
- Intent Layer 調用語義執行引擎執行聚類算法
- 統一所有語義聚類的算法實現
- 實現方式：Combo C（語義執行引擎作為 IntentCluster 的實體引擎）

**方向 4: 語義執行引擎 → Memory Layer（長期記憶選擇）**
- 使用語義執行引擎的 episode clustering 決定長期記憶內容
- 提升長期記憶品質
- 實現方式：Combo D（Episode Cluster 決定長期記憶內容）

#### 2.4.2 四種集成模式總覽

| Combo | 數據流方向 | 核心價值 |
|-------|-----------|---------|
| **Combo A** | IntentCluster → 語義執行引擎 | 目標導向選源，提高檢索精準度 |
| **Combo B** | 語義執行引擎 → 意圖治理引擎 | 語義特徵提升判斷準確度 |
| **Combo C** | Intent Layer ↔ 語義執行引擎 | 統一聚類算法實現 |
| **Combo D** | 語義執行引擎 → Memory Layer | 提升長期記憶品質 |

相關實作細節與 API 規範會在公開實作 / SDK 推出時一併釋出。

---

## 三、技術對齊與定位

### 3.1 理論對齊總結

#### 3.1.1 Conceptual Spaces + Cognitive Maps

**理論對齊**:
- 心智空間 = Intent Conceptual Space，IntentCard 是空間中的節點，IntentCluster 是語義區域
- 心智空間算法 = 一套在 conceptual space 上治理意圖節點的規則

**架構對齊**:
- Mindscape = Intent Cognitive Map，記錄所有長期目標與專案主線
- IntentCluster = 地圖上的「區塊 / subgraph」
- 語義執行引擎 = 在這張地圖上動態計算局部區域與路徑的引擎

#### 3.1.2 BDI + Hierarchical RL

**理論對齊**:
- Beliefs ≈ 工作區記憶、事件歷史、語義特徵
- Desires ≈ IntentSignal（候選意圖集合）
- Intentions ≈ IntentCard（已確認意圖）

**架構對齊**:
- Intent Layer = BDI-influenced 意圖治理層
- 意圖治理引擎 / 執行決策管線 = 高階 policy / meta-controller
- 語義執行引擎 / Playbook execution = 低階 controller / option internal policy

#### 3.1.3 Active Inference / Free Energy Principle

**理論對齊**:
- 心智空間算法把使用者的長期偏好、創作主軸、生活目標，收斂成一組持續更新的「意圖偏好分佈」
- Workspace、Playbook、語意集群在這張偏好空間裡，透過 heuristics + LLM 推理，不斷選擇下一個「預期減少混亂、增加價值」的動作

**架構對齊**:
- 心智空間 = 一個包含偏好、世界模型、可行動作的 state space
- 心智空間算法 = 在這個 state space 上做「類 active inference 的決策」

#### 3.1.4 現代 LLM Agent 架構

**理論對齊**:
- 心智空間算法 = 我們給 LLM-Agent 多加的一層「Intent-aware Cognitive Map」
- 負責管理目標、專案主線與記憶，並驅動底下所有語義聚類、RAG、Playbook、工具調用

**架構對齊**:
- Intent Governance Layer（新增）：IntentSignal → IntentCard 的生命週期管理
- Cognitive Map Layer（新增）：Intent Cognitive Space、Intent Cognitive Map、Preferred States Distribution
- 驅動標準組件：Planning、Memory、Tool Use、Environment Interaction

---

### 3.2 架構對齊總結

#### 3.2.1 三層架構對應

| 理論層面 | 架構層面 | 核心組件 | 數據模型 |
|---------|---------|---------|---------|
| Conceptual Space | Intent Cognitive Space | IntentCard, IntentCluster | IntentCard, IntentCluster |
| Cognitive Map | Intent Cognitive Map | 意圖聚類服務 | IntentCluster |
| BDI Intentions | Intent Governance | 意圖治理引擎 | IntentCard |
| HRL Options | Playbook System | 執行決策管線, Playbook runtime | Playbook execution events |
| Active Inference | Preference Distribution | 意圖治理引擎 + IntentCluster | IntentCard + IntentCluster |

#### 3.2.2 雙層執行架構

```
┌─────────────────────────────────────────────────────────────┐
│              雙層執行架構對應                                 │
└─────────────────────────────────────────────────────────────┘

上層：Intent Governance Layer
├─ 意圖治理引擎: 意圖治理與佈局
├─ IntentCluster: 主題線聚合
└─ 執行決策管線: 執行決策（是否啟動 playbook）

下層：Semantic Execution Layer
├─ 語義理解與聚類
├─ RAG 檢索
├─ Agent 執行
└─ 內容分析

集成點：四種集成模式
├─ Combo A: IntentCluster → 語義執行引擎 (目標導向)
├─ Combo B: 語義執行引擎 → 意圖治理引擎 (語義特徵)
├─ Combo C: Intent Layer ↔ 語義執行引擎 (實體引擎)
└─ Combo D: 語義執行引擎 → Memory Layer (長期記憶)
```

---

### 3.3 產品語境與應用場景

#### 3.3.1 對個人創作者 / 教學者

**核心價值**:
> 心智空間算法 = 一套幫你把「生活中所有想做的事」整理成可執行專案主線、並搭配 Playbook 自動化的系統。

**應用場景**:
- **專案管理**: 將分散的任務與想法聚類為主題線（如「Root3 Grinder 日文募資」）
- **自動化工作流**: 通過 Playbook 自動執行重複性任務（如「補助提案寫作」）
- **長期記憶**: 系統自動識別並記錄重要決策點與轉折

**技術亮點**:
- 意圖治理引擎自動收斂碎片化意圖，無需用戶逐一確認
- IntentCluster 自動聚類相關專案，形成主題線
- 語義執行引擎提供精準的語義理解與內容檢索

#### 3.3.2 對團隊 / Agency

**核心價值**:
> 心智空間算法 = 在團隊的所有案件、流程、客戶之上，提供一層可觀測、可治理的「集體意圖地圖」，串起多個 Agent、工具與知識庫。

**應用場景**:
- **案件管理**: 多個案件自動聚類為主題線（如「政府補助提案」、「課程開發」）
- **團隊協作**: 多個 Workspace 共享同一張 Intent Cognitive Map
- **知識沉澱**: 重要決策與成果自動寫入長期記憶，供後續參考

**技術亮點**:
- 跨 Workspace 的 IntentCluster 聚合
- 集體意圖的可觀測性與治理能力
- 多 Agent 協作在同一張認知地圖上導航

#### 3.3.3 對 AI / Developer 社群

**核心價值**:
> 心智空間算法 = 一套 intent-first 的 LLM agent architecture，把目前 LLM agent 的 Planning/Memory/Tool 使用，放進一個有明確心智空間模型的框架中。

**應用場景**:
- **Agent 架構設計**: 提供 Intent Governance Layer 作為標準組件
- **記憶治理**: 解決向量數據庫變成垃圾場的問題
- **目標對齊**: 解決 Planner 難以將「今天在幹嘛」與「長期專案」對齊的問題

**技術亮點**:
- Intent-aware Cognitive Map 作為新的架構層
- 明確的理論對齊（Conceptual Spaces, BDI, Active Inference）
- 可擴展的集成模式（四種 Combo）

---

## 四、未來方向

> **重要說明**: 下列內容屬於研究與探索方向，不代表正式產品的時間線承諾。

### 4.1 理論深化

- **變分推論實作**: 將 Active Inference 的變分推論機制實作到意圖治理引擎中
- **認知地圖可視化**: 基於 IntentCluster 生成可視化的認知地圖
- **跨任務遷移**: 利用 IntentCluster 實現跨 Workspace 的知識遷移

### 4.2 架構優化

- **增量聚類**: 實現增量式的 IntentCluster 更新，避免全量重算
- **多模態支持**: 將圖片、音頻等內容納入 IntentSignal 提取
- **分佈式架構**: 支持跨機器的 Intent Cognitive Map 共享

### 4.3 產品化

- **Intent 面板 UI**: 開發基於 IntentCluster 的專案面板
- **批量操作**: 支持用戶批量調整或關閉 IntentCard
- **可觀測性**: 提供 Intent 治理過程的可視化與審計

---

## 五、參考文獻

### 理論文獻

**Conceptual Spaces & Cognitive Maps**:
- Gärdenfors, P. (2000). *Conceptual spaces: The geometry of thought*. MIT Press.
- Gärdenfors, P. (2014). *The geometry of meaning: Semantics based on conceptual spaces*. MIT Press.
- Bellmund, J. L. S., Gärdenfors, P., Moser, E. I., & Doeller, C. F. (2018). Navigating cognition: Spatial codes for human thinking. *Science*, 362(6415).
- O'Keefe, J., & Nadel, L. (1978). *The hippocampus as a cognitive map*. Oxford University Press.

**BDI & Hierarchical RL**:
- Bratman, M. E. (1987). *Intention, plans, and practical reason*. Harvard University Press.
- Rao, A. S., & Georgeff, M. P. (1995). BDI agents: From theory to practice. *ICMAS*, 95, 312-319.
- Sutton, R. S., Precup, D., & Singh, S. (1999). Between MDPs and semi-MDPs: A framework for temporal abstraction in reinforcement learning. *Artificial intelligence*, 112(1-2), 181-211.
- Bacon, P. L., Harb, J., & Precup, D. (2017). The option-critic architecture. *AAAI*, 31(1).

**Active Inference & Free Energy**:
- Friston, K. (2010). The free-energy principle: a unified brain theory? *Nature reviews neuroscience*, 11(2), 127-138.
- Friston, K., FitzGerald, T., Rigoli, F., Schwartenbeck, P., & Pezzulo, G. (2017). Active inference: a process theory. *Neural computation*, 29(1), 1-49.

**Modern LLM Agents**:
- Park, J. S., O'Brien, J. C., Cai, C. J., Morris, M. R., Liang, P., & Bernstein, M. S. (2023). Generative agents: Interactive simulacra of human behavior. *arXiv preprint arXiv:2304.03442*.
- Weng, L. (2023). LLM-powered autonomous agents. *Lil'Log*. https://lilianweng.github.io/posts/2023-06-23-agent/

---

## 附錄

### A. 術語表

| 術語 | 英文 | 定義 |
|------|------|------|
| 心智空間算法 | Mindscape Algorithm | Mindscape AI 的核心架構理念，將使用者的長期意圖組織成可治理的認知空間 |
| IntentSignal | Intent Signal | 系統內部信號，代表一個可能的意圖，允許大量、碎片化 |
| IntentCard | Intent Card | 用戶可見的專案/長期目標節點，已確認並 commit 的意圖 |
| IntentCluster | Intent Cluster | 將相關 IntentCard 聚合為主題線/專案線的語義區域 |
| IntentSteward | Intent Steward | 專職 LLM 負責意圖的收斂與佈局，決定哪些 IntentSignal 升級為 IntentCard |
| Conceptual Space | Conceptual Space | Gärdenfors 的理論，將概念視為在多維品質維度上的區域 |
| Cognitive Map | Cognitive Map | 海馬體為抽象空間（任務結構、價值）建立的認知地圖 |
| BDI | Belief-Desire-Intention | 傳統 AI 的 agent 架構，將 agent 內部狀態拆為信念、慾望、意圖 |
| Active Inference | Active Inference | 將行為、知覺、學習視為最小化變分自由能的過程 |

### B. 架構圖表

（見正文各章節）

---

**最後更新**: 2025-12-05
**維護者**: Mindscape AI 開發團隊
**狀態**: 技術白皮書 v0.9（公開版）

