# Brand Mindscape Blueprint

> **Document Date**: 2025-12-12
> **Status**: Active
> **Version**: v1.0

---

## Overview

The Brand Mindscape Blueprint provides a pre-configured workspace setup for brand management, including initial artifacts, recommended playbooks, and workspace configuration.

---

## Blueprint Structure

```
brand-mindscape/
├── workspace.json          # Workspace initial configuration
├── playbooks.json          # Recommended playbook IDs
└── artifacts/              # Initial artifact templates
    ├── brand-mi.md         # Brand Mind Identity
    ├── brand-persona.md    # Brand Personas
    ├── brand-storyline.md  # Brand Storylines
    └── brand-vi-rule.md   # Visual Identity Rules
```

---

## Artifacts

### Brand Mind Identity (brand-mi.md)

**Kind**: `brand_mi`

**Description**: Defines the brand's core identity including vision, values, worldview, and redlines.

**Structure**:
- Vision: Brand vision statement
- Values: List of brand values
- Worldview: Brand worldview description
- Redlines: List of brand redlines (things the brand should never do)

### Brand Personas (brand-persona.md)

**Kind**: `brand_persona`

**Description**: Defines target audience personas for the brand.

**Structure**:
- Name: Persona name
- Description: Detailed persona description
- Needs: List of persona needs
- Pain Points: List of persona pain points

### Brand Storylines (brand-storyline.md)

**Kind**: `brand_storyline`

**Description**: Defines core brand story themes and narratives.

**Structure**:
- Theme: Storyline theme name
- Description: Storyline description
- Key Messages: List of key messages for this storyline

### Visual Identity Rules (brand-vi-rule.md)

**Kind**: `brand_vi_rule`

**Description**: Defines visual identity guidelines including color palette, typography, imagery style, and layout guidelines.

**Structure**:
- Color Palette: Brand color definitions
- Typography: Font specifications
- Imagery Style: Image style guidelines
- Layout Guidelines: Layout and composition rules
- Brand Hub Links: Links to brand assets
- Redlines: Visual identity redlines
- Usage Examples: Examples of correct usage

---

## Usage

### Loading the Blueprint

```bash
POST /api/v1/blueprints/brand-mindscape/load
{
  "workspace_name": "My Brand Workspace",
  "profile_id": "profile-123"
}
```

### Workspace Configuration

The blueprint creates a workspace with:
- `workspace_type`: `brand`
- Initial artifacts loaded from `artifacts/` directory
- Recommended playbooks from `playbooks.json`

### Recommended Playbooks

The blueprint recommends the following playbooks:
- `cis_mind_identity`: Extract CIS from brand documents
- `cross_channel_story`: Create cross-channel brand stories
- `brand_monthly_review`: Monthly brand review and analysis

---

## Artifact Metadata

All artifacts include front matter with:
- `kind`: Artifact kind (e.g., `brand_mi`, `brand_persona`, `brand_storyline`, `brand_vi_rule`)
- `title`: Artifact title
- `summary`: Brief summary
- `workspace_id`: Workspace identifier (set during blueprint load)

---

## Customization

You can customize the blueprint by:
1. Modifying artifact templates in `artifacts/`
2. Adding or removing recommended playbooks in `playbooks.json`
3. Adjusting workspace configuration in `workspace.json`

---

**Last Updated**: 2025-12-12
**Maintainer**: Mindscape AI Development Team
