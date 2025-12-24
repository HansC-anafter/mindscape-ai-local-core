# The Mindscape Algorithm

> **Core architectural philosophy behind Mindscape AI**

## What is the Mindscape Algorithm?

**心智空間算法（Mindscape Algorithm）** 是 Mindscape AI 的核心架構理念。

它把使用者的長期意圖、專案主線、創作主題，整理成一個**可治理、可導航的心智空間**，讓 LLM 不再只是回答單一問題，而是圍繞你的整體人生／工作主線一起思考與行動。

The **Mindscape Algorithm** is the core architectural idea behind Mindscape AI.

It organizes a user's long-term intentions, project storylines, and creative themes into a **governable, navigable cognitive space**, and uses this as the backbone for intent-aware LLM agents and workflows.

---

## Mindscape Architecture (3 Layers)

Mindscape AI 不是只做一個聊天框，而是圍繞「意圖」設計了三層結構：

### 1. Signal Layer — 收集一切線索

對話、文件、工具回傳、Playbook 執行結果，都會被轉成輕量的 **IntentSignal**，作為系統理解你在「忙些什麼」的底層訊號。

### 2. Intent Governance Layer — 幫你整理主線

Signal 會被收斂成 **IntentCard**（長期意圖）與 **短期任務**，並聚成 **IntentCluster**（專案／主題）。這一層就是所謂的「心智空間」，負責維護你的工作與生活主線。

### 3. Execution & Semantic Layer — 真的去幹活

當某條 Intent 準備好，就交給 Playbook、工具、以及各種語意引擎去執行，包含 RAG 查詢、文件生成、跨工具自動化工作流等。

---

## Governance-first hypothesis (real-world constraint)

現實世界的可行解空間通常很小（往往只有 1–3 個可行方案）。Mindscape 假設 AI 的主要價值在於**深化與 operationalize 少數可信方案**（例如把 2 個方案拓成約 5 個可用變體），而不是無限制地生成數百個點子。

Mindscape is designed with the assumption that real-world work has a small feasible solution space (often 1–3 viable options). We expect AI to deepen and operationalize a few grounded options (e.g., turning 2 options into ~5 usable variants) rather than generate hundreds of unconstrained ideas.

Note: this is a design hypothesis today; enforcement mechanisms are not yet implemented at the system level.

---

## For Developers / Researchers

Mindscape AI 把自己定位在「**intent-first 的 LLM agent 架構**」：

* 受 Conceptual Spaces & Cognitive Maps 啟發，我們把 IntentCard / IntentCluster 視為一張可導航的 **意圖地圖**。
* 受 BDI 與階層式強化學習（options）啟發，我們把 Intent Layer 視為高階決策層，Playbook 與執行引擎則專心做執行。
* 受 Active Inference 啟發，我們把使用者的偏好與長期目標，收斂成一組能引導「下一步最值得做什麼」的偏好分佈。

如果你對這些主題有興趣，可以參考 [Mindscape AI 官網](https://mindscapeai.app) 了解完整設計與技術白皮書（即將推出）。

---

## Learn More

- 🌐 [Mindscape AI 官網](https://mindscapeai.app) - 理念與產品介紹、完整技術白皮書（即將推出）
- 📚 [Architecture Documentation](./architecture/) - 技術架構文檔

---

**最後更新**: 2025-12-05
