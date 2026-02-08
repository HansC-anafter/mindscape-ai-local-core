# 驗證 Manifest

## 目的

驗證 scene_edit_manifest 結構和素材可存取性，不執行實際渲染。用於渲染工作提交前的預檢。

## 使用時機

- 提交渲染工作前
- 診斷渲染問題
- 自動化產線驗證

## 輸入

- **manifest_ref**（必填）：scene_edit_manifest 的引用
- **check_assets**（選填）：是否驗證素材可存取性 - 預設：true

## 輸出

- **valid**：manifest 是否可用於渲染
- **errors**：驗證錯誤列表（阻擋）
- **warnings**：警告列表（非阻擋）
- **asset_checks**：個別素材可存取性結果

## 使用範例

```yaml
inputs:
  manifest_ref:
    storage_key: "multi_media_studio/projects/proj_123/scene_edit_manifest.json"
  check_assets: true
```

## 相關 Playbook

- `vr_render_video`：完整渲染工作流程
