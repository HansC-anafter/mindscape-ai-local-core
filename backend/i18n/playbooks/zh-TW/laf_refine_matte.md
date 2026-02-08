# 精修遮罩

## 目的

精修 alpha 遮罩以處理精確的邊緣，特別是毛髮、透明度和陰影。此 playbook 總是建立新版本以維持衍生圖譜的可追溯性。

## 使用時機

- 初始圖層拆解後需要邊緣精修時
- 元素具有複雜邊界時（毛髮、皮毛、羽毛）
- 需要將投射陰影與主元素分離時
- 處理半透明元素時（玻璃、煙霧、布料）

## 輸入

- **element_asset_id**（必填）：要精修的元素資產 ID
- **refine_options**（選填）：
  - `hair_detail`：啟用詳細毛髮/皮毛邊緣精修（預設：true）
  - `separate_shadow`：將投射陰影提取為獨立圖層（預設：false）
  - `transparency_aware`：處理半透明區域（預設：false）

## 流程

1. **載入資產**：從儲存空間取得元素資產
2. **精修遮罩**：套用 matting 模型（MODNet 或類似）進行邊緣精修
3. **陰影分離**：選擇性提取陰影圖層
4. **註冊版本**：建立具有衍生連結的新資產版本

## 輸出

- **refined_asset_ref**：精修後元素資產的引用（新版本）
- **shadow_layer_ref**：提取的陰影圖層引用（若 separate_shadow=true）

## 使用範例

```yaml
inputs:
  element_asset_id: "elem_abc123"
  refine_options:
    hair_detail: true
    separate_shadow: true
    transparency_aware: false
```

## 相關 Playbook

- `laf_extract_layers`：初始圖層拆解
- `laf_complete_hidden`：補全遮擋區域
- `laf_export_pack`：匯出精修後的圖層
