# The Mindscape Algorithm

> **Core architectural philosophy behind Mindscape AI**

## What is the Mindscape Algorithm?

**心智空間算法（Mindscape Algorithm）** 是 Mindscape AI 的核心架構理念。

它把使用者的長期意圖、專案主線、創作主題，整理成一個**可治理、可導航的心智空間**，讓 LLM 不再只是回答單一問題，而是圍繞你的整體人生／工作主線一起思考與行動。

The **Mindscape Algorithm** is the core architectural idea behind Mindscape AI.

It organizes a user's long-term intentions, project storylines, and creative themes into a **governable, navigable cognitive space**, and uses this as the backbone for intent-aware LLM agents and workflows.

---

## Mindscape Operating Engine

Mindscape AI 把人的長期心智脈絡轉成一個可治理的 operating engine：

> **Governance Context → Meeting Runtime ↔ Governed Memory Fabric → Optional Actuation / External Runtimes → Artifacts, Decisions, and Writeback**

### 1. Governance Context — 定義「為什麼做、怎麼看、哪些不能做」

Mindscape 先把執行所需的治理上下文編譯出來：

- **Intent**：什麼重要、當前要推進什麼
- **Mind-Lens**：用什麼視角看、如何取捨與導演輸出
- **Policy**：什麼不能違反、哪些風險必須被攔下

這一層直接構成 agent core 的一部分。

### 2. Meeting Runtime — 承接當下思考與收斂

Mindscape Meeting 負責 live deliberation、釐清、收斂、派發與閉環。

它讓系統在任務、會議與決策之間維持可見推進的 runtime。

### 3. Governed Memory Fabric — 保留長期連續性

記憶層在系統中負責長期連續性、證據治理與執行時 serving。

Mindscape 的記憶層必須能：

- 保留 event、reasoning、artifact 等證據
- 形成 episodic memory，將原始片段整理成可回溯的經驗單位
- 將反覆被驗證的內容升格成較穩定的 core / procedural memory
- 讓過時或被新證據取代的結論失效
- 在執行時把正確的 memory packet 回送到 context 中

### 4. Actuation Layer — 把認知變成可選的實際執行

當治理上下文、Meeting Runtime 與記憶層對齊後，系統才會把工作派發到：

- **Project / Flow**
- **Playbooks / Tools**
- **Sandbox / External Runtimes**

真正的 operating engine 由可治理的認知內核與可執行的外部動作層共同構成。

### 5. Mind-Model VC — 治理線索的版本控管

當治理上下文需要可回顧、可調整、可回滾的演化軌跡時，Mind-Model VC 負責承接這部分。

- **Swatch（色票/線索）**：從 Event 中提取候選線索，需用戶確認
- **Mix（配方/當下調色）**：某個時間窗內的意圖/視角組合，用戶自己寫標題/描述
- **Commit（版本/變更）**：配方的變化，附上用戶自己的 commit message
- **Co-Graph（共現關係圖）**：追蹤線索/顏色之間的共現關係

**核心設計原則**：
- 心智調色盤式的治理介面
- 像 Git，但 commit 的是「配方」
- 用戶完全控制（opt-in、可編輯、可撤銷）

它處理的不是即時 deliberation，也不是長期記憶 serving，而是治理線索本身如何被整理、命名、提交與追蹤。

詳見 [Mind-Model VC Architecture](./core-architecture/mind-model-vc.md) 與 [Governed Memory Fabric](./core-architecture/governed-memory-fabric.md)。

---

## Governance-first hypothesis (real-world constraint)

現實世界的可行解空間通常很小（往往只有 1–3 個可行方案）。Mindscape 假設 AI 的主要價值在於**深化與 operationalize 少數可信方案**，例如把 2 個方案拓成約 5 個可用變體。

Mindscape is designed with the assumption that real-world work has a small feasible solution space (often 1–3 viable options). We expect AI to deepen and operationalize a few grounded options (e.g., turning 2 options into ~5 usable variants) rather than generate hundreds of unconstrained ideas.

Note: this is a design hypothesis today; enforcement mechanisms are not yet implemented at the system level.

---

## For Developers / Researchers

Mindscape AI 把自己定位在「**governance-first、intent-anchored 的 cognitive operating architecture**」：

* 受 Conceptual Spaces & Cognitive Maps 啟發，我們把 IntentCard / IntentCluster 視為一張可導航的 **意圖地圖**。
* 受 BDI 與階層式強化學習（options）啟發，我們把 Intent Layer 視為高階決策層，Playbook 與執行引擎則專心做執行。
* 受 Active Inference 啟發，我們把使用者的偏好與長期目標，收斂成一組能引導「下一步最值得做什麼」的偏好分佈。

如果你對這些主題有興趣，可以參考 [Mindscape AI 官網](https://mindscapeai.app) 了解完整設計與技術白皮書（即將推出）。

---

## Learn More

- 🌐 [Mindscape AI 官網](https://mindscapeai.app) - 理念與產品介紹、完整技術白皮書（即將推出）
- 📚 [Architecture Documentation](./core-architecture/README.md) - 技術架構文檔
- 🧠 [Governed Memory Fabric](./core-architecture/governed-memory-fabric.md) - 對外正式的記憶架構骨架

---

**最後更新**: 2026-03-25
