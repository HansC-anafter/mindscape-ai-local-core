# Use Case: Yearly Personal Book / 年度個人書

> **Category**: Personal & Creative
> **Complexity**: Medium
> **Related Playbook**: `yearly_personal_book`

---

## 1. Scenario Overview

**Goal**: At the end of each year, generate a personal memoir/growth book from your year-long conversations with Mindscape AI.

**The Challenge**: You've had hundreds of conversations throughout the year — daily planning, project discussions, personal reflections. Without a system, these valuable insights are scattered across chat logs with no structure or narrative.

**The Outcome**: A coherent, structured book that captures:
- Key themes and growth areas
- Significant decisions and their outcomes
- Recurring patterns and insights
- Personal milestones and achievements

---

## 2. Why Traditional Tools Fall Short

| Problem | Traditional AI | Mindscape |
|---------|---------------|-----------|
| **Data Scattered** | Export chat logs, manually organize | All conversations tagged with Intents and Projects |
| **No Context** | AI has no memory of past conversations | Long-term memory preserves context across time |
| **Privacy Concerns** | Data on third-party servers | Local-first: all data stays on your machine |
| **No Structure** | Raw text dumps | Intent/Project hierarchy provides natural chapters |
| **Style Inconsistency** | Each regeneration varies | Mind-Lens ensures consistent voice throughout |

---

## 3. Mindscape Solution

### Architecture Flow

```
Year of Conversations
        ↓
  ┌─────────────────────────────────────┐
  │  1. Theme Extraction                │ ← Playbook: analyze_yearly_themes
  │     - Identify recurring topics     │
  │     - Cluster by Intent/Project     │
  └─────────────────────────────────────┘
        ↓
  ┌─────────────────────────────────────┐
  │  2. Chapter Structure               │ ← Playbook: structure_book_outline
  │     - Map themes to chapters        │
  │     - Identify key moments          │
  └─────────────────────────────────────┘
        ↓
  ┌─────────────────────────────────────┐
  │  3. Content Generation              │ ← Playbook: draft_chapter
  │     - Generate chapter drafts       │
  │     - Apply personal Mind-Lens      │
  └─────────────────────────────────────┘
        ↓
  ┌─────────────────────────────────────┐
  │  4. Human Review & Refinement       │ ← Governance checkpoint
  │     - Review each chapter Take      │
  │     - Select preferred versions     │
  └─────────────────────────────────────┘
        ↓
  ┌─────────────────────────────────────┐
  │  5. Final Compilation               │ ← Playbook: compile_book
  │     - Assemble chapters             │
  │     - Generate intro/outro          │
  └─────────────────────────────────────┘
        ↓
    Personal Annual Book
```

### Key Governance Points

| Checkpoint | Governance Type | What You Control |
|------------|----------------|------------------|
| Theme Selection | Intent Governance | Which themes to include/exclude |
| Chapter Structure | Intent Governance | How to organize your story |
| Chapter Draft Review | Asset Governance | Compare Takes, select best version |
| Sensitive Content | Trust Governance | Flag and review personal content |
| Final Approval | Asset Governance | Approve before export/publish |

---

## 4. Key Playbooks Involved

### Core Playbooks

| Playbook | Purpose |
|----------|---------|
| `analyze_yearly_themes` | Extract themes from conversation history |
| `structure_book_outline` | Create chapter structure based on themes |
| `draft_chapter` | Generate individual chapter content |
| `compile_book` | Assemble final book with formatting |

### Supporting Playbooks

| Playbook | Purpose |
|----------|---------|
| `extract_quotes` | Pull out meaningful quotes and insights |
| `generate_timeline` | Create visual timeline of the year |
| `review_sensitive` | Flag potentially sensitive content for review |

---

## 5. Privacy-First Design

### What Stays Local

```
┌─────────────────────────────────────────┐
│          Your Local Machine             │
├─────────────────────────────────────────┤
│  ✓ All conversation history             │
│  ✓ Generated book content               │
│  ✓ All Takes and Selections             │
│  ✓ Personal Mind-Lens settings          │
│  ✓ Theme analysis results               │
└─────────────────────────────────────────┘
                    │
                    │ (only API calls leave)
                    ↓
┌─────────────────────────────────────────┐
│          LLM Provider                   │
├─────────────────────────────────────────┤
│  • Receives: anonymized prompts         │
│  • Does not receive: full history       │
│  • Does not retain: conversation data   │
└─────────────────────────────────────────┘
```

### Data Control

- **Opt-in Analysis**: Only conversations you explicitly include are analyzed
- **Redaction Support**: Sensitive content can be redacted before processing
- **Local Export**: Final book is exported locally (PDF, EPUB, Markdown)
- **No Cloud Sync**: Book content never leaves your machine unless you choose to share

---

## 6. Example Workflow

### Step 1: Initialize the Project

```bash
# Create a new Project for this year's book
POST /api/v1/workspaces/{ws_id}/projects
{
  "type": "yearly_book",
  "title": "My 2025 Journey",
  "flow_id": "yearly_book_flow"
}
```

### Step 2: Run Theme Analysis

The `analyze_yearly_themes` playbook scans your conversations:

```yaml
# playbook: analyze_yearly_themes
steps:
  - action: query_conversations
    params:
      date_range: "2025-01-01 to 2025-12-31"
      group_by: [intent, project, month]

  - action: extract_themes
    ai_member: analyst
    params:
      min_occurrences: 5
      exclude_categories: [system, routine]

  - action: save_artifact
    params:
      type: theme_summary
      path: "{sandbox}/themes.json"
```

### Step 3: Review Themes (Governance Checkpoint)

**You review** the extracted themes and decide:
- Which themes to include in the book
- How to prioritize them
- Any themes to combine or split

### Step 4: Generate Chapters

For each approved theme, the `draft_chapter` playbook generates content:

- Each chapter may have multiple **Takes** (generation attempts)
- You compare Takes and **Select** the best version
- Rollback is always available if you change your mind later

### Step 5: Final Compilation

The `compile_book` playbook:
- Assembles all selected chapter Segments
- Generates introduction and conclusion
- Applies consistent formatting via Mind-Lens
- Exports to your preferred format

---

## 7. Mind-Lens Configuration

### Recommended Lens Settings for Personal Book

```yaml
# lens: personal_memoir
voice:
  tone: reflective, honest
  perspective: first_person
  formality: casual_but_thoughtful

constraints:
  - Use past tense for recounting events
  - Include emotional context, not just facts
  - Connect events to personal growth themes

preferences:
  paragraph_length: medium
  use_quotes: frequent
  include_dates: when_relevant
```

---

## 8. Differences: Local vs Cloud

| Aspect | Local-Core | Cloud Extension |
|--------|-----------|-----------------|
| Data Storage | All local | Optional cloud backup (encrypted) |
| Processing | Local LLM or API calls | Additional cloud generation options |
| Sharing | Manual export | Collaborative editing (if enabled) |
| Templates | Built-in playbooks | Community playbook marketplace |

---

## 9. Related Documents

- [Asset Provenance Architecture](../core-architecture/asset-provenance.md) — How chapter Takes and Selections work
- [Playbooks & Workflows](../core-architecture/playbooks-and-workflows.md) — How the book generation flow is orchestrated
- [Brand: Yearly Book Use Case](file:///Users/shock/Projects_local/workspace/site-brand/sites/mindscape-ai/docs/MINDSCAPE_AI_USE_CASE_YEARLY_BOOK.md) — Marketing description of this use case
