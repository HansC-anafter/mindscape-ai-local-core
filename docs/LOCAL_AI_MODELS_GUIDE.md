# 本地 AI 模型使用指南

適用於 Mindscape AI Local-Core 搭配本地 GPU 工作站的使用者。

---

## 硬體需求

| 等級 | GPU VRAM | 系統 RAM | 適用場景 |
|------|----------|----------|---------|
| **入門** | 8GB | 16GB | 文字 LLM + 基礎圖像分析 |
| **推薦** | 12GB | 32GB | LLM + ComfyUI 圖像/影片生成 |
| **進階** | 16GB+ | 64GB | 多模型並行、高解析度影片 |

> 本指南以 **RTX 4070 Super (12GB) + 32GB RAM** 為基準配置撰寫。

---

## 模型總覽

Mindscape AI 使用兩種本地模型：

1. **Ollama 模型** — 文字 / 視覺理解 LLM，處理對話、分析、提示詞生成
2. **ComfyUI 模型** — 圖像 / 影片生成（Diffusion 模型）

兩者**共用 GPU VRAM**，無法同時滿載運行，系統會**自動分時排程**。

---

## Ollama 推薦模型

### 文字對話（Chat）

| 模型 | 大小 | VRAM | 說明 |
|------|------|------|------|
| **gemma3:4b** | 4B | ~2.5GB | ⭐ 輕量首選，摘要 / Q&A / 快速任務 |
| **qwen3:8b** | 8B | ~5GB | ⭐ 最佳全能，指令跟隨佳，支援工具調用 |
| **llama3.1:8b** | 8B | ~5GB | 通用寫作與推理 |
| **deepseek-r1:8b** | 8B | ~5GB | 複雜規劃與分析推理 |

### 視覺理解（Multimodal）

| 模型 | 大小 | VRAM | 說明 |
|------|------|------|------|
| **qwen2.5vl** | 7B | ~5GB | ⭐ 圖像分析首選，多語言，文件理解強 |
| **llama3.2-vision** | 11B | ~7GB | Meta 視覺推理，OCR |
| **gemma3:12b** | 12B | ~7GB | 1080p 圖像理解，多語言 |
| **moondream:1.8b** | 1.8B | ~1GB | 超輕量，可與 ComfyUI 同時運行 |

### 安裝方式

```bash
# 安裝 Ollama（Windows / macOS / Linux）
# https://ollama.com/download

# 拉取推薦模型
ollama pull qwen3:8b          # 文字對話
ollama pull qwen2.5vl         # 視覺分析
ollama pull gemma3:4b         # 輕量備用
```

安裝後在 Settings → Models & Quota 頁面可看到已連接的 Ollama 模型。

---

## ComfyUI 推薦模型

### 圖像生成（穩定優先）

| 模型 | 檔案大小 | VRAM | 說明 |
|------|---------|------|------|
| **SDXL Base 1.0** | ~6.9GB | ~8GB | ⭐ 最穩定，LoRA / ControlNet 生態完整 |
| **SDXL Lightning 4-Step** | ~5.1GB | ~8GB | 極速預覽，4 步即出圖 |
| **Flux.1 Dev (FP8)** | ~8GB | ~8GB | 最高品質，需 FP8 量化 |

### 影片生成

| 模型 | 檔案大小 | VRAM | 說明 |
|------|---------|------|------|
| **Wan2.2 1.3B** | ~2.6GB | ~6GB | ⭐ 12GB VRAM 甜蜜點 |
| **LTX-Video** | ~4GB | ~8GB | 極速，5 秒影片只需 2 秒 |

### 輔助模型

| 模型 | 用途 | VRAM |
|------|------|------|
| **ControlNet Depth v1.1** | 深度控制 | ~1.5GB |
| **ControlNet OpenPose v1.1** | 姿態控制 | ~1.5GB |
| **SDXL VAE** | VAE 解碼器 | ~0.3GB |
| **RealESRGAN x4** | 4 倍超解析度 | ~0.5GB |

ComfyUI 模型透過 Capability Pack 的 Profile 一鍵下載，無需手動操作。

---

## VRAM 管理：分時運行原則

12GB VRAM 無法同時運行所有模型，請遵循以下原則：

### 工作模式

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│  分析模式    │ ──→ │  生成模式     │ ──→ │  後處理模式  │
│  Ollama 活躍 │     │  ComfyUI 活躍 │     │  Ollama 活躍 │
│  ~5GB VRAM  │     │  ~8GB VRAM   │     │  ~5GB VRAM  │
└─────────────┘     └──────────────┘     └─────────────┘
```

1. **分析模式** — Ollama 分析圖片 / 生成提示詞（ComfyUI idle）
2. **生成模式** — ComfyUI 渲染圖像或影片（Ollama 自動卸載）
3. **後處理模式** — Ollama 評估結果 / 迭代提示詞

### 可同時運行的組合

| 組合 | VRAM | 可行 |
|------|------|------|
| Ollama 4B + ComfyUI SDXL | ~10.5GB | ✅ |
| Ollama 1.8B + ComfyUI Flux FP8 | ~9GB | ✅ |
| Ollama 8B + ComfyUI SDXL | ~13GB | ⚠️ 需 offload |
| ComfyUI SDXL + Wan2.2 | ~14GB | ❌ |

> **提示**：32GB 系統 RAM 可作為 VRAM 溢出緩衝，速度會降低但不會崩潰。

### ComfyUI 啟動建議

```bash
# 推薦啟動參數（12GB VRAM）
python main.py --listen 0.0.0.0 --port 8188 --lowvram
```

---

## 推薦配置方案

### 方案 A：穩定產線（推薦新手）

```
Ollama:   qwen3:8b + qwen2.5vl
ComfyUI:  SDXL Base + SDXL Lightning + ControlNet Depth + VAE
總磁碟:   ~20GB
```

### 方案 B：品質優先

```
Ollama:   qwen3:8b + gemma3:12b
ComfyUI:  Flux.1 Dev FP8 + ControlNet + VAE + RealESRGAN
總磁碟:   ~25GB
```

### 方案 C：影片產線

```
Ollama:   gemma3:4b（輕量，留 VRAM 給影片）
ComfyUI:  Wan2.2 1.3B + SDXL Lightning
總磁碟:   ~15GB
```

---

## 常見問題

**Q: 模型存在哪裡？**
- Ollama：`~/.ollama/models/`
- ComfyUI：`~/.mindscape/models/`（由 ModelWeightsInstaller 管理）

**Q: VRAM 不夠怎麼辦？**
- 使用 `--lowvram` 啟動 ComfyUI
- 選擇 FP8 量化版模型
- 使用較小的模型（4B / 1.8B）
- 設定 NVMe SSD 靜態 swap file（Windows: 16GB+）

**Q: Ollama 模型如何切換？**
- Ollama 自動管理，呼叫哪個模型就載入哪個，閒置自動卸載
- 在 Settings → Models & Quota 可查看已連接模型

**Q: 需要全部模型都下載嗎？**
- 不需要。選擇一個方案，按需下載即可
- 推薦新手從**方案 A** 開始
