# 補全遮擋區域

## 目的

修補遮擋區域以補全元素的隱藏部分。此 playbook 總是建立新版本以確保可追溯性 - 原始資產永不被修改。

## 使用時機

- 元素被另一物體部分遮擋時
- 移除物體後的背景補全
- 準備可靈活重新定位的資產時
- 為裁切元素建立「完整」版本

## 輸入

- **element_asset_id**（必填）：要補全的元素資產 ID
- **mask_region**（必填）：修補的區域規格
  - 可從遮擋分析自動偵測或手動指定
- **strategy**（選填）：
  - `conservative`：最小化修補，盡可能保留原始內容
  - `aggressive`：更廣泛的補全以獲得更好的視覺效果

## 流程

1. **載入資產**：取得元素資產和遮罩區域
2. **修補**：套用修補模型（LaMa 或類似）補全隱藏區域
3. **品質檢查**：計算補全信心分數
4. **註冊版本**：建立具有衍生連結的新資產版本

## 輸出

- **completed_asset_ref**：補全後元素資產的引用（新版本）
- **completion_confidence**：修補區域的信心分數（0.0-1.0）

## 使用範例

```yaml
inputs:
  element_asset_id: "elem_abc123"
  mask_region:
    x: 100
    y: 50
    width: 200
    height: 150
    source: "occlusion_detection"
  strategy: "conservative"
```

## 重要說明

- 修補總是產生新版本 - 原始版本會保留
- 使用衍生圖譜可追溯回原始資產
- 較低的信心分數可能表示需要人工審核

## 相關 Playbook

- `laf_extract_layers`：初始圖層拆解
- `laf_refine_matte`：補全前/後的邊緣精修
- `laf_version_and_register`：手動版本控制
