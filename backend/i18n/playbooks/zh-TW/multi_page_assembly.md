---
playbook_code: multi_page_assembly
version: 1.0.0
capability_code: web_generation
name: 多頁面組裝
description: |
  從 site_spec.yaml 的多頁面配置生成完整的多頁面網站，包括根 Layout、多頁面路由（Next.js App Router）和 SEO metadata。
  這是完整網站生成流程的第四步，整合所有組件和樣式，生成可部署的完整網站。
tags:
  - web
  - multi-page
  - nextjs
  - routing
  - seo
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

language_strategy: model_native
locale: zh-TW
supported_locales:
  - zh-TW
  - en
default_locale: zh-TW
auto_localize: true

entry_agent_type: coder
icon: 🏗️
---

# 多頁面組裝 - SOP

## 目標

從 `spec/site_spec.yaml` 的多頁面配置生成完整的多頁面網站，包括：
- 根 Layout 組件（整合 Header、Footer）
- 多頁面路由（Next.js App Router 結構）
- SEO metadata（每頁的 metadata）
- 頁面內容組件

輸出到 Project Sandbox 的 `app/` 目錄（Next.js App Router 結構）。

**工作流程說明**：
- 這是完整網站生成流程的**第四步**：多頁面組裝
- 必須在 `site_spec_generation`、`style_system_gen` 和 `component_library_gen` playbook 之後執行
- 生成的網站可以直接部署到生產環境

## 執行步驟

### Phase 0: 檢查 Project Context

#### 步驟 0.1: 檢查是否有活躍的 web_page 或 website project
- 檢查 execution context 中是否有 `project_id`
- 如果有，確認 project type 為 `web_page` 或 `website`
- 如果沒有，提示用戶需要先創建 project

#### 步驟 0.2: 獲取 Project Sandbox 路徑
- 使用 `project_sandbox_manager.get_sandbox_path()` 獲取 sandbox 路徑
- Sandbox 路徑結構：`sandboxes/{workspace_id}/{project_type}/{project_id}/`
- 確保 `app/` 目錄存在（Next.js App Router 結構）

#### 步驟 0.3: 檢查依賴文件
檢查以下文件是否存在：
- `spec/site_spec.yaml`（從 `site_spec_generation` 生成）
- `styles/variables.css`（從 `style_system_gen` 生成）
- `styles/global.css`（從 `style_system_gen` 生成）
- `tailwind.config.js`（從 `style_system_gen` 生成）
- `components/Header.tsx`（從 `component_library_gen` 生成）
- `components/Footer.tsx`（從 `component_library_gen` 生成）
- `components/index.ts`（從 `component_library_gen` 生成）

如果任何一個不存在，提示用戶需要先執行對應的 playbook。

### Phase 1: 解析網站規格

#### 步驟 1.1: 讀取 site_spec.yaml
**必須**使用 `filesystem_read_file` 工具讀取網站規格文檔：

- **文件路徑**：`spec/site_spec.yaml`（在 Project Sandbox 中）
- **完整路徑**：`sandboxes/{workspace_id}/{project_type}/{project_id}/spec/site_spec.yaml`

#### 步驟 1.2: 提取頁面配置
從 `site_spec.yaml` 中提取：
- `site`: 網站基礎信息（title, description, base_url, metadata）
- `pages`: 所有頁面配置列表
- `navigation`: 導航結構
- `theme`: 主題配置（用於驗證樣式一致性）

#### 步驟 1.3: 驗證頁面路由
- 確保所有頁面路由唯一
- 確保導航中的路由對應到實際頁面
- 驗證路由格式符合 Next.js App Router 規範

### Phase 2: 生成根 Layout

#### 步驟 2.1: 構建根 Layout 結構
生成 `app/layout.tsx`，整合 Header 和 Footer：

```typescript
import type { Metadata } from 'next'
import { Header, Footer } from '@/components'
import '@/styles/global.css'

export const metadata: Metadata = {
  title: {
    default: '{site.title}',
    template: '%s | {site.title}'
  },
  description: '{site.description}',
  metadataBase: new URL('{site.base_url}'),
  openGraph: {
    title: '{site.title}',
    description: '{site.description}',
    type: 'website',
  },
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="zh-TW">
      <body>
        <Header />
        <main className="min-h-screen">
          {children}
        </main>
        <Footer />
      </body>
    </html>
  )
}
```

#### 步驟 2.2: 生成 layout.tsx
**必須**使用 `filesystem_write_file` 工具保存根 Layout：

- **文件路徑**：`app/layout.tsx`（在 Project Sandbox 中）
- **完整路徑**：`sandboxes/{workspace_id}/{project_type}/{project_id}/app/layout.tsx`

### Phase 3: 生成頁面路由

#### 步驟 3.1: 處理首頁路由
生成 `app/page.tsx`（對應路由 `/`）：

```typescript
import type { Metadata } from 'next'
import { Features, CTA, About } from '@/components'

export const metadata: Metadata = {
  title: '{page.title}',
  description: '{page.metadata.seo_description || site.description}',
}

export default function HomePage() {
  return (
    <>
      {/* Hero Section - 如果有 hero 組件 */}
      {/* 根據 page.sections 渲染對應的 Section 組件 */}
      <Features features={[]} />
      <About />
      <CTA
        title="Get Started"
        buttonText="Contact Us"
        buttonLink="/contact"
      />
    </>
  )
}
```

#### 步驟 3.2: 處理動態路由
對於每個頁面，根據其 `route` 生成對應的路由文件：

**路由映射規則**：
- `/` → `app/page.tsx`
- `/about` → `app/about/page.tsx`
- `/chapters/chapter-1` → `app/chapters/chapter-1/page.tsx`
- `/chapters/chapter-1/section-1` → `app/chapters/chapter-1/section-1/page.tsx`

#### 步驟 3.3: 生成頁面組件模板
為每個頁面生成對應的頁面組件：

```typescript
import type { Metadata } from 'next'
import { Features, CTA } from '@/components'

export const metadata: Metadata = {
  title: '{page.title}',
  description: '{page.metadata.seo_description || site.description}',
  // 其他 SEO metadata
}

export default function {PageName}Page() {
  return (
    <div className="page-container">
      {/* 根據 page.sections 渲染對應的 Section 組件 */}
      {page.sections.includes('features') && (
        <Features features={[]} />
      )}
      {page.sections.includes('cta') && (
        <CTA
          title="Call to Action"
          buttonText="Learn More"
          buttonLink="/"
        />
      )}
      {/* 其他 sections */}
    </div>
  )
}
```

#### 步驟 3.4: 處理頁面內容來源
如果頁面有 `source` 配置（例如來自 Obsidian 的 Markdown 文件）：
- 讀取源文件內容
- 轉換為 React 組件可用的格式
- 整合到頁面組件中

#### 步驟 3.5: 生成所有頁面路由
**必須**使用 `filesystem_write_file` 工具為每個頁面生成路由文件：

- 根據 `pages` 列表遍歷所有頁面
- 為每個頁面生成對應的路由文件
- 確保目錄結構正確（例如 `app/chapters/chapter-1/` 需要先創建 `chapters/chapter-1/` 目錄）

### Phase 4: 生成 SEO Metadata

#### 步驟 4.1: 提取 SEO 信息
從每個頁面的配置中提取：
- `page.title`: 頁面標題
- `page.metadata.seo_title`: SEO 標題（如果有）
- `page.metadata.seo_description`: SEO 描述（如果有）
- `page.metadata.keywords`: 關鍵字（如果有）
- `site.metadata`: 網站級別的元數據

#### 步驟 4.2: 生成 Metadata 配置
為每個頁面生成完整的 Metadata 配置：

```typescript
export const metadata: Metadata = {
  title: page.metadata.seo_title || page.title,
  description: page.metadata.seo_description || site.description,
  keywords: page.metadata.keywords || site.metadata.keywords,
  openGraph: {
    title: page.metadata.seo_title || page.title,
    description: page.metadata.seo_description || site.description,
    url: `${site.base_url}${page.route}`,
    type: 'website',
  },
  twitter: {
    card: 'summary_large_image',
    title: page.metadata.seo_title || page.title,
    description: page.metadata.seo_description || site.description,
  },
}
```

#### 步驟 4.3: 生成 sitemap.xml（可選）
**可選**生成 `app/sitemap.ts` 或 `public/sitemap.xml`：

```typescript
import { MetadataRoute } from 'next'

export default function sitemap(): MetadataRoute.Sitemap {
  return [
    {
      url: `${site.base_url}`,
      lastModified: new Date(),
      changeFrequency: 'yearly',
      priority: 1,
    },
    // 其他頁面...
  ]
}
```

### Phase 5: 生成配置文件

#### 步驟 5.1: 生成 next.config.js
生成 Next.js 配置文件：

```javascript
/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  swcMinify: true,
  // 其他配置...
}

module.exports = nextConfig
```

#### 步驟 5.2: 生成 tsconfig.json
生成 TypeScript 配置文件：

```json
{
  "compilerOptions": {
    "target": "ES2020",
    "lib": ["dom", "dom.iterable", "esnext"],
    "allowJs": true,
    "skipLibCheck": true,
    "strict": true,
    "forceConsistentCasingInFileNames": true,
    "noEmit": true,
    "esModuleInterop": true,
    "module": "esnext",
    "moduleResolution": "bundler",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "jsx": "preserve",
    "incremental": true,
    "plugins": [
      {
        "name": "next"
      }
    ],
    "paths": {
      "@/*": ["./*"]
    }
  },
  "include": ["next-env.d.ts", "**/*.ts", "**/*.tsx", ".next/types/**/*.ts"],
  "exclude": ["node_modules"]
}
```

#### 步驟 5.3: 生成 package.json
生成或更新 `package.json`：

```json
{
  "name": "{project_id}",
  "version": "1.0.0",
  "private": true,
  "scripts": {
    "dev": "next dev",
    "build": "next build",
    "start": "next start",
    "lint": "next lint"
  },
  "dependencies": {
    "next": "^14.0.0",
    "react": "^18.2.0",
    "react-dom": "^18.2.0"
  },
  "devDependencies": {
    "@types/node": "^20.0.0",
    "@types/react": "^18.2.0",
    "@types/react-dom": "^18.2.0",
    "typescript": "^5.0.0",
    "tailwindcss": "^3.3.0",
    "postcss": "^8.4.0",
    "autoprefixer": "^10.4.0"
  }
}
```

### Phase 6: 驗證生成的網站結構

#### 步驟 6.1: 檢查路由完整性
- 確保所有 `pages` 列表中的頁面都有對應的路由文件
- 確保所有導航中的路由都有對應的頁面

#### 步驟 6.2: 檢查組件導入
- 確保所有頁面組件正確導入需要的組件
- 確保組件路徑正確（使用 `@/components` 別名）

#### 步驟 6.3: 檢查樣式導入
- 確保根 Layout 正確導入全局樣式
- 確保 Tailwind 配置正確

### Phase 7: 註冊 Artifacts

#### 步驟 7.1: 註冊網站 Artifacts
**必須**使用 `artifact_registry.register_artifact` 註冊產出的 artifacts：

1. **完整網站**：
   - **artifact_id**：`multi_page_website`
   - **artifact_type**：`nextjs_app`
   - **path**：`app/`

2. **根 Layout**：
   - **artifact_id**：`root_layout`
   - **artifact_type**：`component`
   - **path**：`app/layout.tsx`

3. **頁面路由**：
   - **artifact_id**：`page_routes`
   - **artifact_type**：`routes`
   - **path**：`app/`（所有頁面路由）

### Phase 8: 執行記錄保存

#### 步驟 8.1: 保存對話歷史
**必須**使用 `filesystem_write_file` 工具保存完整的對話歷史：

- 文件路徑: `artifacts/multi_page_assembly/{{execution_id}}/conversation_history.json`

#### 步驟 8.2: 保存執行摘要
**必須**使用 `filesystem_write_file` 工具保存執行摘要：

- 文件路徑: `artifacts/multi_page_assembly/{{execution_id}}/execution_summary.md`
- 內容:
  - 執行時間
  - 執行 ID
  - Playbook 名稱
  - 生成的頁面數量
  - 生成的路由列表
  - 配置文件名稱
  - 驗證結果

## 個人化

基於使用者的 Mindscape 個人檔案：
- **技術等級**：若為「進階」，包含更多優化和自訂選項
- **詳細程度**：若偏好「高」，提供更詳細的代碼註釋和說明
- **工作風格**：若偏好「結構化」，提供更清晰的目錄結構和組織

## 與長期意圖的整合

若使用者有相關的活躍意圖（例如「建立品牌網站」），明確引用：
> "由於您正在進行「建立品牌網站」，我已經將所有組件和頁面整合成完整的多頁面網站，可以直接部署使用..."

## 成功標準

- 根 Layout 已生成到 `app/layout.tsx`
- 所有頁面路由都已生成到對應的 `app/` 目錄結構
- 每個頁面都有完整的 SEO metadata
- 所有組件正確導入和使用
- 全局樣式正確導入
- Next.js 配置文件已生成
- TypeScript 配置文件已生成
- package.json 已生成或更新
- Artifacts 已正確註冊
- 網站結構完整，可以直接部署

## 注意事項

- **Project Context**：必須在 web_page 或 website project 的 context 中執行
- **依賴關係**：必須先執行 `site_spec_generation`、`style_system_gen` 和 `component_library_gen` playbook
- **Sandbox 路徑**：確保使用 Project Sandbox 路徑，而非 artifacts 路徑
- **Next.js App Router**：使用 Next.js 13+ 的 App Router 結構
- **路由映射**：確保路由映射符合 Next.js App Router 規範
- **組件路徑**：使用 `@/components` 別名導入組件

## 相關文檔

- **Schema 定義**：`capabilities/web_generation/schema/site_spec_schema.py`
- **網站規格生成**：`capabilities/web_generation/playbooks/zh-TW/site_spec_generation.md`
- **樣式系統生成**：`capabilities/web_generation/playbooks/zh-TW/style_system_gen.md`
- **組件庫生成**：`capabilities/web_generation/playbooks/zh-TW/component_library_gen.md`
- **完整網站生成流程**：`capabilities/web_generation/docs/complete-pipeline-workflow.md`

