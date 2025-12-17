---
playbook_code: threejs_hero_landing
version: 1.0.0
name: Three.js Hero Landing Page Generator
description: Generate interactive Three.js + GSAP hero sections for landing pages, including complete HTML+JS code and React/three-fiber conversion
tags:
  - webfx
  - threejs
  - gsap
  - landing
  - animation
  - frontend

kind: user_workflow
interaction_mode:
  - hybrid
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

entry_agent_type: webfx_coder
icon: 🎨
---

# Three.js Hero Landing Page Generator - SOP

## Goal
Generate complete, production-ready Three.js + GSAP hero sections for landing pages. Output standalone HTML+JS code first, then provide React/three-fiber conversion guidance for Mindscape integration.

## Execution Steps

### Phase 0: Check Project Context

#### Step 0.1: Check for Active web_page Project
- Check if `project_id` exists in execution context
- If yes, confirm project type is `web_page` or `website`
- If no, use existing flow (standalone generation to artifacts)

#### Step 0.2: Get Project Sandbox Path (if project exists)
- If project context exists, use `project_sandbox_manager.get_sandbox_path()` to get sandbox path
- Sandbox path structure: `sandboxes/{workspace_id}/{project_type}/{project_id}/`
- Ensure `hero/` directory exists

#### Step 0.3: Read Page Specification (if project exists)
- If project context exists, try to read `spec/page.md` (from `page_outline` playbook)
- If exists, use hero planning from page.md as design reference
- If not exists, use existing flow (standalone requirements gathering)

### Phase 1: Requirements Gathering

#### If Project Context Exists and `spec/page.md` Exists:
- **Read Page Specification**: Extract hero section planning from `spec/page.md`
- **Use Specification Design**: Use hero type, content, and style defined in page.md
- **Supplement Details**: If needed, ask for additional technical details (camera behavior, interaction style, etc.)

#### If No Project Context or `spec/page.md` Doesn't Exist:
- **Design References**: Ask for design inspiration, mood boards, or reference websites
- **Camera Behavior**: Understand desired camera movement (orbit, scroll-based, interactive)
- **Interaction Style**: Determine user interactions (mouse movement, scroll triggers, click events)
- **Target Platform**: Identify deployment target (web, mobile-responsive, specific browsers)
- **Performance Requirements**: Understand performance constraints and target devices
- **Content Elements**: Identify text, images, 3D models, or other assets to include

### Phase 2: Architecture Design
- **Scene Structure**: Design Three.js scene hierarchy
  - Camera setup (PerspectiveCamera with appropriate FOV and position)
  - Lighting strategy (ambient, directional, point lights)
  - Renderer configuration (antialiasing, pixel ratio, shadow maps)
- **GSAP Timeline Strategy**: Plan animation sequences
  - Entry animations (fade-in, slide-in, scale-up)
  - Scroll-triggered animations
  - Interactive hover/click animations
  - Exit or transition animations
- **Scroll Trigger Strategy**: Design scroll-based interactions
  - Parallax effects
  - Camera movement tied to scroll
  - Element reveal animations
  - Progress indicators
- **Performance Optimization**: Plan optimization techniques
  - Geometry instancing for repeated objects
  - Texture compression and LOD (Level of Detail)
  - Animation frame rate management
  - Memory cleanup strategies

### Phase 3: Code Generation

#### Step 3.1: Generate React Three Fiber Component (Primary)
**Priority**: Generate React Three Fiber component directly for site-brand integration

Generate component with:
- **TypeScript Interface**: Proper type definitions for props
- **React Three Fiber Structure**: Use R3F JSX syntax
- **GSAP Integration**: Use `useEffect` or `useLayoutEffect` for timelines
- **State Management**: React state for interactive elements
- **Performance Optimization**: useFrame, useMemo, proper cleanup
- **Error Handling**: Graceful degradation and error boundaries
- **Comments**: English comments following code standards

**Component Template**:
```typescript
import { useRef, useMemo, useEffect } from 'react'
import { useFrame, useThree } from '@react-three/fiber'
import * as THREE from 'three'
import { gsap } from 'gsap'

interface HeroComponentProps {
  // Define props based on requirements
}

export default function HeroComponent({
  // Props
}: HeroComponentProps) {
  const meshRef = useRef<THREE.Mesh>(null)
  const { gl, scene, camera } = useThree()

  useFrame((state) => {
    // Animation loop
    if (meshRef.current) {
      // Update mesh based on state
    }
  })

  useEffect(() => {
    // GSAP timeline setup
    const tl = gsap.timeline()
    // Animation configuration
    return () => {
      tl.kill()
    }
  }, [])

  return (
    <mesh ref={meshRef}>
      <boxGeometry args={[1, 1, 1]} />
      <meshStandardMaterial color="orange" />
    </mesh>
  )
}
```

#### Step 3.2: Standalone HTML+JS Output (Optional)
If user requests standalone version for testing:
- Generate complete, runnable HTML+JS code
- Include CDN links for Three.js and GSAP
- Provide testing instructions
- Note: This is optional, primary output is React Three Fiber component

### Phase 4: Integration Notes
- **Dependencies List**: Complete npm package list
  - `three`, `@react-three/fiber`, `@react-three/drei`
  - `gsap`, `@gsap/react`
  - Additional libraries (loaders, post-processing, etc.)
- **Installation Instructions**: Step-by-step setup guide
- **File Structure**: Recommended project organization
- **Integration Steps**: How to integrate into Mindscape component system
- **Troubleshooting**: Common issues and solutions
  - Performance problems
  - Animation glitches
  - Browser compatibility
  - Mobile responsiveness
- **Optimization Tips**: Further performance improvements
- **Testing Checklist**: What to verify before deployment

## Code Quality Standards

### Three.js Best Practices
- Use BufferGeometry for better performance
- Implement proper disposal of geometries, materials, textures
- Use Object3D groups for organization
- Optimize draw calls with instancing
- Implement frustum culling where applicable

### GSAP Best Practices
- Use `gsap.context()` for proper cleanup
- Leverage ScrollTrigger for scroll-based animations
- Use `will-change` CSS property for performance
- Implement animation pausing/resuming for performance
- Clean up event listeners and timelines

### React/Three-Fiber Best Practices
- Use `useMemo` for expensive calculations
- Implement proper cleanup in `useEffect`
- Use `useFrame` efficiently (avoid heavy computations)
- Leverage R3F's automatic render optimization
- Use `Suspense` for async asset loading

## Personalization

Based on user's Mindscape Profile:
- **Technical Level**: If "advanced", include advanced optimization techniques and custom shaders
- **Detail Level**: If "high", provide extensive code comments and architecture explanations
- **Work Style**: If "structured", break down into smaller, testable components

## Integration with Long-term Intents

If the user has relevant Active Intents (e.g., "Build Company Landing Page"), explicitly reference it:
> "Since you're working on 'Build Company Landing Page', I'll focus on creating a hero section that aligns with your brand identity and conversion goals..."

## Success Criteria
- React Three Fiber component has no TypeScript compilation errors
- All animations work smoothly (60fps target)
- Code is well-documented and maintainable (English comments)
- Component follows project code standards and style
- Component integrates correctly into site-brand
- Performance meets target requirements
- Responsive design works on target devices

### Phase 4: Site-Brand Integration

#### Step 4.1: Analyze Site-Brand Structure
- Review existing component structure in `site-brand/sites/mindscape-ai/src/components/Home/`
- Understand component patterns (DissolvePlane, IntentCards, SharedFogLayer)
- Identify integration points (which page to add component)
- Review TypeScript and React Three Fiber conventions used

#### Step 4.2: Generate React Three Fiber Component
**Priority**: Generate React Three Fiber component (not standalone HTML+JS)

**Component Structure**:
```typescript
import { useRef, useMemo } from 'react'
import { useFrame, useThree } from '@react-three/fiber'
import * as THREE from 'three'
import { gsap } from 'gsap'

interface ComponentNameProps {
  // Define props
}

export default function ComponentName({ ...props }: ComponentNameProps) {
  const meshRef = useRef<THREE.Mesh>(null)
  const { gl, scene, camera } = useThree()

  useFrame((state) => {
    // Animation loop
  })

  useEffect(() => {
    // GSAP timeline setup
    return () => {
      // Cleanup
    }
  }, [])

  return (
    <mesh ref={meshRef}>
      {/* Three.js objects as JSX */}
    </mesh>
  )
}
```

**Requirements**:
- Use TypeScript with proper type definitions
- Follow React Three Fiber patterns (JSX syntax)
- Integrate GSAP using `useEffect` or `useLayoutEffect`
- Implement proper cleanup logic
- Use English comments (following code standards)
- Match existing component style and structure

#### Step 4.3: Component Integration
- Determine target page (e.g., `src/pages/index.tsx`)
- Generate component import statement
- Update page to include new component within Canvas
- Ensure WebGLContextGuard is used if needed
- Handle component props and state management

### Phase 5: Site-Brand Deployment

#### Step 5.1: Prepare Component Files
- Generate component file: `site-brand/sites/mindscape-ai/src/components/Home/{ComponentName}.tsx`
- Ensure file follows project structure and naming conventions
- Validate TypeScript syntax and imports
- Check for any missing dependencies

#### Step 5.2: Deploy via File System + Git
**Method**: Use filesystem tools to write files, then commit via Git

**Steps**:
1. Write component file to correct path using filesystem tool
2. Update page file to import and use new component
3. Commit changes to Git repository (if permissions allow)
4. Or provide manual commit instructions

**File Paths**:
- Component: `site-brand/sites/mindscape-ai/src/components/Home/{ComponentName}.tsx`
- Page update: `site-brand/sites/mindscape-ai/src/pages/index.tsx` (or target page)

#### Step 5.3: Build and Deploy
- Trigger Next.js build (`next build`)
- Verify build succeeds without errors
- Deploy static files via Docker Compose
- Or provide deployment instructions

#### Step 5.4: Verify Deployment
- Check component file exists in correct location
- Verify page imports and renders component correctly
- Test Three.js scene loads without errors
- Verify GSAP animations work smoothly
- Check responsive design on mobile devices
- Validate performance (60fps target)

#### Step 5.5: Return Deployment Results
- Provide component file path
- Provide Git commit hash (if committed)
- Provide preview URL (if deployed)
- Provide deployment summary:
  - Component file location
  - Page integration status
  - Build status
  - Any warnings or errors
- Provide next steps:
  - Manual review needed
  - Testing recommendations
  - Optimization suggestions

## Natural Language Input Processing

When user provides natural language description, extract:
- **Component Name**: Suggested component name (e.g., "TechHero", "ParticleBackground")
- **Design Style**: Modern, retro, tech, minimalist, etc.
- **Animation Effects**: Scroll parallax, mouse interaction, auto-play, dissolve transitions, etc.
- **3D Elements**: Particles, geometries, 3D models, shader effects, etc.
- **Color Scheme**: Specific colors or color palette
- **Interaction Methods**: Mouse movement, scroll triggers, click events, etc.
- **Integration Target**: Which page to integrate (home page, specific route, etc.)

**Example Natural Language Inputs**:
- "I want a tech-style hero section with particle effects and parallax on mouse movement for the home page"
- "Create a retro-style landing page hero with scroll-triggered animations, add it to the index page"
- "Generate a minimalist hero section with 3D geometries and dissolve transitions, integrate into site-brand"

### Phase 6: Component Output and Saving

#### Step 6.1: Determine Output Path
**Based on whether Project Context exists**:

**If Project Context Exists**:
- **Output Path**: `hero/Hero.tsx` (in Project Sandbox)
- **Full Path**: `sandboxes/{workspace_id}/{project_type}/{project_id}/hero/Hero.tsx`
- **Register Artifact**: Use `artifact_registry.register_artifact` to register
  - `artifact_id`: `hero_component`
  - `artifact_type`: `react_component`
  - `path`: `hero/Hero.tsx`

**If No Project Context**:
- **Output Path**: `artifacts/threejs_hero_landing/{{execution_id}}/ParticleNetworkHero.tsx`
- Use existing flow (standalone generation)

#### Step 6.2: Save Generated Component Code
**Must** use `sandbox.write_file` tool to save generated React Three Fiber component (preferred) or `filesystem_write_file` (requires manual confirmation):

- **File Path**: Path determined in Step 6.1
- **Content**: Complete component code (including all imports, type definitions, component logic)
- **Ensure file can be used directly in project**

#### Step 6.3: Save Conversation History
**Must** use `sandbox.write_file` tool to save complete conversation history (preferred) or `filesystem_write_file` (requires manual confirmation):

- **File Path**: `artifacts/threejs_hero_landing/{{execution_id}}/conversation_history.json`
- **Content**: Complete conversation history (including all user and assistant messages)
- **Format**: JSON format with timestamps and role information

#### Step 6.4: Save Execution Summary
**Must** use `sandbox.write_file` tool to save execution summary (preferred) or `filesystem_write_file` (requires manual confirmation):

- **File Path**: `artifacts/threejs_hero_landing/{{execution_id}}/execution_summary.md`
- **Content**:
  - Execution time
  - Execution ID
  - Playbook name
  - Main input parameters (design requirements, interaction style, etc.)
  - Execution result summary
  - Generated component name and path
  - Integration notes and dependency list
  - Whether Project Context exists (if yes, record project_id)

#### Step 6.5: Save Usage Example (if generated)
If usage example was generated, save to:

- **File Path**: `artifacts/threejs_hero_landing/{{execution_id}}/usage-example.tsx`
- **Content**: Complete usage example code

## Notes
- Always generate standalone code first for easy testing
- Provide both vanilla Three.js and React versions
- Include comprehensive error handling
- Document all dependencies and versions
- Consider accessibility (keyboard navigation, screen readers)
- Test on multiple browsers and devices
- **Deployment**: After code generation, automatically offer deployment to site-brand
- **Confirmation**: Always confirm with user before deploying to production
- **Version Control**: Keep deployment history for rollback capability
- **Project Context**: If project context exists, output to Project Sandbox; otherwise use artifacts path

