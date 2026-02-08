---
playbook_code: divi_slotizer
version: 1.0.0
capability_code: web_generation
name: Divi 模板 Slotizer
description: |
  自動化處理 Divi Theme 模板的 Slot 化流程，將 Divi Portability 匯出的 .json 模板自動掃描可變欄位，
  插入 {{slot_id}} 佔位符，產出 slots.schema.json 和 template.registry.json。
  後續生成頁面時只需填值 slot，不動排版，確保視覺一致性。
tags:
  - web
  - divi
  - wordpress
  - template
  - automation
  - slotization

kind: user_workflow
interaction_mode:
  - conversational
  - needs_review
visible_in:
  - workspace_tools_panel
  - workspace_playbook_menu

required_tools:
  - filesystem_write_file
  - filesystem_read_file
  - cloud_capability.call

language_strategy: model_native
locale: zh-TW
supported_locales:
  - zh-TW
  - en
default_locale: zh-TW
auto_localize: true

entry_agent_type: coder
icon: 🎯
---

# Divi 模板 Slotizer - SOP

## 目標

將 Divi Theme 的模板（透過 Portability 匯出的 `.json` 檔案）自動化處理為可組裝的 Slot 化模板：

1. **自動掃描可變欄位**：識別文字、URL、圖片等可變內容
2. **插入 Slot 佔位符**：將可變欄位替換為 `{{slot_id}}`
3. **生成 CSS ID**：為每個模組自動生成 CSS ID，實現持久性定位（**新功能**）
4. **產出 Slot Schema**：生成 `slots.schema.json` 定義所有 slot 的類型、限制、預設值（**包含 CSS ID**）
5. **註冊模板**：產出 `template.registry.json` 記錄模板 ID、hash、context、版本

**核心價值**：
- 消除手工埋 placeholder 的繁瑣工作
- 確保排版一致性（只填值，不動設計設定）
- 支援大量自動產頁且視覺一致

## 執行步驟

### Phase 0: 檢查 Project Context

**執行順序**：
1. 步驟 0.0: 檢查是否有活躍的 web_page 或 website project
2. 步驟 0.1: 獲取 Project Sandbox 路徑
3. 步驟 0.2: 檢查輸入檔案（template_json）

#### 步驟 0.0: 檢查 Project Context

- 檢查 execution context 中是否有 `project_id`
- 如果有，確認 project type 為 `web_page` 或 `website`
- 如果沒有，提示用戶需要先創建 project

#### 步驟 0.1: 獲取 Project Sandbox 路徑

- 使用 `project_sandbox_manager.get_sandbox_path()` 獲取 sandbox 路徑
- Sandbox 路徑結構：`sandboxes/{workspace_id}/{project_type}/{project_id}/`
- 確保 `templates/divi/` 目錄存在（用於存放處理後的模板）

#### 步驟 0.2: 檢查輸入檔案

**必須**使用 `filesystem_read_file` 工具讀取 Divi 匯出的 `.json` 檔案：

- **文件路徑**：由用戶提供（可能是上傳的檔案或已存在的檔案）
- **完整路徑**：`sandboxes/{workspace_id}/{project_type}/{project_id}/templates/divi/input/{template_name}.json`

**驗證 JSON 格式**：
- 確保檔案是有效的 JSON
- 檢查是否包含 Divi Portability 的標準結構
- 如果格式錯誤，提示用戶重新匯出

**輸出**：
- `template_json`: 解析後的 JSON 物件
- `template_file_path`: 原始檔案路徑

### Phase 1: Fingerprint & Context Detection

#### 步驟 1.1: 計算 Template Hash

計算模板的 SHA256 hash，用於：
- 模板版本追蹤
- 重複檢測
- 完整性驗證

```python
import hashlib
import json

def calculate_template_hash(template_json: dict) -> str:
    """Calculate SHA256 hash of template JSON"""
    template_str = json.dumps(template_json, sort_keys=True)
    return hashlib.sha256(template_str.encode()).hexdigest()
```

**輸出**：
- `template_hash`: SHA256 hash（完整 64 字元）
- `template_hash_short`: 前 8 字元（用於 template_id）

#### 步驟 1.2: 判斷 Context 類型

Divi Portability 匯出的檔案可能來自三種上下文：

1. **divi_library**：Divi Library 項目（Layouts、Modules、Sections）
2. **page_layout**：完整頁面布局
3. **theme_builder**：Theme Builder 模板（Header、Footer、Body）

**自動判斷邏輯**：

檢查 JSON 結構中的關鍵字段：

```python
def detect_context(template_json: dict) -> str:
    """Detect Divi template context"""
    # 檢查是否有 theme_builder 相關字段
    if 'theme_builder' in template_json or 'template_type' in template_json:
        template_type = template_json.get('template_type', '')
        if 'header' in template_type.lower() or 'footer' in template_type.lower():
            return 'theme_builder'

    # 檢查是否有 library 相關字段
    if 'library' in template_json or 'item_type' in template_json:
        return 'divi_library'

    # 預設為 page_layout
    return 'page_layout'
```

**重要**：Divi 匯入有「上下文限制」，匯錯位置會出現 *This file should not be imported in this context* 錯誤，所以必須正確識別 context。

**輸出**：
- `context`: `divi_library` / `page_layout` / `theme_builder`
- `context_confidence`: 判斷信心度（high/medium/low）

#### 步驟 1.3: 生成 Template ID

生成唯一的 template_id，格式：`{slug(name)}-{short_hash}`

```python
import re

def generate_template_id(name: str, short_hash: str) -> str:
    """Generate template ID from name and hash"""
    # 將名稱轉為 slug
    slug = re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')
    return f"{slug}-{short_hash}"
```

**輸出**：
- `template_id`: 唯一模板識別碼
- `template_name`: 從 JSON 提取的模板名稱（如果存在）

### Phase 2: Candidate Slots 掃描

#### 步驟 2.1: 定義 Slot Policy

**Slot Policy 規則**（硬編碼，不可變）：

**允許 Slot 的模組類型**：
- Text
- Heading
- Button
- Image
- Blurb
- Testimonial
- Pricing Table
- CTA (Call to Action)
- Post Title
- Post Content
- Post Meta

**允許 Slot 的欄位**：
- `title`: 標題文字
- `content`: 內容文字（允許 HTML）
- `button_text`: 按鈕文字
- `button_url`: 按鈕連結
- `image_url`: 圖片 URL
- `alt`: 圖片替代文字
- `subtitle`: 副標題
- `description`: 描述文字
- `author`: 作者名稱
- `date`: 日期文字

**固定不 Slot 的欄位**（排版一致性根）：
- 所有 spacing 相關欄位（padding, margin, gap）
- 所有 color 相關欄位（background_color, text_color, border_color）
- 所有 font 相關欄位（font_family, font_size, font_weight, line_height）
- 所有 animation 相關欄位（animation_style, animation_duration）
- 所有 breakpoint 相關欄位（responsive settings）
- 所有 custom CSS 欄位

**輸出**：
- `slot_policy`: Slot Policy 規則字典

#### 步驟 2.2: 遍歷 JSON Tree 掃描候選欄位

遞迴遍歷 Divi JSON 結構，找出所有符合條件的候選欄位：

```python
def scan_candidate_slots(template_json: dict, slot_policy: dict) -> list:
    """Scan JSON tree for candidate slots"""
    candidates = []

    def traverse(obj, path="", module_id=None):
        if isinstance(obj, dict):
            # 檢查是否為 Divi 模組
            if 'type' in obj and obj['type'] in slot_policy['allowed_modules']:
                module_id = obj.get('id') or obj.get('module_id')
                # 掃描允許的欄位
                for field in slot_policy['allowed_fields']:
                    if field in obj:
                        value = obj[field]
                        if is_slot_candidate(value, field):
                            candidates.append({
                                'path': f"{path}.{field}",
                                'module_id': module_id,
                                'module_type': obj['type'],
                                'field_name': field,
                                'value': value,
                                'value_type': detect_value_type(value, field)
                            })

            # 遞迴遍歷
            for key, value in obj.items():
                new_path = f"{path}.{key}" if path else key
                traverse(value, new_path, module_id)

        elif isinstance(obj, list):
            for idx, item in enumerate(obj):
                traverse(item, f"{path}[{idx}]", module_id)

    traverse(template_json)
    return candidates
```

**候選欄位判斷邏輯**：

```python
def is_slot_candidate(value: any, field_name: str) -> bool:
    """Check if a field is a candidate for slotization"""
    # 排除空值
    if not value or value == '':
        return False

    # 文字類欄位：長度介於 1～300，允許含 HTML
    if field_name in ['title', 'content', 'button_text', 'subtitle', 'description']:
        if isinstance(value, str) and 1 <= len(value) <= 300:
            return True

    # URL 類欄位：看起來像 URL 或路徑
    if field_name in ['button_url', 'image_url']:
        if isinstance(value, str) and (value.startswith('http') or value.startswith('/')):
            return True

    # 圖片類欄位：URL 或 attachment id
    if field_name == 'image_url':
        if isinstance(value, str) and (value.startswith('http') or value.isdigit()):
            return True

    return False

def detect_value_type(value: any, field_name: str) -> str:
    """Detect value type for slot schema"""
    if field_name in ['title', 'content', 'button_text', 'subtitle', 'description']:
        return 'text'
    elif field_name in ['button_url', 'image_url']:
        if field_name == 'image_url':
            return 'image'
        return 'url'
    return 'text'
```

**輸出**：
- `candidate_slots`: 候選 slot 列表（通常 30～80 個）

### Phase 3: Slot Selection（規則優先 + LLM 輔助）

#### 步驟 3.1: 硬規則必選 Slots

**硬規則必選**（幾乎永遠要變 slot）：

```python
def apply_hard_rules(candidates: list) -> tuple[list, list]:
    """Apply hard rules to select/exclude slots"""
    selected = []
    excluded = []

    for candidate in candidates:
        # 必選規則
        if is_hero_title(candidate):
            selected.append(candidate)
            continue

        if is_hero_subtitle(candidate):
            selected.append(candidate)
            continue

        if is_cta_button(candidate):
            selected.append(candidate)
            continue

        if is_hero_image(candidate):
            selected.append(candidate)
            continue

        # 必排除規則
        if is_footer_copyright(candidate):
            excluded.append(candidate)
            continue

        if is_brand_declaration(candidate):
            excluded.append(candidate)
            continue

        if is_design_setting(candidate):
            excluded.append(candidate)
            continue

        # 未決定的候選
        yield candidate

def is_hero_title(candidate: dict) -> bool:
    """Check if candidate is hero title"""
    path = candidate['path'].lower()
    return ('hero' in path or 'banner' in path) and candidate['field_name'] == 'title'

def is_cta_button(candidate: dict) -> bool:
    """Check if candidate is CTA button"""
    return candidate['field_name'] in ['button_text', 'button_url']

def is_hero_image(candidate: dict) -> bool:
    """Check if candidate is hero image"""
    path = candidate['path'].lower()
    return ('hero' in path or 'banner' in path) and candidate['field_name'] == 'image_url'

def is_footer_copyright(candidate: dict) -> bool:
    """Check if candidate is footer copyright"""
    path = candidate['path'].lower()
    return 'footer' in path and ('copyright' in path or '©' in candidate.get('value', ''))

def is_brand_declaration(candidate: dict) -> bool:
    """Check if candidate is brand declaration"""
    value = candidate.get('value', '').lower()
    return 'all rights reserved' in value or 'powered by' in value

def is_design_setting(candidate: dict) -> bool:
    """Check if candidate is design setting (should not be slotted)"""
    # 檢查是否在設計設定區塊
    path = candidate['path'].lower()
    design_keywords = ['spacing', 'color', 'font', 'animation', 'breakpoint', 'css']
    return any(keyword in path for keyword in design_keywords)
```

**輸出**：
- `hard_selected`: 硬規則必選的 slots
- `hard_excluded`: 硬規則必排除的 slots
- `undecided_candidates`: 未決定的候選（交給 LLM）

#### 步驟 3.2: LLM 輔助分類（語意判斷）

對未決定的候選，使用 LLM 做「語意判斷」（不是視覺決策）：

**LLM Prompt 結構**：

```
你是一個 Divi 模板分析專家。請分析以下候選欄位，判斷它們是否應該被「Slot 化」（即：每次生成頁面時需要填入不同內容的欄位）。

**Slot 化的標準**：
- ✅ 應該 Slot：內容性文字（標題、描述、正文）、CTA 按鈕、主要圖片
- ❌ 不應該 Slot：固定版權聲明、品牌宣告、導航固定字樣、設計設定（spacing/color/font）

**候選欄位列表**：
{candidate_list_json}

**任務**：
對每個候選欄位，判斷：
1. `should_slot`: true/false
2. `slot_type`: text/url/image
3. `max_length`: 建議最大字數（如果是文字類）
4. `reason`: 判斷理由（簡短說明）

**輸出格式**：JSON 陣列，每個元素對應一個候選欄位。
```

**LLM 調用**：

```python
async def llm_classify_slots(undecided_candidates: list) -> list:
    """Use LLM to classify undecided candidate slots"""
    # 構建 prompt
    prompt = build_classification_prompt(undecided_candidates)

    # 調用 LLM（使用 cloud_capability.call 或直接調用 LLM）
    response = await call_llm(prompt, temperature=0.3)

    # 解析 LLM 回應
    classifications = parse_llm_response(response)

    return classifications
```

**輸出**：
- `llm_classified_slots`: LLM 分類結果（包含 should_slot, slot_type, max_length, reason）

#### 步驟 3.3: 合併選中 Slots

合併硬規則選中的和 LLM 判斷為 `should_slot=true` 的候選：

```python
def merge_selected_slots(hard_selected: list, llm_classified: list) -> list:
    """Merge hard-selected and LLM-classified slots"""
    selected = []

    # 加入硬規則選中的
    for slot in hard_selected:
        selected.append({
            **slot,
            'selection_reason': 'hard_rule'
        })

    # 加入 LLM 判斷為應該 slot 的
    for classification in llm_classified:
        if classification['should_slot']:
            # 找到對應的候選
            candidate = find_candidate_by_path(classification['path'])
            selected.append({
                **candidate,
                'slot_type': classification['slot_type'],
                'max_length': classification.get('max_length'),
                'selection_reason': 'llm_classified',
                'llm_reason': classification.get('reason')
            })

    return selected
```

**驗證選中數量**：
- 確保選中的 slot 數量在合理範圍（例如 8～30 個）
- 如果太少（< 5），警告用戶可能遺漏重要欄位
- 如果太多（> 40），警告用戶可能選到不該 slot 的欄位

**輸出**：
- `selected_slots`: 最終選中的 slots 列表（10～20 個）

### Phase 4: Slot ID 命名（可重現、可追蹤）

#### 步驟 4.1: 生成 Slot ID（機器穩定 key）

使用「JSON path + module_id + field_name」hash 出來，確保可重現：

```python
import hashlib

def generate_slot_id(candidate: dict) -> str:
    """Generate stable slot ID from candidate"""
    # 構建唯一識別字串
    identifier = f"{candidate['path']}|{candidate.get('module_id', '')}|{candidate['field_name']}"

    # Hash 並取前 8 字元
    hash_obj = hashlib.md5(identifier.encode())
    hash_short = hash_obj.hexdigest()[:8]

    # 組合：s_{hash}_{field_name}
    return f"s_{hash_short}_{candidate['field_name']}"
```

**輸出**：
- `slot_id`: 機器穩定的 key（例如：`s_7f2a9c_title`）

#### 步驟 4.2: 生成 Slot Alias（人類可讀）

使用 LLM 或規則給一個別名：

**規則優先**（如果規則能判斷）：

```python
def generate_slot_alias(candidate: dict, slot_id: str) -> str:
    """Generate human-readable alias for slot"""
    # 規則優先
    if is_hero_title(candidate):
        return 'hero_title'

    if is_hero_subtitle(candidate):
        return 'hero_subtitle'

    if is_cta_button_text(candidate):
        return 'cta_button_text'

    if is_cta_button_url(candidate):
        return 'cta_button_url'

    if is_hero_image(candidate):
        return 'hero_image'

    # 如果規則無法判斷，使用 LLM 生成
    return llm_generate_alias(candidate, slot_id)
```

**LLM 生成 Alias**（如果規則無法判斷）：

```python
async def llm_generate_alias(candidate: dict, slot_id: str) -> str:
    """Use LLM to generate human-readable alias"""
    prompt = f"""
    為以下 Divi 模板欄位生成一個簡潔、有意義的別名（alias）：

    - 路徑：{candidate['path']}
    - 模組類型：{candidate['module_type']}
    - 欄位名稱：{candidate['field_name']}
    - 現有內容片段：{candidate['value'][:50]}...

    **要求**：
    - 使用 snake_case
    - 簡潔（不超過 20 字元）
    - 有意義（能清楚表達欄位用途）
    - 英文

    **範例**：
    - hero_title
    - cta_button_text
    - feature_description
    - testimonial_author

    只輸出別名，不要其他文字。
    """

    response = await call_llm(prompt, temperature=0.5)
    return response.strip()
```

**輸出**：
- `slot_alias`: 人類可讀的別名（例如：`hero_title`）

### Phase 5: Patch Template（插入 Slot 佔位符）

#### 步驟 5.1: 替換欄位值為 `{{slot_id}}`

對選中的每個 slot，在原始 JSON 中找到對應欄位，替換為 `{{slot_id}}`：

```python
from capabilities.web_generation.services.divi.divi_slotizer import patch_template

# 使用集成 CSS ID 的 patch_template 函数
# 此函数會自動：
# 1. 為每個模組生成 CSS ID（基於 slot_id）
# 2. 將 CSS ID 添加到模組的 css_id 屬性
# 3. 替換欄位值為 slot 佔位符

patched_json = patch_template(template_json, selected_slots)

def get_nested_value(obj: dict, path: str) -> any:
    """Get nested value from JSON by path"""
    keys = path.split('.')
    current = obj
    for key in keys:
        if '[' in key:
            # 處理陣列索引
            key_part, index_part = key.split('[')
            index = int(index_part.rstrip(']'))
            current = current[key_part][index]
        else:
            current = current[key]
    return current

def set_nested_value(obj: dict, path: str, value: any):
    """Set nested value in JSON by path"""
    keys = path.split('.')
    current = obj
    for key in keys[:-1]:
        if '[' in key:
            key_part, index_part = key.split('[')
            index = int(index_part.rstrip(']'))
            current = current[key_part][index]
        else:
            current = current[key]

    final_key = keys[-1]
    if '[' in final_key:
        key_part, index_part = final_key.split('[')
        index = int(index_part.rstrip(']'))
        current[key_part][index] = value
    else:
        current[final_key] = value
```

**輸出**：
- `template_patched_json`: 已插入 `{{slot_id}}` 的模板 JSON，且模組已包含 CSS ID

#### 步驟 5.2: 為 Shortcode 格式頁面添加 CSS ID（如果適用）

如果頁面使用 `post_content` (shortcode) 格式而非 `_et_pb_builder_data` (JSON) 格式，需要為 shortcode 添加 CSS ID：

```python
from capabilities.web_generation.services.divi.divi_slotizer import (
    patch_post_content_with_css_ids,
    build_slots_schema
)

# 1. 先構建 slot schema（包含 CSS ID）
slot_schema = build_slots_schema(selected_slots, template_id)

# 2. 準備 match_attributes 映射（用於定位 shortcode）
# 例如：{'s_7f2a9c_desc_text': {'label': 'MINDFULLNESS'}}
match_attributes_map = {}
for slot in selected_slots:
    slot_id = slot['slot_id']
    # 從 slot 元數據提取定位屬性
    match_attrs = {}
    if 'label' in slot:
        match_attrs['label'] = slot['label']
    if 'title' in slot:
        match_attrs['title'] = slot['title']
    if match_attrs:
        match_attributes_map[slot_id] = match_attrs

# 3. 獲取頁面的 post_content
post_content = get_post_content(page_id)  # 需要實現此函數

# 4. 為 shortcode 添加 CSS ID
updated_content = patch_post_content_with_css_ids(
    post_content,
    slot_schema,
    match_attributes_map
)

# 5. 保存更新後的 post_content
update_post_content(page_id, updated_content)  # 需要實現此函數
```

**重要**：
- CSS ID 格式：`slot-{base_slot_id}`（例如：`slot-s-7f2a9c`）
- CSS ID 會添加到 shortcode 的 `css_id` 屬性中
- 如果 shortcode 已有 `css_id`，不會覆蓋

**輸出**：
- `updated_post_content`: 已添加 CSS ID 的 post_content

#### 步驟 5.3: 保存 Patched Template

**必須**使用 `filesystem_write_file` 工具保存處理後的模板：

- **文件路徑**：`templates/divi/patched/{template_id}.json`
- **完整路徑**：`sandboxes/{workspace_id}/{project_type}/{project_id}/templates/divi/patched/{template_id}.json`

### Phase 6: 生成 Slots Schema

#### 步驟 6.1: 構建 Slots Schema 結構

生成 `slots.schema.json`，定義所有 slot 的類型、限制、預設值：

```python
from capabilities.web_generation.services.divi.divi_slotizer import build_slots_schema

# 使用集成 CSS ID 的 build_slots_schema 函数
# 此函数會自動：
# 1. 為每個 slot 生成 CSS ID（基於 slot_id）
# 2. 將 CSS ID 添加到 slot_schema 中
# 3. 包含所有必要的 slot 元數據

slot_schema = build_slots_schema(selected_slots, template_id)

# slot_schema 現在包含每個 slot 的 css_id 欄位：
# {
#   'slot_id': 's_7f2a9c_desc_text',
#   'css_id': 'slot-s-7f2a9c',  # 自動生成
#   'module_type': 'dipi_carousel_child',
#   ...
# }
```

**輸出**：
- `slots_schema`: Slots Schema JSON 物件，**已包含 CSS ID**

**重要**：`build_slots_schema()` 函數會自動為每個 slot 生成並包含 `css_id` 欄位：
```json
{
  "slot_id": "s_7f2a9c_desc_text",
  "css_id": "slot-s-7f2a9c",  // 自動生成
  "module_type": "dipi_carousel_child",
  "field_name": "desc_text",
  ...
}
```

#### 步驟 6.2: 保存 Slots Schema

**必須**使用 `filesystem_write_file` 工具保存：

- **文件路徑**：`templates/divi/schemas/{template_id}.slots.schema.json`
- **完整路徑**：`sandboxes/{workspace_id}/{project_type}/{project_id}/templates/divi/schemas/{template_id}.slots.schema.json`

### Phase 7: 註冊 Template（Template Registry）

#### 步驟 7.1: 構建 Template Registry Entry

生成 `template.registry.json` 或更新 registry：

```python
def build_registry_entry(
    template_id: str,
    template_name: str,
    template_hash: str,
    context: str,
    slot_count: int,
    template_file_path: str
) -> dict:
    """Build template registry entry"""
    return {
        'template_id': template_id,
        'template_name': template_name,
        'template_hash': template_hash,
        'context': context,
        'slot_count': slot_count,
        'version': '1.0.0',
        'created_at': datetime.now().isoformat(),
        'template_file_path': template_file_path,
        'patched_template_path': f"templates/divi/patched/{template_id}.json",
        'schema_path': f"templates/divi/schemas/{template_id}.slots.schema.json",
        'tags': [],  # 可選：用途標籤
        'description': ''  # 可選：模板描述
    }
```

**輸出**：
- `registry_entry`: Template Registry Entry JSON 物件

#### 步驟 7.2: 保存或更新 Registry

**選項 1：單一檔案 Registry**（推薦用於 PoC）：

- **文件路徑**：`templates/divi/registry.json`
- 讀取現有 registry（如果存在）
- 添加或更新 entry
- 保存回檔案

**選項 2：分散式 Registry**（每個模板一個 entry 檔案）：

- **文件路徑**：`templates/divi/registry/{template_id}.registry.json`
- 直接保存 entry 檔案

**必須**使用 `filesystem_write_file` 工具保存。

### Phase 8: Validator（驗證）

#### 步驟 8.1: JSON 語法驗證

- 檢查 `template_patched_json` 是否為有效 JSON
- 檢查 `slots_schema` 是否為有效 JSON
- 檢查 `registry_entry` 是否為有效 JSON

#### 步驟 8.2: Slot 數量驗證

- 檢查 `slot_count` 是否在合理範圍（8～30）
- 如果 < 5，警告「可能遺漏重要欄位」
- 如果 > 40，警告「可能選到不該 slot 的欄位」

#### 步驟 8.3: Slot 類型格式驗證

- 檢查所有 `url` slot 的值是否符合 URL/路徑格式
- 檢查所有 `image` slot 的值是否符合 URL 或 attachment id 格式
- 檢查所有 `text` slot 的值是否在 `max_length` 限制內

#### 步驟 8.4: Placeholder 位置驗證

- 檢查 `{{slot_id}}` 是否出現在「設計設定欄位」（不應該出現）
- 如果發現，標記為錯誤並排除該 slot

#### 步驟 8.5: Context 驗證（可選但強烈建議）

**匯入到 Staging Site 做一次實測**：

1. 將 `template_patched.json` 匯入到 staging WordPress 站點
2. 檢查是否出現 *This file should not be imported in this context* 錯誤
3. 如果出現錯誤，直接 fail（表示 registry 的 context 判斷錯誤）

**注意**：此步驟需要 WordPress 環境，如果沒有 staging site，可以跳過但會標記為「未驗證」。

**輸出**：
- `validation_results`: 驗證結果字典
- `validation_passed`: true/false
- `validation_warnings`: 警告列表
- `validation_errors`: 錯誤列表

### Phase 9: 註冊 Artifacts

#### 步驟 9.1: 註冊產出 Artifacts

**必須**使用 `artifact_registry.register_artifact` 註冊產出的 artifacts：

1. **Patched Template**：
   - **artifact_id**：`divi_template_patched_{template_id}`
   - **artifact_type**：`divi_template`
   - **path**：`templates/divi/patched/{template_id}.json`

2. **Slots Schema**：
   - **artifact_id**：`divi_slots_schema_{template_id}`
   - **artifact_type**：`json_schema`
   - **path**：`templates/divi/schemas/{template_id}.slots.schema.json`

3. **Template Registry Entry**：
   - **artifact_id**：`divi_template_registry_{template_id}`
   - **artifact_type**：`registry_entry`
   - **path**：`templates/divi/registry/{template_id}.registry.json` 或 `templates/divi/registry.json`

### Phase 10: 執行記錄保存

#### 步驟 10.1: 保存對話歷史

**必須**使用 `filesystem_write_file` 工具保存完整的對話歷史：

- 文件路徑: `artifacts/divi_slotizer/{{execution_id}}/conversation_history.json`
- 內容: 完整的對話歷史（包含所有 user 和 assistant 消息）
- 格式: JSON 格式，包含時間戳和角色信息

#### 步驟 10.2: 保存執行摘要

**必須**使用 `filesystem_write_file` 工具保存執行摘要：

- 文件路徑: `artifacts/divi_slotizer/{{execution_id}}/execution_summary.md`
- 內容:
  - 執行時間
  - 執行 ID
  - Playbook 名稱
  - 輸入模板檔案路徑
  - Template ID
  - Template Hash
  - Context
  - Slot 數量
  - 生成的檔案列表
  - 驗證結果
  - 警告和錯誤（如有）

## Runtime 使用流程（後續工作流）

後續的 web-generation 流程使用 Slotizer 產出的模板：

### 1. LLM 選 Template

從 Template Registry 選擇 `template_id`：

```python
# 讀取 registry
registry = load_template_registry()

# LLM 根據需求選擇合適的模板
selected_template_id = llm_select_template(user_requirements, registry)
```

### 2. LLM 產出 Slot Values

根據 `slots.schema.json` 產出 slot 值：

```python
# 讀取 slots schema
schema = load_slots_schema(selected_template_id)

# LLM 產出 slot values
slot_values = llm_generate_slot_values(user_content, schema)
```

### 3. 生成 Page JSON

將 `template_patched.json` 複製一份，替換所有 `{{slot_id}}` 為實際內容：

```python
# 讀取 patched template
page_json = load_patched_template(selected_template_id)

# 替換 slot 佔位符
for slot_id, value in slot_values.items():
    page_json_str = page_json_str.replace(f"{{{{{slot_id}}}}}", value)

# 保存為新頁面 JSON
save_page_json(page_json, f"pages/{page_id}.json")
```

### 4. 匯入到 WordPress

將生成的 `page_json` 匯入到 WordPress（透過 Divi Portability）：

- 確保匯入到正確的 context（根據 registry 的 context）
- 檢查匯入是否成功
- 如果失敗，記錄錯誤並回報

## 成功標準

- ✅ Template Hash 已計算
- ✅ Context 已正確識別
- ✅ Template ID 已生成
- ✅ 候選 Slots 已掃描（30～80 個）
- ✅ 最終選中 Slots（10～20 個）
- ✅ Slot ID 和 Alias 已生成
- ✅ Template 已 Patch（插入 `{{slot_id}}`）
- ✅ Slots Schema 已生成
- ✅ Template Registry Entry 已創建
- ✅ 所有驗證通過
- ✅ Artifacts 已註冊
- ✅ 執行記錄已保存

## 注意事項

- **Project Context**：必須在 web_page 或 website project 的 context 中執行
- **輸入檔案格式**：必須是 Divi Portability 匯出的有效 JSON
- **Context 判斷**：必須正確識別 context，否則匯入會失敗
- **Slot 數量**：建議在 8～30 個之間，太少可能遺漏重要欄位，太多可能選到不該 slot 的欄位
- **可重現性**：Slot ID 使用 hash 生成，確保模板改版後仍能對應到相同 slot
- **Staging 驗證**：強烈建議在 staging site 驗證 context 判斷是否正確

## 相關文檔

- **Template Registry 對照表**：`docs/divi/divi_template_registry_reference.md`
- **Slotizer 實現指南**：`docs/divi/divi_slotizer_implementation_guide.md`
- **Slot Schema 範例**：`docs/divi/divi_slot_schema_examples.md`
- **Divi Portability 文檔**：https://www.elegantthemes.com/documentation/divi/library-import/
- **Context 錯誤修復指南**：https://help.elegantthemes.com/en/articles/2612617-how-to-fix-the-this-file-should-not-be-imported-in-this-context-error-when-importing-a-json-file

