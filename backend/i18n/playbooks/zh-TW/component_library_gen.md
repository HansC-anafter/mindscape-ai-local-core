---
playbook_code: component_library_gen
version: 1.0.0
capability_code: web_generation
name: 組件庫生成
description: |
  從 site_spec.yaml 的 components 配置生成完整的組件庫，包括 Header、Footer、Section 組件和基礎 UI 組件。
  這是完整網站生成流程的第三步，為後續多頁面組裝提供可重用的組件基礎。
tags:
  - web
  - components
  - react
  - ui-library
  - code-generation

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
icon: 🧩
---

# 組件庫生成 - SOP

## 目標

從 `spec/site_spec.yaml` 的 `components` 配置生成完整的組件庫，包括：
- Header 組件（`components/Header.tsx`）
- Footer 組件（`components/Footer.tsx`）
- Section 組件（Features, CTA, About 等）
- 基礎 UI 組件（Button, Card, Input 等）

輸出到 Project Sandbox 的 `components/` 目錄。

**工作流程說明**：
- 這是完整網站生成流程的**第三步**：生成組件庫
- 必須在 `site_spec_generation` 和 `style_system_gen` playbook 之後執行
- 生成的組件將被後續的多頁面組裝使用

## 執行步驟

### Phase 0: 檢查 Project Context

#### 步驟 0.0: 取得 Brand Context

在開始生成組件庫之前，先取得品牌的基礎設定，特別是品牌個性和調性。

**取得品牌設定**：

```tool
cloud_capability.call
capability: brand_identity
endpoint: context/get
params:
  workspace_id: {workspace_id}
  auto_generate: true
  min_data_required: true
```

**Brand Context 的使用指引**：

如果 `has_brand_context = true`，在後續生成組件時，請參考：

1. **組件個性與調性**：
   - 參考 `brand_mi.vision` 和 `brand_mi.worldview` 來決定組件的整體風格
   - 參考 `brand_mi.values` 來確保組件設計符合品牌價值
   - 參考 `brand_mi.redlines` 來避免不符合品牌調性的設計

2. **受眾需求**：
   - 參考 `brand_personas[].needs` 來設計組件的功能
   - 參考 `brand_personas[].pain_points` 來規劃組件要解決的問題
   - 根據不同 persona 的需求，設計相應的組件變體

3. **品牌故事主軸**：
   - 參考 `brand_storylines[].theme` 和 `brand_storylines[].key_messages` 來決定組件的內容和訊息
   - 確保組件能夠有效傳達品牌故事

4. **組件文案與互動**：
   - 根據品牌個性決定組件的文案風格（正式、親和、創新等）
   - 根據品牌調性決定互動方式（動畫、過渡效果等）

**Brand Context 來源提示**：

- 如果 `metadata.source = "existing_artifacts"`：使用現有的品牌設定
- 如果 `metadata.source = "auto_generated"`：
  - 這些品牌設定是基於現有數據自動生成的
  - 建議後續執行 `cis_mind_identity` playbook 建立更完整的品牌定義
  - 當前生成的組件可以基於這些臨時設定開始，後續可以調整

**如果沒有 Brand Context**：

如果 `has_brand_context = false`：
- 提示用戶：「建議先執行 `cis_mind_identity` playbook 建立品牌設定，這樣生成的組件會更符合品牌調性。」
- 可以繼續生成，但提醒「未參考品牌設定，後續可能需要調整」

#### 步驟 0.1: 檢查是否有活躍的 web_page 或 website project
- 檢查 execution context 中是否有 `project_id`
- 如果有，確認 project type 為 `web_page` 或 `website`
- 如果沒有，提示用戶需要先創建 project

#### 步驟 0.2: 獲取 Project Sandbox 路徑
- 使用 `project_sandbox_manager.get_sandbox_path()` 獲取 sandbox 路徑
- Sandbox 路徑結構：`sandboxes/{workspace_id}/{project_type}/{project_id}/`
- 確保 `components/` 目錄存在

#### 步驟 0.3: 檢查依賴文件
檢查以下文件是否存在：
- `spec/site_spec.yaml`（從 `site_spec_generation` 生成）
- `styles/variables.css`（從 `style_system_gen` 生成）
- `styles/global.css`（從 `style_system_gen` 生成）
- `tailwind.config.js`（從 `style_system_gen` 生成）

如果任何一個不存在，提示用戶需要先執行對應的 playbook。

### Phase 1: 解析組件需求

#### 步驟 1.1: 讀取 site_spec.yaml
**必須**使用 `filesystem_read_file` 工具讀取網站規格文檔：

- **文件路徑**：`spec/site_spec.yaml`（在 Project Sandbox 中）
- **完整路徑**：`sandboxes/{workspace_id}/{project_type}/{project_id}/spec/site_spec.yaml`

#### 步驟 1.2: 提取 Components 配置
從 `site_spec.yaml` 中提取 `components` 列表：
- 每個組件的 `component_id`、`component_type`、`required`、`config`
- 根據 `component_type` 分類：
  - `header`: Header 組件
  - `footer`: Footer 組件
  - `section`: Section 組件（Features, CTA, About 等）
  - `ui`: 基礎 UI 組件（Button, Card, Input 等）

#### 步驟 1.3: 提取 Navigation 配置
從 `site_spec.yaml` 中提取 `navigation` 配置：
- `navigation.top`: 頂部導航項目
- `navigation.sidebar`: 側邊欄導航項目
- `navigation.footer`: 頁尾導航項目

#### 步驟 1.4: 提取 Theme 配置
從 `site_spec.yaml` 中提取 `theme` 配置：
- 用於確保組件使用一致的樣式

### Phase 2: 生成 Header 組件

#### 步驟 2.1: 檢查 Header 需求
- 檢查 `components` 列表中是否有 `component_type: "header"` 的組件
- 如果沒有但導航存在，自動創建 Header 組件需求
- 讀取 Header 組件的 `config` 配置

#### 步驟 2.2: 構建 Header 組件結構
根據配置和 Brand Context 生成 Header 組件：

**如果有 Brand Context**：
- 參考 `brand_mi.values` 和 `brand_mi.worldview` 來決定 Header 的風格（正式、親和、創新等）
- 參考 `brand_personas` 來決定導航項目的優先順序和分類
- 參考 `brand_storylines` 來決定導航項目的命名和組織方式

```typescript
'use client'

import Link from 'next/link'
import { useState } from 'react'

interface HeaderProps {
  // Props based on component config
}

export default function Header({ ...props }: HeaderProps) {
  const [isMenuOpen, setIsMenuOpen] = useState(false)

  return (
    <header className="sticky top-0 z-50 bg-white/80 backdrop-blur-sm border-b border-neutral-200">
      <nav className="container-custom flex items-center justify-between h-16">
        {/* Logo */}
        {config.show_logo && (
          <Link href="/" className="flex items-center space-x-2">
            <span className="text-2xl font-heading font-bold text-primary">
              {site.title}
            </span>
          </Link>
        )}

        {/* Desktop Navigation */}
        {config.show_navigation && navigation.top && (
          <div className="hidden md:flex items-center space-x-8">
            {navigation.top.map((item) => (
              <Link
                key={item.route}
                href={item.route}
                className="text-neutral-700 hover:text-primary transition-colors"
              >
                {item.label}
              </Link>
            ))}
          </div>
        )}

        {/* Mobile Menu Button */}
        <button
          className="md:hidden p-2"
          onClick={() => setIsMenuOpen(!isMenuOpen)}
        >
          {/* Menu Icon */}
        </button>
      </nav>

      {/* Mobile Menu */}
      {isMenuOpen && (
        <div className="md:hidden border-t border-neutral-200">
          {/* Mobile Navigation Items */}
        </div>
      )}
    </header>
  )
}
```

#### 步驟 2.3: 生成 Header.tsx
**必須**使用 `filesystem_write_file` 工具保存 Header 組件：

- **文件路徑**：`components/Header.tsx`（在 Project Sandbox 中）
- **完整路徑**：`sandboxes/{workspace_id}/{project_type}/{project_id}/components/Header.tsx`

### Phase 3: 生成 Footer 組件

#### 步驟 3.1: 檢查 Footer 需求
- 檢查 `components` 列表中是否有 `component_type: "footer"` 的組件
- 如果沒有，根據常見需求自動創建 Footer 組件
- 讀取 Footer 組件的 `config` 配置

#### 步驟 3.2: 構建 Footer 組件結構
根據配置和 Brand Context 生成 Footer 組件：

**如果有 Brand Context**：
- 參考 `brand_mi.vision` 來決定 Footer 要傳達的核心訊息
- 參考 `brand_storylines` 來決定 Footer 連結的組織方式

```typescript
import Link from 'next/link'

interface FooterProps {
  // Props based on component config
}

export default function Footer({ ...props }: FooterProps) {
  const currentYear = new Date().getFullYear()

  return (
    <footer className="bg-neutral-900 text-neutral-300">
      <div className="container-custom py-12">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-8">
          {/* Brand Section */}
          <div className="col-span-1 md:col-span-2">
            <h3 className="text-xl font-heading font-bold text-white mb-4">
              {site.title}
            </h3>
            <p className="text-neutral-400">{site.description}</p>
          </div>

          {/* Navigation Links */}
          {navigation.footer && navigation.footer.length > 0 && (
            <div>
              <h4 className="text-white font-semibold mb-4">Links</h4>
              <ul className="space-y-2">
                {navigation.footer.map((item) => (
                  <li key={item.route}>
                    <Link
                      href={item.route}
                      className="hover:text-white transition-colors"
                    >
                      {item.label}
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Contact Info */}
          <div>
            <h4 className="text-white font-semibold mb-4">Contact</h4>
            {/* Contact information */}
          </div>
        </div>

        {/* Copyright */}
        {config.show_copyright && (
          <div className="mt-8 pt-8 border-t border-neutral-800 text-center text-sm text-neutral-500">
            <p>&copy; {currentYear} {site.title}. All rights reserved.</p>
          </div>
        )}
      </div>
    </footer>
  )
}
```

#### 步驟 3.3: 生成 Footer.tsx
**必須**使用 `filesystem_write_file` 工具保存 Footer 組件：

- **文件路徑**：`components/Footer.tsx`

### Phase 4: 生成 Section 組件

#### 步驟 4.1: 識別需要的 Section 組件
根據 `components` 列表和 `pages` 配置識別需要的 Section 組件：
- Features Section（如果頁面中有 features）
- CTA Section（如果頁面中有 call-to-action）
- About Section（如果頁面中有 about）
- 其他自訂 Section

#### 步驟 4.2: 生成 Features Section
如果需要的話，生成 Features Section 組件：

**如果有 Brand Context**：
- 參考 `brand_storylines[].key_messages` 來決定 Features 要強調的價值點
- 參考 `brand_personas[].needs` 來決定 Features 要解決的問題

```typescript
interface Feature {
  title: string
  description: string
  icon?: string
}

interface FeaturesProps {
  features: Feature[]
  layout?: 'grid' | 'list' | 'timeline'
  columns?: number
}

export default function Features({
  features,
  layout = 'grid',
  columns = 3,
}: FeaturesProps) {
  return (
    <section className="section-padding bg-neutral-50">
      <div className="container-custom">
        <h2 className="text-3xl font-heading font-bold text-center mb-12">
          Features
        </h2>
        <div
          className={`grid grid-cols-1 md:grid-cols-${columns} gap-8`}
        >
          {features.map((feature, index) => (
            <div
              key={index}
              className="bg-white p-6 rounded-lg shadow-sm hover:shadow-md transition-shadow"
            >
              {feature.icon && (
                <div className="text-4xl mb-4">{feature.icon}</div>
              )}
              <h3 className="text-xl font-semibold mb-2">{feature.title}</h3>
              <p className="text-neutral-600">{feature.description}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}
```

#### 步驟 4.3: 生成 CTA Section
生成 CTA (Call-to-Action) Section 組件：

**如果有 Brand Context**：
- 參考 `brand_storylines[].key_messages` 來決定 CTA 的文案和訊息
- 參考 `brand_mi.values` 來決定 CTA 的調性和風格

```typescript
interface CTAProps {
  title: string
  description?: string
  buttonText: string
  buttonLink: string
  variant?: 'primary' | 'secondary'
}

export default function CTA({
  title,
  description,
  buttonText,
  buttonLink,
  variant = 'primary',
}: CTAProps) {
  return (
    <section className="section-padding bg-primary text-white">
      <div className="container-custom text-center">
        <h2 className="text-3xl font-heading font-bold mb-4">{title}</h2>
        {description && <p className="text-lg mb-8">{description}</p>}
        <Link
          href={buttonLink}
          className={`inline-block px-8 py-4 rounded-lg font-semibold transition-all ${
            variant === 'primary'
              ? 'bg-white text-primary hover:bg-neutral-100'
              : 'bg-transparent border-2 border-white hover:bg-white/10'
          }`}
        >
          {buttonText}
        </Link>
      </div>
    </section>
  )
}
```

#### 步驟 4.4: 生成其他 Section 組件
根據需要生成其他 Section 組件（About, Testimonials, Pricing 等）。

#### 步驟 4.5: 保存所有 Section 組件
**必須**使用 `filesystem_write_file` 工具保存每個 Section 組件：

- `components/sections/Features.tsx`
- `components/sections/CTA.tsx`
- `components/sections/About.tsx`
- 其他 sections...

### Phase 5: 生成基礎 UI 組件

#### 步驟 5.1: 生成 Button 組件
生成可重用的 Button 組件：

```typescript
import Link from 'next/link'
import { ButtonHTMLAttributes } from 'react'

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'outline'
  size?: 'sm' | 'md' | 'lg'
  href?: string
  as?: 'button' | 'link'
}

export default function Button({
  variant = 'primary',
  size = 'md',
  href,
  as = 'button',
  children,
  className = '',
  ...props
}: ButtonProps) {
  const baseStyles = 'font-semibold rounded-lg transition-all'
  const variants = {
    primary: 'bg-primary text-white hover:bg-primary/90',
    secondary: 'bg-secondary text-white hover:bg-secondary/90',
    outline: 'border-2 border-primary text-primary hover:bg-primary hover:text-white',
  }
  const sizes = {
    sm: 'px-4 py-2 text-sm',
    md: 'px-6 py-3',
    lg: 'px-8 py-4 text-lg',
  }

  const classes = `${baseStyles} ${variants[variant]} ${sizes[size]} ${className}`

  if (as === 'link' && href) {
    return (
      <Link href={href} className={classes}>
        {children}
      </Link>
    )
  }

  return (
    <button className={classes} {...props}>
      {children}
    </button>
  )
}
```

#### 步驟 5.2: 生成 Card 組件
生成可重用的 Card 組件：

```typescript
interface CardProps {
  title?: string
  description?: string
  children?: React.ReactNode
  className?: string
  hover?: boolean
}

export default function Card({
  title,
  description,
  children,
  className = '',
  hover = false,
}: CardProps) {
  return (
    <div
      className={`bg-white rounded-lg shadow-sm p-6 ${
        hover ? 'hover:shadow-md transition-shadow' : ''
      } ${className}`}
    >
      {title && (
        <h3 className="text-xl font-semibold mb-2">{title}</h3>
      )}
      {description && (
        <p className="text-neutral-600 mb-4">{description}</p>
      )}
      {children}
    </div>
  )
}
```

#### 步驟 5.3: 生成 Input 組件
生成可重用的 Input 組件：

```typescript
import { InputHTMLAttributes } from 'react'

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string
  error?: string
}

export default function Input({
  label,
  error,
  className = '',
  ...props
}: InputProps) {
  return (
    <div className="w-full">
      {label && (
        <label className="block text-sm font-medium text-neutral-700 mb-2">
          {label}
        </label>
      )}
      <input
        className={`w-full px-4 py-2 border border-neutral-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent ${
          error ? 'border-error' : ''
        } ${className}`}
        {...props}
      />
      {error && (
        <p className="mt-1 text-sm text-error">{error}</p>
      )}
    </div>
  )
}
```

#### 步驟 5.4: 保存所有 UI 組件
**必須**使用 `filesystem_write_file` 工具保存每個 UI 組件：

- `components/ui/Button.tsx`
- `components/ui/Card.tsx`
- `components/ui/Input.tsx`
- 其他 UI 組件...

### Phase 6: 創建組件索引文件

#### 步驟 6.1: 生成 components/index.ts
生成組件導出索引文件：

```typescript
// Layout Components
export { default as Header } from './Header'
export { default as Footer } from './Footer'

// Section Components
export { default as Features } from './sections/Features'
export { default as CTA } from './sections/CTA'
export { default as About } from './sections/About'

// UI Components
export { default as Button } from './ui/Button'
export { default as Card } from './ui/Card'
export { default as Input } from './ui/Input'
```

#### 步驟 6.2: 保存 index.ts
**必須**使用 `filesystem_write_file` 工具保存索引文件：

- **文件路徑**：`components/index.ts`

### Phase 7: 驗證組件完整性

#### 步驟 7.1: 檢查必需組件
- 檢查所有 `required: true` 的組件是否都已生成
- 檢查組件文件是否存在且可讀

#### 步驟 7.2: 驗證組件依賴
- 檢查組件使用的樣式是否在 `styles/` 目錄中
- 檢查組件導入的路徑是否正確
- 確保組件使用統一的樣式系統

### Phase 8: 註冊 Artifacts

#### 步驟 8.1: 註冊組件庫 Artifacts
**必須**使用 `artifact_registry.register_artifact` 註冊產出的 artifacts：

1. **組件庫**：
   - **artifact_id**：`component_library`
   - **artifact_type**：`components`
   - **path**：`components/`

2. **Header 組件**：
   - **artifact_id**：`header_component`
   - **artifact_type**：`component`
   - **path**：`components/Header.tsx`

3. **Footer 組件**：
   - **artifact_id**：`footer_component`
   - **artifact_type**：`component`
   - **path**：`components/Footer.tsx`

### Phase 9: 執行記錄保存

#### 步驟 9.1: 保存對話歷史
**必須**使用 `filesystem_write_file` 工具保存完整的對話歷史：

- 文件路徑: `artifacts/component_library_gen/{{execution_id}}/conversation_history.json`

#### 步驟 9.2: 保存執行摘要
**必須**使用 `filesystem_write_file` 工具保存執行摘要：

- 文件路徑: `artifacts/component_library_gen/{{execution_id}}/execution_summary.md`
- 內容:
  - 執行時間
  - 執行 ID
  - Playbook 名稱
  - 生成的組件列表
  - 組件配置摘要
  - 驗證結果

## 個人化

基於使用者的 Mindscape 個人檔案：
- **技術等級**：若為「進階」，包含更多自訂選項和進階組件功能
- **詳細程度**：若偏好「高」，提供更詳細的組件註釋和文檔
- **工作風格**：若偏好「結構化」，提供更清晰的組件組織結構

## 與長期意圖的整合

若使用者有相關的活躍意圖（例如「建立品牌網站」），明確引用：
> "由於您正在進行「建立品牌網站」，我將根據您的品牌識別生成一致的組件庫..."

## 成功標準

- Header 組件已生成到 `components/Header.tsx`
- Footer 組件已生成到 `components/Footer.tsx`
- 所有需要的 Section 組件都已生成
- 基礎 UI 組件（Button, Card, Input）都已生成
- 組件索引文件已生成到 `components/index.ts`
- 所有組件使用統一的樣式系統
- 所有必需組件（`required: true`）都已生成
- Artifacts 已正確註冊
- 組件可以與後續的多頁面組裝無縫整合

## 注意事項

- **Project Context**：必須在 web_page 或 website project 的 context 中執行
- **依賴關係**：必須先執行 `site_spec_generation` 和 `style_system_gen` playbook
- **Sandbox 路徑**：確保使用 Project Sandbox 路徑，而非 artifacts 路徑
- **樣式一致性**：所有組件必須使用統一的樣式系統（CSS 變量、Tailwind 類）
- **組件可重用性**：組件設計應考慮可重用性，支持多頁面使用

## 相關文檔

- **Schema 定義**：`capabilities/web_generation/schema/site_spec_schema.py`
- **網站規格生成**：`capabilities/web_generation/playbooks/zh-TW/site_spec_generation.md`
- **樣式系統生成**：`capabilities/web_generation/playbooks/zh-TW/style_system_gen.md`
- **完整網站生成流程**：`capabilities/web_generation/docs/complete-pipeline-workflow.md`

