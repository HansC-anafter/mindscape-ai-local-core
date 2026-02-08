---
playbook_code: site_deploy_gcp_vm
version: 1.0.0
capability_code: web_generation
name: Deploy Site to GCP VM
description: Deploy generated site components to GCP VM production environment through Git workflow
tags:
  - deployment
  - gcp
  - vm
  - git
  - production

kind: user_workflow
interaction_mode:
  - conversational
  - needs_review
visible_in:
  - workspace_tools_panel
  - workspace_playbook_menu

required_tools:
  - filesystem_read_file
  - filesystem_write_file

language_strategy: model_native
locale: en
supported_locales:
  - zh-TW
  - en
default_locale: en
auto_localize: true

entry_agent_type: coder
icon: 🚀
---

# Deploy Site to GCP VM - SOP

## Goal
Deploy generated complete site components to GCP VM production environment through Git workflow. **Strictly follow developer guidelines: Never bypass Git to directly operate on VM.**

## Execution Steps

### Phase 0: Check Project Context

#### Step 0.1: Check for Active web_page Project
- Check if `project_id` exists in execution context
- If yes, confirm project type is `web_page` or `website`
- If no, prompt user to create project first

#### Step 0.2: Get Project Sandbox Path
- Use `project_sandbox_manager.get_sandbox_path()` to get sandbox path
- Sandbox path structure: `sandboxes/{workspace_id}/{project_type}/{project_id}/`
- Confirm generated components exist

#### Step 0.3: Check Required Artifacts
Check if the following artifacts exist:
- `complete_page` - Complete page component (`pages/index.tsx`)
- `hero_component` - Hero component (`hero/Hero.tsx`)
- `sections` - Section components (`sections/` directory)

If any is missing, prompt user to run corresponding playbook first.

### Phase 1: Prepare Deployment Files

#### Step 1.1: Read Generated Components
**Must** use `filesystem_read_file` tool to read:

- **Complete page component**: `pages/index.tsx`
- **Hero component**: `hero/Hero.tsx`
- **All section components**: `sections/*.tsx`
- **Style files** (if any): `styles/*.css` or `styles/*.ts`
- **Dependency list**: `package.json` or `dependencies.md`

#### Step 1.2: Validate Component Completeness
- Check all components for TypeScript errors
- Check all import paths are correct
- Check dependencies are complete
- Verify component structure matches target project standards

#### Step 1.3: Prepare Git Commit Content
- Determine target Git repository path (site-brand or other project)
- Plan file structure and placement
- Prepare commit message (following Conventional Commits format)

### Phase 2: Git Workflow

#### Step 2.1: Check Git Repository Status
- Confirm target Git repository path exists
- Check current branch (should be on feature branch, not main/master)
- Confirm working directory is clean (no uncommitted changes)

#### Step 2.2: Create Feature Branch (if needed)
If not currently on feature branch:
- Create new feature branch: `feature/deploy-{project_id}-{timestamp}`
- Branch naming convention: `feature/deploy-{description}`

#### Step 2.3: Copy Files to Target Location
**Must** use `filesystem_write_file` tool to write components to target location:

- **Component files**: Write to target project's component directory
  - Example: `site-brand/sites/{site-name}/src/components/Home/Hero.tsx`
- **Page files**: Update or create page files
  - Example: `site-brand/sites/{site-name}/src/pages/index.tsx`
- **Style files**: Write to style directory (if any)
- **Config files**: Update `package.json` and other configs (if needed)

#### Step 2.4: Generate Git Commit Commands
**Must** generate Git commit commands, but **do not execute directly** (wait for user confirmation):

```bash
# Check changes
git status

# Add files (specify files explicitly, never use git add .)
git add [specific file names]

# Commit changes (following Conventional Commits format)
git commit -m "feat(site): deploy {project_name} to production

- Add hero component: Hero.tsx
- Add page sections: About.tsx, Features.tsx, etc.
- Update main page: index.tsx
- Generated via playbook: site_deploy_gcp_vm"

# Push to remote
git push origin feature/deploy-{project_id}-{timestamp}
```

**Important**:
- Must specify file names explicitly, never use `git add .`
- Commit message must follow Conventional Commits format
- Must commit on feature branch, never directly on main/master

### Phase 3: Deployment Preparation

#### Step 3.1: Generate Deployment Checklist
Generate pre-deployment checklist:

- [ ] All component files correctly written
- [ ] TypeScript compilation has no errors
- [ ] All dependencies installed
- [ ] Git changes committed to feature branch
- [ ] Pull Request created (if needed)
- [ ] Code review passed (if needed)

#### Step 3.2: Generate Deployment Commands
Generate deployment commands for GCP VM (**do not execute directly**, wait for user confirmation):

```bash
# Method 1: Deploy via Git (recommended)
# Execute on GCP VM
cd /path/to/site-brand
git pull origin main  # or develop, depending on deployment flow
npm install  # if new dependencies
npm run build  # build project
pm2 restart site-brand  # or use other process manager

# Method 2: Deploy via CI/CD (if configured)
# Automatically triggered after push
```

#### Step 3.3: Generate Deployment Verification Steps
Generate post-deployment verification steps:

- Check if website is running normally
- Check if Three.js scene loads correctly
- Check if GSAP animations run smoothly
- Check responsive design on mobile devices
- Check performance (target 60fps)
- Check console for errors

### Phase 4: Document Generation and Saving

#### Step 4.1: Save Deployment Plan
**Must** use `filesystem_write_file` tool to save deployment plan:

- **File path**: `artifacts/site_deploy_gcp_vm/{{execution_id}}/deployment_plan.md`
- **Content**:
  - Deployment target (GCP VM information)
  - Git repository path
  - File placement locations
  - Git commit commands
  - Deployment commands
  - Verification steps
- **Format**: Markdown format

#### Step 4.2: Save Git Changes Summary
**Must** use `filesystem_write_file` tool to save Git changes summary:

- **File path**: `artifacts/site_deploy_gcp_vm/{{execution_id}}/git_changes.md`
- **Content**:
  - List of changed files
  - Change summary for each file
  - Git commit message
  - Branch name

#### Step 4.3: Save Conversation History
**Must** use `filesystem_write_file` tool to save complete conversation history:

- **File path**: `artifacts/site_deploy_gcp_vm/{{execution_id}}/conversation_history.json`
- **Content**: Complete conversation history (all user and assistant messages)
- **Format**: JSON format with timestamps and role information

#### Step 4.4: Save Execution Summary
**Must** use `filesystem_write_file` tool to save execution summary:

- **File path**: `artifacts/site_deploy_gcp_vm/{{execution_id}}/execution_summary.md`
- **Content**:
  - Execution time
  - Execution ID
  - Playbook name
  - Deployment target
  - List of generated files
  - Git commit commands
  - Deployment commands
  - Execution result summary

### Phase 5: User Confirmation and Next Steps

#### Step 5.1: Provide Deployment Summary
Provide complete deployment summary to user:

- Generated file locations
- Git commit commands (wait for user confirmation before execution)
- Deployment commands (wait for user confirmation before execution)
- Deployment checklist
- Verification steps

#### Step 5.2: Wait for User Confirmation
**Important**: All Git operations and deployment operations must wait for user confirmation before execution.

- Provide clear commands and instructions
- Wait for user confirmation before proceeding
- If user needs modifications, provide modification guidance

#### Step 5.3: Provide Follow-up Support
Provide follow-up support information:

- How to rollback deployment (if needed)
- How to view deployment logs
- How to monitor site status
- How to perform subsequent updates

## Personalization

Based on user's Mindscape Profile:
- **Technical Level**: If "advanced", provide more detailed deployment options and custom configurations
- **Detail Level**: If prefers "high", provide more detailed deployment steps and verification checklist
- **Work Style**: If prefers "structured", provide clearer deployment flow and checkpoints

## Integration with Long-term Intents

If user has related Active Intent (e.g., "Build company landing page"), explicitly reference it:
> "Since you're working towards 'Build company landing page', I've prepared to deploy the generated site to production environment..."

## Success Criteria

- All component files correctly written to target location
- Git commit commands generated (following standards)
- Deployment commands generated
- Deployment plan document saved
- User confirmed deployment steps
- All changes go through Git workflow (no direct VM operations)

## Notes

### ⚠️ Absolute Deadlines

1. **💀 Never bypass Git to directly operate on VM**
   - All changes must go through Git commits
   - All deployments must go through Git workflow
   - Never directly SSH to VM to modify files

2. **💀 Never use `git add .`**
   - Must specify file names explicitly
   - Must clearly know content of each change

3. **💀 Never commit directly on main/master branch**
   - Must commit on feature branch
   - Must merge through Pull Request (if needed)

4. **💀 Commit messages must follow standards**
   - Use Conventional Commits format
   - Provide clear change descriptions

### Other Notes

- **Dependencies**: Must run `page_outline`, `threejs_hero_landing`, `page_sections`, `page_assembly` playbooks first
- **Project Context**: Must execute in web_page project context
- **Git Repository**: Must confirm target Git repository path is correct
- **Deployment Confirmation**: All deployment operations must wait for user confirmation
- **Version Control**: Keep deployment history for rollback capability
- **Execution Records**: Must save complete conversation history and execution summary

## Related Documentation

- **Developer Guidelines**: `docs-internal/DEVELOPER_GUIDE_MINDSCAPE_AI.md`
- **Git Workflow**: Git workflow section in developer documentation
- **Deployment Architecture**: `docs-internal/core-architecture/cloud-local-deployment-guide.md`

