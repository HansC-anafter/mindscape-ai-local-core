---
playbook_code: component_library_gen
version: 1.0.0
capability_code: web_generation
name: Component Library Generation
description: |
  Generate complete component library from components configuration in site_spec.yaml, including Header, Footer, Section components, and basic UI components.
  This is the third step in the complete website generation workflow, providing reusable component foundation for subsequent multi-page assembly.
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

language_strategy: model_native
locale: en
supported_locales:
  - zh-TW
  - en
default_locale: en
auto_localize: true

entry_agent_type: coder
icon: 🧩
---

# Component Library Generation - SOP

## Goal

Generate complete component library from `components` configuration in `spec/site_spec.yaml`, including:
- Header component (`components/Header.tsx`)
- Footer component (`components/Footer.tsx`)
- Section components (Features, CTA, About, etc.)
- Basic UI components (Button, Card, Input, etc.)

Output to Project Sandbox `components/` directory.

**Workflow Description**:
- This is the **third step** in the complete website generation workflow: generate component library
- Must execute after `site_spec_generation` and `style_system_gen` playbooks
- Generated components will be used by subsequent multi-page assembly

## Execution Steps

### Phase 0: Check Project Context

#### Step 0.1: Check for Active web_page or website Project
- Check if `project_id` exists in execution context
- If yes, confirm project type is `web_page` or `website`
- If no, prompt user to create project first

#### Step 0.2: Get Project Sandbox Path
- Use `project_sandbox_manager.get_sandbox_path()` to get sandbox path
- Sandbox path structure: `sandboxes/{workspace_id}/{project_type}/{project_id}/`
- Ensure `components/` directory exists

#### Step 0.3: Check Dependency Files
Check if the following files exist:
- `spec/site_spec.yaml` (generated from `site_spec_generation`)
- `styles/variables.css` (generated from `style_system_gen`)
- `styles/global.css` (generated from `style_system_gen`)
- `tailwind.config.js` (generated from `style_system_gen`)

If any is missing, prompt user to execute corresponding playbook first.

### Phase 1: Parse Component Requirements

#### Step 1.1: Read site_spec.yaml
**Must** use `filesystem_read_file` tool to read site specification document:

- **File Path**: `spec/site_spec.yaml` (in Project Sandbox)
- **Full Path**: `sandboxes/{workspace_id}/{project_type}/{project_id}/spec/site_spec.yaml`

#### Step 1.2: Extract Components Configuration
Extract `components` list from `site_spec.yaml`:
- Each component's `component_id`, `component_type`, `required`, `config`
- Categorize by `component_type`:
  - `header`: Header component
  - `footer`: Footer component
  - `section`: Section components (Features, CTA, About, etc.)
  - `ui`: Basic UI components (Button, Card, Input, etc.)

#### Step 1.3: Extract Navigation Configuration
Extract `navigation` configuration from `site_spec.yaml`:
- `navigation.top`: Top navigation items
- `navigation.sidebar`: Sidebar navigation items
- `navigation.footer`: Footer navigation items

#### Step 1.4: Extract Theme Configuration
Extract `theme` configuration from `site_spec.yaml`:
- Used to ensure components use consistent styles

### Phase 2: Generate Header Component

#### Step 2.1: Check Header Requirements
- Check if there is a component with `component_type: "header"` in `components` list
- If not but navigation exists, automatically create Header component requirement
- Read Header component's `config` configuration

#### Step 2.2: Build Header Component Structure
Generate Header component based on configuration:

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

#### Step 2.3: Generate Header.tsx
**Must** use `filesystem_write_file` tool to save Header component:

- **File Path**: `components/Header.tsx` (in Project Sandbox)
- **Full Path**: `sandboxes/{workspace_id}/{project_type}/{project_id}/components/Header.tsx`

### Phase 3: Generate Footer Component

#### Step 3.1: Check Footer Requirements
- Check if there is a component with `component_type: "footer"` in `components` list
- If not, automatically create Footer component based on common requirements
- Read Footer component's `config` configuration

#### Step 3.2: Build Footer Component Structure
Generate Footer component based on configuration:

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

#### Step 3.3: Generate Footer.tsx
**Must** use `filesystem_write_file` tool to save Footer component:

- **File Path**: `components/Footer.tsx`

### Phase 4: Generate Section Components

#### Step 4.1: Identify Required Section Components
Identify required Section components based on `components` list and `pages` configuration:
- Features Section (if pages have features)
- CTA Section (if pages have call-to-action)
- About Section (if pages have about)
- Other custom Sections

#### Step 4.2: Generate Features Section
If needed, generate Features Section component:

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

#### Step 4.3: Generate CTA Section
Generate CTA (Call-to-Action) Section component:

```typescript
import Link from 'next/link'

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

#### Step 4.4: Generate Other Section Components
Generate other Section components as needed (About, Testimonials, Pricing, etc.).

#### Step 4.5: Save All Section Components
**Must** use `filesystem_write_file` tool to save each Section component:

- `components/sections/Features.tsx`
- `components/sections/CTA.tsx`
- `components/sections/About.tsx`
- Other sections...

### Phase 5: Generate Basic UI Components

#### Step 5.1: Generate Button Component
Generate reusable Button component:

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

#### Step 5.2: Generate Card Component
Generate reusable Card component:

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

#### Step 5.3: Generate Input Component
Generate reusable Input component:

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

#### Step 5.4: Save All UI Components
**Must** use `filesystem_write_file` tool to save each UI component:

- `components/ui/Button.tsx`
- `components/ui/Card.tsx`
- `components/ui/Input.tsx`
- Other UI components...

### Phase 6: Create Component Index File

#### Step 6.1: Generate components/index.ts
Generate component export index file:

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

#### Step 6.2: Save index.ts
**Must** use `filesystem_write_file` tool to save index file:

- **File Path**: `components/index.ts`

### Phase 7: Validate Component Completeness

#### Step 7.1: Check Required Components
- Check if all components with `required: true` are generated
- Check if component files exist and are readable

#### Step 7.2: Validate Component Dependencies
- Check if styles used by components are in `styles/` directory
- Check if component import paths are correct
- Ensure components use unified style system

### Phase 8: Register Artifacts

#### Step 8.1: Register Component Library Artifacts
**Must** use `artifact_registry.register_artifact` to register output artifacts:

1. **Component Library**:
   - **artifact_id**: `component_library`
   - **artifact_type**: `components`
   - **path**: `components/`

2. **Header Component**:
   - **artifact_id**: `header_component`
   - **artifact_type**: `component`
   - **path**: `components/Header.tsx`

3. **Footer Component**:
   - **artifact_id**: `footer_component`
   - **artifact_type**: `component`
   - **path**: `components/Footer.tsx`

### Phase 9: Execution Record Saving

#### Step 9.1: Save Conversation History
**Must** use `filesystem_write_file` tool to save complete conversation history:

- File path: `artifacts/component_library_gen/{{execution_id}}/conversation_history.json`

#### Step 9.2: Save Execution Summary
**Must** use `filesystem_write_file` tool to save execution summary:

- File path: `artifacts/component_library_gen/{{execution_id}}/execution_summary.md`
- Content:
  - Execution time
  - Execution ID
  - Playbook name
  - Generated component list
  - Component configuration summary
  - Validation results

## Personalization

Based on user's Mindscape profile:
- **Technical Level**: If "advanced", include more customization options and advanced component features
- **Detail Level**: If preference is "high", provide more detailed component comments and documentation
- **Work Style**: If preference is "structured", provide clearer component organization structure

## Integration with Long-term Intentions

If user has related active intentions (e.g., "Build brand website"), explicitly reference:
> "Since you are working on 'Build brand website', I will generate a consistent component library based on your brand identity..."

## Success Criteria

- Header component generated to `components/Header.tsx`
- Footer component generated to `components/Footer.tsx`
- All required Section components generated
- Basic UI components (Button, Card, Input) generated
- Component index file generated to `components/index.ts`
- All components use unified style system
- All required components (`required: true`) generated
- Artifacts correctly registered
- Components can seamlessly integrate with subsequent multi-page assembly

## Notes

- **Project Context**: Must execute in web_page or website project context
- **Dependencies**: Must execute `site_spec_generation` and `style_system_gen` playbooks first
- **Sandbox Path**: Ensure using Project Sandbox path, not artifacts path
- **Style Consistency**: All components must use unified style system (CSS variables, Tailwind classes)
- **Component Reusability**: Component design should consider reusability, supporting multi-page usage

## Related Documentation

- **Schema Definition**: `capabilities/web_generation/schema/site_spec_schema.py`
- **Site Specification Generation**: `capabilities/web_generation/playbooks/en/site_spec_generation.md`
- **Style System Generation**: `capabilities/web_generation/playbooks/en/style_system_gen.md`
- **Complete Website Generation Workflow**: `capabilities/web_generation/docs/complete-pipeline-workflow.md`

