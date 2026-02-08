---
playbook_code: multi_page_assembly
version: 1.0.0
capability_code: web_generation
name: Multi-Page Assembly
description: |
  Generate complete multi-page website from multi-page configuration in site_spec.yaml, including root Layout, multi-page routes (Next.js App Router), and SEO metadata.
  This is the fourth step in the complete website generation workflow, integrating all components and styles to generate a deployable complete website.
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
locale: en
supported_locales:
  - zh-TW
  - en
default_locale: en
auto_localize: true

entry_agent_type: coder
icon: 🏗️
---

# Multi-Page Assembly - SOP

## Goal

Generate complete multi-page website from multi-page configuration in `spec/site_spec.yaml`, including:
- Root Layout component (integrating Header and Footer)
- Multi-page routes (Next.js App Router structure)
- SEO metadata (metadata for each page)
- Page content components

Output to Project Sandbox `app/` directory (Next.js App Router structure).

**Workflow Description**:
- This is the **fourth step** in the complete website generation workflow: multi-page assembly
- Must execute after `site_spec_generation`, `style_system_gen`, and `component_library_gen` playbooks
- Generated website can be directly deployed to production

## Execution Steps

### Phase 0: Check Project Context

#### Step 0.1: Check for Active web_page or website Project
- Check if `project_id` exists in execution context
- If yes, confirm project type is `web_page` or `website`
- If no, prompt user to create project first

#### Step 0.2: Get Project Sandbox Path
- Use `project_sandbox_manager.get_sandbox_path()` to get sandbox path
- Sandbox path structure: `sandboxes/{workspace_id}/{project_type}/{project_id}/`
- Ensure `app/` directory exists (Next.js App Router structure)

#### Step 0.3: Check Dependency Files
Check if the following files exist:
- `spec/site_spec.yaml` (generated from `site_spec_generation`)
- `styles/variables.css` (generated from `style_system_gen`)
- `styles/global.css` (generated from `style_system_gen`)
- `tailwind.config.js` (generated from `style_system_gen`)
- `components/Header.tsx` (generated from `component_library_gen`)
- `components/Footer.tsx` (generated from `component_library_gen`)
- `components/index.ts` (generated from `component_library_gen`)

If any is missing, prompt user to execute corresponding playbook first.

### Phase 1: Parse Site Specification

#### Step 1.1: Read site_spec.yaml
**Must** use `filesystem_read_file` tool to read site specification document:

- **File Path**: `spec/site_spec.yaml` (in Project Sandbox)
- **Full Path**: `sandboxes/{workspace_id}/{project_type}/{project_id}/spec/site_spec.yaml`

#### Step 1.2: Extract Page Configuration
Extract from `site_spec.yaml`:
- `site`: Site basic information (title, description, base_url, metadata)
- `pages`: All page configuration list
- `navigation`: Navigation structure
- `theme`: Theme configuration (for style consistency validation)

#### Step 1.3: Validate Page Routes
- Ensure all page routes are unique
- Ensure navigation routes correspond to actual pages
- Validate route format conforms to Next.js App Router specifications

### Phase 2: Generate Root Layout

#### Step 2.1: Build Root Layout Structure
Generate `app/layout.tsx`, integrating Header and Footer:

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
    <html lang="en">
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

#### Step 2.2: Generate layout.tsx
**Must** use `filesystem_write_file` tool to save root Layout:

- **File Path**: `app/layout.tsx` (in Project Sandbox)
- **Full Path**: `sandboxes/{workspace_id}/{project_type}/{project_id}/app/layout.tsx`

### Phase 3: Generate Page Routes

#### Step 3.1: Handle Home Page Route
Generate `app/page.tsx` (corresponding to route `/`):

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
      {/* Hero Section - if hero component exists */}
      {/* Render corresponding Section components based on page.sections */}
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

#### Step 3.2: Handle Dynamic Routes
For each page, generate corresponding route file based on its `route`:

**Route Mapping Rules**:
- `/` → `app/page.tsx`
- `/about` → `app/about/page.tsx`
- `/chapters/chapter-1` → `app/chapters/chapter-1/page.tsx`
- `/chapters/chapter-1/section-1` → `app/chapters/chapter-1/section-1/page.tsx`

#### Step 3.3: Generate Page Component Template
Generate corresponding page component for each page:

```typescript
import type { Metadata } from 'next'
import { Features, CTA } from '@/components'

export const metadata: Metadata = {
  title: '{page.title}',
  description: '{page.metadata.seo_description || site.description}',
  // Other SEO metadata
}

export default function {PageName}Page() {
  return (
    <div className="page-container">
      {/* Render corresponding Section components based on page.sections */}
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
      {/* Other sections */}
    </div>
  )
}
```

#### Step 3.4: Handle Page Content Source
If page has `source` configuration (e.g., Markdown file from Obsidian):
- Read source file content
- Convert to format usable by React components
- Integrate into page component

#### Step 3.5: Generate All Page Routes
**Must** use `filesystem_write_file` tool to generate route file for each page:

- Iterate through all pages in `pages` list
- Generate corresponding route file for each page
- Ensure directory structure is correct (e.g., `app/chapters/chapter-1/` needs to create `chapters/chapter-1/` directory first)

### Phase 4: Generate SEO Metadata

#### Step 4.1: Extract SEO Information
Extract from each page's configuration:
- `page.title`: Page title
- `page.metadata.seo_title`: SEO title (if exists)
- `page.metadata.seo_description`: SEO description (if exists)
- `page.metadata.keywords`: Keywords (if exists)
- `site.metadata`: Site-level metadata

#### Step 4.2: Generate Metadata Configuration
Generate complete Metadata configuration for each page:

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

#### Step 4.3: Generate sitemap.xml (Optional)
**Optional** generate `app/sitemap.ts` or `public/sitemap.xml`:

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
    // Other pages...
  ]
}
```

### Phase 5: Generate Configuration Files

#### Step 5.1: Generate next.config.js
Generate Next.js configuration file:

```javascript
/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  swcMinify: true,
  // Other configurations...
}

module.exports = nextConfig
```

#### Step 5.2: Generate tsconfig.json
Generate TypeScript configuration file:

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

#### Step 5.3: Generate package.json
Generate or update `package.json`:

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

### Phase 6: Validate Generated Website Structure

#### Step 6.1: Check Route Completeness
- Ensure all pages in `pages` list have corresponding route files
- Ensure all navigation routes have corresponding pages

#### Step 6.2: Check Component Imports
- Ensure all page components correctly import required components
- Ensure component paths are correct (using `@/components` alias)

#### Step 6.3: Check Style Imports
- Ensure root Layout correctly imports global styles
- Ensure Tailwind configuration is correct

### Phase 7: Register Artifacts

#### Step 7.1: Register Website Artifacts
**Must** use `artifact_registry.register_artifact` to register output artifacts:

1. **Complete Website**:
   - **artifact_id**: `multi_page_website`
   - **artifact_type**: `nextjs_app`
   - **path**: `app/`

2. **Root Layout**:
   - **artifact_id**: `root_layout`
   - **artifact_type**: `component`
   - **path**: `app/layout.tsx`

3. **Page Routes**:
   - **artifact_id**: `page_routes`
   - **artifact_type**: `routes`
   - **path**: `app/` (all page routes)

### Phase 8: Execution Record Saving

#### Step 8.1: Save Conversation History
**Must** use `filesystem_write_file` tool to save complete conversation history:

- File path: `artifacts/multi_page_assembly/{{execution_id}}/conversation_history.json`

#### Step 8.2: Save Execution Summary
**Must** use `filesystem_write_file` tool to save execution summary:

- File path: `artifacts/multi_page_assembly/{{execution_id}}/execution_summary.md`
- Content:
  - Execution time
  - Execution ID
  - Playbook name
  - Number of pages generated
  - List of routes generated
  - Configuration file names
  - Validation results

## Personalization

Based on user's Mindscape profile:
- **Technical Level**: If "advanced", include more optimizations and customization options
- **Detail Level**: If preference is "high", provide more detailed code comments and explanations
- **Work Style**: If preference is "structured", provide clearer directory structure and organization

## Integration with Long-term Intentions

If user has related active intentions (e.g., "Build brand website"), explicitly reference:
> "Since you are working on 'Build brand website', I have integrated all components and pages into a complete multi-page website that can be directly deployed..."

## Success Criteria

- Root Layout generated to `app/layout.tsx`
- All page routes generated to corresponding `app/` directory structure
- Each page has complete SEO metadata
- All components correctly imported and used
- Global styles correctly imported
- Next.js configuration file generated
- TypeScript configuration file generated
- package.json generated or updated
- Artifacts correctly registered
- Website structure complete, ready for deployment

## Notes

- **Project Context**: Must execute in web_page or website project context
- **Dependencies**: Must execute `site_spec_generation`, `style_system_gen`, and `component_library_gen` playbooks first
- **Sandbox Path**: Ensure using Project Sandbox path, not artifacts path
- **Next.js App Router**: Use Next.js 13+ App Router structure
- **Route Mapping**: Ensure route mapping conforms to Next.js App Router specifications
- **Component Paths**: Use `@/components` alias to import components

## Related Documentation

- **Schema Definition**: `capabilities/web_generation/schema/site_spec_schema.py`
- **Site Specification Generation**: `capabilities/web_generation/playbooks/en/site_spec_generation.md`
- **Style System Generation**: `capabilities/web_generation/playbooks/en/style_system_gen.md`
- **Component Library Generation**: `capabilities/web_generation/playbooks/en/component_library_gen.md`
- **Complete Website Generation Workflow**: `capabilities/web_generation/docs/complete-pipeline-workflow.md`

