# 競品風格分析

## 目的

透過聚合 mind_lens 萃取的視覺特徵來分析競品視覺風格。此 playbook 幫助識別常見模式、流行風格，以及差異化機會。

## 使用時機

- 進行競品研究時
- 重大品牌刷新或視覺識別更新前
- 規劃內容策略時需要了解市場定位
- 收集競品內容的視覺特徵數據後

## 輸入

- **feature_refs**（必填）：mind_lens 視覺特徵萃取的引用陣列
  - 每個 ref 應包含 `source`（如 "competitor_a", "own"）、`feature_set_id`，以及 `storage_key` 或內嵌的 `features`
- **aggregation_strategy**（選填）：分析策略
  - `cluster`：將相似視覺模式分組
  - `timeline`：分析風格隨時間演變
  - `comparison`：跨不同來源比較（預設）

## 流程

1. **載入特徵**：從提供的引用取得視覺特徵集
2. **聚合分析**：套用選定的策略來合併和分析特徵
3. **萃取洞察**：將聚合結果轉換為可執行的洞察

## 輸出

- **aggregation_result**：基於選定策略的詳細分析
  - 主要視覺 token 及其頻率
  - 色彩趨勢
  - 情緒向量分析
- **insights**：可供規劃和內容策略使用的可執行洞察

## 使用範例

```yaml
inputs:
  feature_refs:
    - source: "competitor_a"
      feature_set_id: "fs_001"
      storage_key: "mind_lens/extractions/competitor_a/..."
    - source: "competitor_b"
      feature_set_id: "fs_002"
      features:
        visual_tokens: ["gradient", "minimalist", "soft_shadow"]
        colors: ["#6366F1", "#EC4899"]
  aggregation_strategy: "comparison"
```

## 相關 Playbook

- `ana_content_gap`：使用缺口分析結果作為競爭定位的輸入
- `bi_define_vi`：將洞察應用於視覺識別優化
