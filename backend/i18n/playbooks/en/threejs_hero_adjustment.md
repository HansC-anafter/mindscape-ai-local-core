---
playbook_code: threejs_hero_adjustment
version: 1.0.0
name: Three.js Hero Section Adjustment
description: Help users analyze and convert Gemini-generated Three.js + GSAP code into Mindscape component architecture, including React/three-fiber structure conversion and integration task planning
tags:
  - webfx
  - threejs
  - gsap
  - animation
  - frontend
  - integration

kind: user_workflow
interaction_mode:
  - conversational
  - needs_review
visible_in:
  - workspace_tools_panel
  - workspace_playbook_menu

required_tools:
  - sandbox.write_file
  - sandbox.read_file
  - filesystem_write_file
  - filesystem_read_file

language_strategy: model_native
locale: en
supported_locales:
  - zh-TW
  - en
default_locale: en
auto_localize: true

entry_agent_type: reviewer
icon: 🎨
---

# Three.js Hero Section Adjustment - SOP

## Goal
Help users analyze Gemini-generated Three.js + GSAP code and convert it into Mindscape's React/three-fiber component architecture. Provide code structure analysis, conversion guidance, and integration task planning.

## Execution Steps

### Phase 1: Code Analysis
- Analyze the provided Three.js + GSAP code structure
- Identify key components: scenes, cameras, lights, geometries, materials, animations
- Map GSAP timelines and scroll triggers
- Document dependencies and external libraries
- Identify potential integration challenges

### Phase 2: Architecture Mapping
- Map Three.js scene structure to React component hierarchy
- Convert vanilla Three.js to React Three Fiber (R3F) patterns
- Identify reusable components vs. one-time setup code
- Plan state management strategy (React state vs. Three.js state)
- Map GSAP animations to React lifecycle hooks or effects

### Phase 3: Component Structure Design
- Design React component structure:
  - Main container component
  - Scene setup component
  - Object/mesh components
  - Animation controller components
- Define props and state interfaces
- Plan component communication patterns
- Identify shared utilities and helpers

### Phase 4: Integration Task Planning
- Create detailed task list for code conversion
- Prioritize tasks (critical path first)
- Identify dependencies between tasks
- Estimate complexity for each task
- Provide step-by-step conversion guide

### Phase 5: Code Conversion Guidance
- Provide React Three Fiber equivalent code examples
- Show how to convert Three.js objects to R3F components
- Demonstrate GSAP integration with React hooks
- Provide best practices for performance optimization
- Include error handling and edge cases

## Code Conversion Patterns

### Three.js to React Three Fiber
- `new THREE.Scene()` → `<Canvas><Scene /></Canvas>`
- `new THREE.PerspectiveCamera()` → `<PerspectiveCamera />`
- `new THREE.Mesh(geometry, material)` → `<mesh geometry={...} material={...} />`
- `scene.add(object)` → Component composition in JSX
- `renderer.render(scene, camera)` → Handled by R3F automatically

### GSAP Integration
- Timeline creation in `useEffect` hook
- Scroll triggers with `useScroll` hook or GSAP ScrollTrigger
- Animation cleanup in `useEffect` return function
- State updates via React state, not direct DOM manipulation

## Personalization

Based on user's Mindscape Profile:
- **Technical Level**: If "advanced", provide detailed implementation patterns and optimization techniques
- **Detail Level**: If "high", include comprehensive code examples and edge case handling
- **Work Style**: If "structured", provide clear task breakdown and step-by-step guides

## Integration with Long-term Intents

If the user has relevant Active Intents (e.g., "Build Interactive Landing Page"), explicitly reference it:
> "Since you're working on 'Build Interactive Landing Page', I recommend focusing on the hero section conversion first, as it's the primary visual element..."

## Success Criteria
- Code structure is fully analyzed and documented
- React component architecture is clearly defined
- Conversion task list is comprehensive and actionable
- User has clear guidance for integrating code into Mindscape
- Performance considerations are addressed

### Phase 6: File Generation and Saving

#### Step 6.1: Save Adjusted Component
**Must** use `sandbox.write_file` tool to save adjusted component (preferred) or `filesystem_write_file` (requires manual confirmation):

- File Path: `{ComponentName}_adjusted.tsx` (relative path, relative to sandbox root)
- Content: Adjusted React Three Fiber component code
- Format: TypeScript/TSX format

#### Step 6.2: Save Adjustment Notes
**Must** use `sandbox.write_file` tool to save adjustment notes (preferred) or `filesystem_write_file` (requires manual confirmation):

- File Path: `adjustment_notes.md` (relative path, relative to sandbox root)
- Content: Code structure analysis, conversion guidance, and integration task planning
- Format: Markdown format

## Notes
- This playbook assumes code is generated externally (e.g., from Gemini) and needs integration
- Focus on conversion patterns rather than generating new code from scratch
- Emphasize maintainability and React best practices
- Consider bundle size and performance implications

