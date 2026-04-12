# 分析釘選參考素材

## 目標
分析一張釘選的 IG 參考素材圖片，產出三層結構化視覺分析（場景/物件/風格），並自動回填標籤。

## 前置條件
- 已透過「釘選參考素材」功能釘選至少一張圖片
- 該圖片有對應的 `reference_id`

## 流程

### 步驟 1：前處理
讀取釘選的參考圖片，將其轉換為 Base64 格式，並準備結構化分析提示詞。

使用工具：`ig.ig_analyze_reference`（mode: preprocess）

### 步驟 2：視覺分析
將前處理結果送入多模態視覺模型進行三層分析：
- **Scene（場景）**：構圖、光線、場景、氛圍
- **Object（物件）**：偵測物件、主要主體
- **Style（風格）**：色彩、排版、視覺技法、IG 風格分類

使用工具：`core_llm.multimodal_analyze`

### 步驟 3：回填
驗證視覺分析結果（Pydantic schema 驗證），提取自動標籤並正規化，寫回參考素材的 metadata。

使用工具：`ig.ig_analyze_reference`（mode: backfill）

## 輸出
- 更新後的參考素材 metadata（含 `vision_description`、`auto_tags`、`analysis_provenance`）
- 分析工作狀態更新為 `COMPLETED`
