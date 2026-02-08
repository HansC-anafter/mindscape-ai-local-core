---
playbook_code: sonic_asset_import
version: 1.1.0
locale: zh-TW
name: "Audio Asset Import & Normalization"
description: "Import, normalize, and QA-check audio assets from various sources"
kind: user_workflow
capability_code: sonic_space
---

# Audio Asset Import & Normalization

Import, normalize, and QA-check audio assets from various sources

## 概述

音訊資產匯入與標準化 playbook 是將音訊資產帶入 Sonic Space 系統的入口點。它處理從各種來源（本地檔案、雲端儲存或影片檔案）匯入音訊檔案，將其標準化為統一格式，並執行基本的品質保證檢查。

**主要功能：**
- 支援多種音訊格式（WAV、MP3、FLAC、AAC、M4A）和影片格式（MP4、MOV）的音訊提取
- 自動格式標準化至 44.1kHz 取樣率和 -14 LUFS 響度
- 最小化 QA 檢查以確保音訊品質（無削波、合理的響度範圍、有效時長）
- 自動元數據提取（時長、峰值電平、動態範圍、頻率特性）
- 大型檔案的異步處理

**目的：**
此 playbook 為 Sonic Space 流程中的進一步處理準備音訊資產。所有匯入的資產必須通過此 playbook，才能在其他 playbook 中使用，例如 `sonic_segment_extract`、`sonic_embedding_build` 或 `sonic_navigation`。

**相關 Playbooks：**
- `sonic_license_governance` - 為匯入的資產註冊授權資訊
- `sonic_segment_extract` - 將標準化音訊切段為可搜尋的區塊
- `sonic_embedding_build` - 從匯入的資產建立 embeddings

詳細規格請參考：`playbooks/specs/sonic_asset_import.json`

## 輸入參數

### 必填輸入

- **source_files** (`array[file]`)
  - Audio files (wav/mp3/flac) or video files (for audio extraction)
  - Accepted formats: wav, mp3, flac, aac, m4a, mp4, mov

### 選填輸入

- **source_url** (`string`)
  - Cloud link (Google Drive / Dropbox)

- **target_sample_rate** (`integer`)
  - Target sample rate
  - Default: `44100`

- **target_loudness** (`float`)
  - Target loudness (LUFS)
  - Default: `-14.0`

- **channel_mode** (`enum`)
  - Default: `stereo`
  - Options: mono, stereo

## 輸出結果

**Artifacts:**

- `audio_asset`
  - Schema defined in spec file

## 執行步驟

### Step 1: Validate Input Format

Check file format and size

- **Action**: `validate`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool

### Step 2: Extract Audio from Video

Extract audio track from video files

- **Action**: `extract_audio_from_video`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool
- **Condition**: input.source_files contains video format

### Step 3: Format Normalization

- **Action**: `normalize`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool

### Step 4: Generate Metadata

- **Action**: `analyze_audio`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool
- **Outputs**: duration, peak_level, dynamic_range, frequency_profile

### Step 5: Minimal QA Check

Basic quality checks (merged from F02 to avoid P0/P1 dependency)

- **Action**: `qa_gate`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool

### Step 6: Create Asset Record

- **Action**: `create_artifact`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool

## 安全檢查

- **format_validation**
  - Rule: Only accept supported audio/video formats
  - Action: `reject_with_message`

- **file_size_limit**
  - Rule: Single file < 500MB
  - Action: `reject_with_message`

- **duration_limit**
  - Rule: Single file duration < 60 minutes
  - Action: `warn_and_proceed`

- **qa_gate**
  - Rule: Must pass minimal QA checks
  - Action: `reject_with_qa_report`

## 所需能力

This playbook requires the following capabilities:

- `sonic_space`

**Note**: Capabilities are specified using `capability_code`, not hardcoded tools or APIs.

## 資料邊界

- **Local Only**: False
- **Cloud Allowed**: True

**Note**: Data locality is defined in the playbook spec and takes precedence over manifest defaults.

## 使用場景

1. **批量音訊匯入**
   - 從本地儲存或雲端連結匯入多個音訊檔案
   - 自動將所有檔案標準化為一致格式
   - 批次處理大型音訊資產集合

2. **影片音訊提取**
   - 從影片檔案（MP4、MOV）提取音訊軌道
   - 將影片音訊轉換為標準音訊格式
   - 準備提取的音訊以供進一步處理

3. **品質保證**
   - 驗證音訊檔案符合最低品質標準
   - 檢測削波、過度響度或格式問題
   - 為有問題的檔案產生 QA 報告

4. **資產準備**
   - 為 embedding 生成準備音訊資產
   - 標準化格式以確保一致處理
   - 提取元數據以供編目和搜尋

## 使用範例

### 範例 1：匯入單一音訊檔案

```json
{
  "source_files": ["/path/to/audio.wav"],
  "target_sample_rate": 44100,
  "target_loudness": -14.0,
  "channel_mode": "stereo"
}
```

**預期輸出：**
- `audio_asset` artifact，包含標準化音訊檔案
- 元數據，包括時長、峰值電平、動態範圍
- QA 檢查結果

### 範例 2：從雲端儲存匯入

```json
{
  "source_url": "https://drive.google.com/file/d/xxx",
  "target_sample_rate": 44100,
  "target_loudness": -14.0
}
```

**預期輸出：**
- `audio_asset` artifact，包含下載並標準化的音訊
- 來源追蹤資訊

### 範例 3：從影片提取音訊

```json
{
  "source_files": ["/path/to/video.mp4"],
  "target_sample_rate": 44100,
  "target_loudness": -14.0
}
```

**預期輸出：**
- `audio_asset` artifact，包含提取並標準化的音訊軌道
- 保留原始影片元數據

## 技術細節

**工具依賴：**
- `sonic_audio_analyzer` - 音訊分析和元數據提取

**服務依賴：**
- `ffmpeg` - 音訊/影片處理和格式轉換

**處理流程：**
1. 檔案驗證（格式、大小檢查）
2. 音訊提取（如果是影片檔案）
3. 格式標準化（取樣率、響度、聲道）
4. 元數據提取（時長、峰值、動態範圍、頻率特性）
5. QA 檢查（削波、響度範圍、時長、取樣率）
6. 資產記錄建立

**效能：**
- 預估時間：每個檔案約 5 秒
- 大型檔案的異步處理
- 支援最大 500MB 的檔案
- 最大時長：60 分鐘（含警告）

**輸出結構：**
`audio_asset` artifact 包含：
- 資產 ID 和工作區/租戶資訊
- 原始和標準化檔案路徑
- 格式資訊（取樣率、位深度、聲道）
- 元數據（時長、峰值電平、LUFS、動態範圍）
- QA 結果（通過的檢查、失敗的檢查及數值）
- 匯入時間戳記和狀態

## 相關 Playbooks

- **sonic_license_governance** - 為匯入的資產註冊授權資訊
- **sonic_segment_extract** - 將標準化音訊切段為可搜尋的區塊
- **sonic_embedding_build** - 從匯入的資產建立 embeddings
- **sonic_navigation** - 搜尋和導航匯入的資產

## 參考資料

- **規格文件**: `playbooks/specs/sonic_asset_import.json`
- **API 端點**: `POST /api/v1/sonic-space/assets/import`
