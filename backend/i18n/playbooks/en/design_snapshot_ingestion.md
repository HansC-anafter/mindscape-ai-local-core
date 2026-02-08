---
playbook_code: design_snapshot_ingestion
version: 1.0.0
capability_code: web_generation
name: Design Snapshot Ingestion
description: |
  Import outputs from Stitch or other design tools to create versioned design snapshot artifacts.
  Serves as the "upstream input baseline" for the web-generation workflow, providing visual design references.
tags:
  - web
  - design
  - snapshot
  - ingestion
  - governance

kind: user_workflow
interaction_mode:
  - conversational
  - needs_review
visible_in:
  - workspace_tools_panel
  - workspace_playbook_menu

execution_profile: short_flow  # Short-flow playbook, no LangGraph needed

required_tools:
  # Basic Artifact operations
  - artifact.create
  - artifact.list
  - artifact.read

  # Filesystem operations
  - filesystem_write_file
  - filesystem_read_file
  - filesystem_list
  - filesystem_mkdir

language_strategy: model_native
locale: en
supported_locales:
  - zh-TW
  - en
default_locale: en
auto_localize: true

entry_agent_type: planner
icon: 🎨
---

# Design Snapshot Ingestion - SOP

## Goal

Import outputs from external design tools (e.g., Google Labs Stitch, Figma) to create versioned Design Snapshot Artifacts. These snapshots serve as "upstream input baselines" for the web-generation workflow, reducing prompt drift and accelerating design convergence.

**Workflow Overview**:
- This is **Phase 0** of the complete website generation workflow: design exploration and ingestion
- Supports multiple sources: Stitch HTML/CSS, Figma (future), manual upload
- Creates versioned, traceable design snapshot artifacts

---

## Execution Steps

### Phase 0: Check Project Context

#### Step 0.1: Check for active web_page or website project
- Check if execution context has `project_id`
- If yes, confirm project type is `web_page` or `website`
- If no, prompt user to create project first (but playbook can still run, creating workspace-level snapshot)

#### Step 0.2: Get Project Sandbox path (if available)
- Use `project_sandbox_manager.get_sandbox_path()` to get sandbox path
- Sandbox path structure: `sandboxes/{workspace_id}/{project_type}/{project_id}/`
- Ensure `design_snapshots/` directory exists (for storing original files)

#### Step 0.3: Check for parent snapshot
- Use `artifact.list` to query `kind: design_snapshot`
- If multiple snapshots exist, ask user if they want to create new version based on existing snapshot
- Record `parent_snapshot_id` (if selected)

---

### Phase 1: Import Source Selection

#### Step 1.1: Select import source

Ask user to choose import source:

**Option A: Upload HTML/CSS files**
- Use tool to upload files (via frontend or tool support)
- Read file contents

**Option B: Paste HTML/CSS content**
- Ask user to paste HTML and CSS content
- Store as separate strings

**Option C: Provide file path** (if files already exist in sandbox)
- Read files from sandbox

**Option D: Figma URL** (future expansion)
- Currently show "Not yet supported, please export as HTML/CSS first"

**Decision Card: Import Source**

```decision_card
card_id: dc_import_source
type: selection
title: "Select Import Source"
question: "Please choose the source of the design snapshot"
options:
  - "Upload HTML/CSS files"
  - "Paste HTML/CSS content"
  - "Provide file path"
description: "Currently supports HTML/CSS import, Figma integration coming in future versions"
```

---

### Phase 2: Security Check and Sanitization ⚠️ Security Boundary

#### Step 2.1: HTML Security Processing

**⚠️ Core Security Principle: No Execution, No Injection**

1. **Remove dangerous tags**:
   - Remove all `<script>` tags and their content
   - Remove `<iframe>`, `<object>`, `<embed>`
   - Remove `<form>`, `<input>`, `<button>` (interactive form elements)

2. **Remove dangerous attributes**:
   - Remove all inline event handlers: `onclick`, `onerror`, `onload`, `onmouseover`, etc.
   - Remove `javascript:` URLs

3. **Calculate source_hash** (for reproducibility):
   ```python
   import hashlib
   source_hash = hashlib.sha256(html_content.encode()).hexdigest()
   ```

4. **Storage Strategy**:
   - **Original file** (after security processing): Save to `design_snapshots/{version}/original.html`
   - **Metadata**: Store in artifact metadata field (does not include executable code)

#### Step 2.2: CSS Security Processing

1. **Remove dangerous rules**:
   - Remove `@import` (may load external resources)
   - Remove external `url()` (but keep data: URLs)
   - Remove `expression()` (IE JavaScript execution)
   - Remove `javascript:` URLs

2. **Storage**:
   - Security-processed CSS saved to `design_snapshots/{version}/styles.css`

---

### Phase 3: Design Snapshot Parsing

#### Step 3.1: HTML Structure Parsing

Use HTML parser (e.g., BeautifulSoup) to extract:

1. **Navigation structure**:
   - `<nav>` tags and their children
   - Navigation items (label, href/route)
   - Navigation hierarchy (top/sidebar/footer)

2. **Page states**:
   - CSS classes containing state markers like `hover`, `active`, `disabled`
   - State changes of interactive elements

3. **Component structure**:
   - Main sections (hero, about, features, etc.)
   - Component hierarchy

**Record parsing quality**:
- If navigation structure is clear → `extraction_quality: "high"`
- If some information cannot be determined → `extraction_quality: "medium"`, record `missing_fields`
- If much is missing → `extraction_quality: "low"`

#### Step 3.2: CSS Style Extraction

Extract style information:

1. **Color Palette**:
   - CSS variables (`--color-primary`, etc.)
   - Hardcoded color values (`#ff0000`, `rgb()`, etc.)
   - Identify primary, secondary, accent colors

2. **Typography**:
   - `font-family` definitions
   - `font-size` scale (h1, h2, h3, body, etc.)
   - `line-height` settings
   - `font-weight` variations

3. **Spacing**:
   - `margin` / `padding` values
   - Identify spacing scale (e.g., 4, 8, 12, 16, 24, 32...)

4. **Other design tokens**:
   - `border-radius`
   - `box-shadow`
   - `breakpoints` (if using media queries)

**Record missing fields**:
- If cannot identify breakpoints → `missing_fields: ["breakpoints"]`
- If cannot identify state tokens → `missing_fields: ["state_tokens"]`

#### Step 3.3: Design Assumptions Extraction

Based on parsing results, record design assumptions:

1. **Navigation assumptions**:
   - Assumptions about navigation structure (if parsing incomplete)
   - Assumptions about navigation behavior

2. **State assumptions**:
   - Assumptions about interactive states (hover, active, etc.)

3. **Responsive assumptions**:
   - If cannot identify breakpoints, record assumptions (e.g., "assumes mobile-first")

---

### Phase 4: Version Chain and Metadata Configuration

#### Step 4.1: Version Information

Ask user or auto-generate:

- **Version number**: If first snapshot, use `1.0.0`; if has parent, suggest bump minor
- **Variant ID**: If multiple UI variants, record `variant_id` (e.g., `variant_a`, `variant_b`)
- **Source tool**: `source_tool: "stitch" | "figma" | "manual"`

#### Step 4.2: Version Chain Configuration (Optional)

Ask user:

**Decision Card: Version Chain Configuration**

```decision_card
card_id: dc_version_chain
type: optional
title: "Version Chain Configuration"
question: "Does this snapshot have a parent version or belong to a branch?"
options:
  - parent_snapshot_id: "Select parent version (optional)"
  - branch: "Branch name (e.g., 'main', 'experiment-a')"
  - lineage_key: "Lineage key (e.g., 'exploration_001')"
allow_custom: true
```

#### Step 4.3: Baseline Binding (Optional)

Ask user if they want to set as baseline immediately:

**Decision Card: Baseline Binding**

```decision_card
card_id: dc_baseline_binding
type: optional
title: "Baseline Binding"
question: "Do you want to set this snapshot as baseline?"
options:
  - baseline_for: "Project ID (optional, None = workspace level)"
  - lock_mode: "Lock mode ('locked' or 'advisory')"
```

**Notes**:
- If not set at this stage, can be set later in UI
- `lock_mode: "locked"` = hard constraint (subsequent playbooks must follow)
- `lock_mode: "advisory"` = reference suggestion (subsequent playbooks can reference but not required)

---

### Phase 5: Create Design Snapshot Artifact

#### Step 5.1: Prepare Metadata

Use `DesignSnapshotMetadata` schema to prepare metadata:

```python
from capabilities.web_generation.schema import DesignSnapshotMetadata
from datetime import datetime

metadata = DesignSnapshotMetadata(
    # Basic identification
    kind="design_snapshot",
    source_tool="stitch",  # From user selection
    version="1.0.0",  # From version info
    snapshot_date=datetime.utcnow(),

    # Baseline locking mechanism (if user chooses to set)
    variant_id="variant_a",  # If has variants
    active_variant="variant_a",  # Currently active variant
    baseline_for="project_123",  # If set as baseline
    lock_mode="advisory",  # If set as baseline

    # Reproducibility
    source_hash=source_hash,  # Calculated in Phase 2
    extractor_version="1.0.0",  # Parser version
    transformer_version=None,  # Not yet transformed

    # Version chain
    parent_snapshot_id="<parent_id>",  # If parent version selected
    branch="main",  # If branch specified
    lineage_key="exploration_001",  # If specified

    # UI structure (from Phase 3 parsing results)
    navigation_structure={
        "top": [...],
        "sidebar": [...],
        "footer": [...]
    },
    page_states=["default", "hover", "active"],

    # Style extraction (from Phase 3 parsing results)
    extracted_colors={
        "primary": "#ff0000",
        "secondary": "#00ff00",
        ...
    },
    extracted_typography={
        "heading_font": "Arial",
        "body_font": "Arial",
        "type_scale": {...}
    },
    extracted_spacing=[4, 8, 12, 16, 24, 32],

    # Confidence and missing fields
    extraction_quality="high",  # "low" | "medium" | "high"
    missing_fields=["breakpoints"],  # If cannot parse
    assumptions=[
        "Responsive design assumes mobile-first",
        "Navigation structure inferred from HTML classes"
    ],
    design_assumptions={
        "navigation": {...},
        "states": {...},
        "breakpoints": {...}
    }
)
```

#### Step 5.2: Save Original Files to Sandbox

If project_id exists:

```tool
filesystem_mkdir
path: design_snapshots/{version}/
```

```tool
filesystem_write_file
path: design_snapshots/{version}/original.html
content: {Security-processed HTML}
```

```tool
filesystem_write_file
path: design_snapshots/{version}/styles.css
content: {Security-processed CSS}
```

#### Step 5.3: Create Artifact

```tool
create_artifact
workspace_id: {workspace_id}
playbook_code: design_snapshot_ingestion
artifact_type: markdown
title: "Design Snapshot v{version} - {source_tool}"
summary: "Design snapshot: source {source_tool}, version {version}, quality {extraction_quality}"
content:
  # Design Snapshot Summary

  **Source**: {source_tool}
  **Version**: {version}
  **Created**: {snapshot_date}

  ## Parsing Quality
  - Quality Level: {extraction_quality}
  - Missing Fields: {missing_fields}

  ## Design Elements
  - Navigation Structure: {parsed/partially parsed}
  - Color Scheme: {extracted}
  - Typography System: {extracted}

  ## Design Assumptions
  {assumptions list}
metadata:
  # Use DesignSnapshotMetadata schema
  kind: design_snapshot
  source_tool: {source_tool}
  version: {version}
  snapshot_date: {ISO8601}
  variant_id: {variant_id}
  active_variant: {active_variant}
  source_hash: {source_hash}
  extractor_version: {extractor_version}
  parent_snapshot_id: {parent_snapshot_id}
  branch: {branch}
  lineage_key: {lineage_key}
  navigation_structure: {...}
  page_states: [...]
  extracted_colors: {...}
  extracted_typography: {...}
  extracted_spacing: [...]
  extraction_quality: {extraction_quality}
  missing_fields: [...]
  assumptions: [...]
  design_assumptions: {...}
primary_action_type: view
```

---

### Phase 6: Optional Baseline Configuration

If user selected to set as baseline in Phase 4.3, execute:

```tool
# Set baseline via API (requires tool implementation or direct API call)
# POST /api/v1/workspaces/{workspace_id}/web-generation/baseline
# Body: {
#   "snapshot_id": "{artifact_id}",
#   "variant_id": "{variant_id}",
#   "project_id": "{project_id}",
#   "lock_mode": "{lock_mode}"
# }
```

**Note**: If tool not yet implemented, can prompt user "Please set baseline in UI".

---

## Outputs

After completion, the following outputs are generated:

1. **Design Snapshot Artifact**:
   - Artifact ID: `{snapshot_artifact_id}`
   - Stored in workspace artifacts
   - Metadata contains complete `DesignSnapshotMetadata`

2. **Original Files** (if project_id exists):
   ```
   design_snapshots/{version}/
   ├── original.html  # Security-processed HTML
   └── styles.css     # Security-processed CSS
   ```

3. **Baseline Configuration** (if selected):
   - Record in `web_generation_baselines` table
   - Event record in `baseline_events` table

---

## Quality Checklist

Before completion, check:

- [ ] HTML/CSS has been security processed (no script, no inline handlers)
- [ ] `source_hash` has been calculated
- [ ] Parsing quality has been recorded (`extraction_quality` + `missing_fields`)
- [ ] Metadata conforms to `DesignSnapshotMetadata` schema
- [ ] Original files have been saved to sandbox (if project_id exists)
- [ ] Artifact has been correctly created
- [ ] If set as baseline, baseline configuration has been recorded

---

## Next Steps

After completing design snapshot ingestion, you can:

1. **View Snapshot in UI**: View Design Snapshot Card in Artifacts panel
2. **Set Baseline**: Set snapshot as baseline in UI (if not already set)
3. **Continue web-generation workflow**:
   - Run `page_outline` playbook (will read Design Snapshot as reference)
   - Run `site_spec_generation` playbook (will integrate design baseline)

---

## Notes

1. **Security First**: HTML/CSS must be security processed, never execute any script
2. **Versioning**: Each import should create a new version snapshot, maintaining history traceability
3. **Quality Marking**: Honestly record parsing quality, avoid false precision
4. **Optional Enhancement**: Baseline setting is optional, can be set later in UI
5. **Backward Compatibility**: If no Design Snapshot exists, subsequent playbooks can still run with original logic

---

## Technical References

- **Schema Definition**: `capabilities/web_generation/schema/design_snapshot_schema.py`
- **Security Strategy**: See `docs/ui-engineering-decisions.md` → Decision Point #3
- **Version Governance**: See `docs/ui-engineering-decisions.md` → Decision Points #1, #2, #4
- **Complete Workflow**: `docs/complete-pipeline-workflow.md`
