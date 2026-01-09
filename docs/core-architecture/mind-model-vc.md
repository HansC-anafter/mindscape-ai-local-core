# Mind-Model VC Architecture

Mind-Model VC (Version Control for Mind Models) organizes "clues you're willing to provide" into reviewable, adjustable, and rollback-able "mind state recipes" with version history.

**Last Updated**: 2026-01-07
**Status**: Architecture Design
**Version**: v0.1.0

---

## Overview

### Core Position

> **This is a Mind Palette, not a mind diagnosis.**
> **The system does not claim to understand you; it only provides tools for "color mixing" and "version history".**

Key principles:

- **It's your self-described/chosen modeling** (not AI secretly inferring)
- **It's editable, revocable, and can be cooled down** (not stuck once applied)
- **VC is not for "the person", but for "a mind recipe (model draft) that you can adopt/reject"**

### Relationship with Existing Architecture

Mind-Model VC sits above the existing "Asset & Process Governance" layer, providing "mind modeling version control" capabilities. It integrates with:

- **Event Layer**: Extracts candidate Swatches from Events (status=SUGGESTED, requires user confirmation)
- **Intent Governance Layer**: IntentSteward decisions can serve as Swatch candidate sources
- **ExecutionContext**: Adds optional `current_mix_id` field for referencing current confirmed recipe

---

## Core Concepts: Swatch / Mix / Commit

### Swatch (Color Swatch / Clue)

**Definition**: Any clue you're willing to provide.

**Key Design**:

- **Opt-in**: System suggests, you confirm
- **Status flow**: SUGGESTED → CONFIRMED (user confirmation required)
- **Markable**: You can mark importance or reject

**Implementation Reference**: `backend/app/models/mind_model_vc.py`

### Mix (Recipe / Current Color Mixing)

**Definition**: Intent/viewpoint combination in a time window.

**Characteristics**:

- Contains 3-7 main colors (main intents) + weights
- User writes title/description (not AI-generated)
- Status: DRAFT → CONFIRMED (user confirmation required)

**Implementation Reference**: `backend/app/models/mind_model_vc.py`

### Commit (Version / Change)

**Definition**: Mix changes, with your own commit message.

**Key Design**:

- **Commit message is written by you**, not AI-generated
- AI can suggest, but final text is confirmed/modified by you
- Rollback-able, comparable, annotatable

**Implementation Reference**: `backend/app/models/mind_model_vc.py`

### Co-Graph (Co-occurrence Relationship Graph)

Tracks co-occurrence relationships between clues/colors. Users can override labels or hide associations.

**Implementation Reference**: `backend/app/models/mind_model_vc.py`

---

## Data Models

### Database Tables

**New Tables**:

- `mind_swatches`: Color swatches/clues table
- `mind_mixes`: Recipes table
- `mind_commits`: Versions/changes table
- `mind_co_edges`: Co-occurrence relationships table

**Implementation Reference**: `backend/app/models/mind_model_vc.py`

**Key Design**:

- All clues require user confirmation (status: SUGGESTED → CONFIRMED)
- Recipes require user-written title/description (not AI-generated)
- Commit messages are written by user

---

## System Components

### SwatchCollector

Collects clues from various sources, but does not auto-confirm.

**Implementation Reference**: `backend/app/services/mind_model_vc/swatch_collector.py`

### MixDrafter

Generates recipe drafts, but only becomes official after user confirmation.

**Implementation Reference**: `backend/app/services/mind_model_vc/mix_drafter.py`

### DiffAnalyzer

Analyzes differences between recipes and suggests commit messages (user writes final version).

**Implementation Reference**: `backend/app/services/mind_model_vc/diff_analyzer.py`

### CoGraphUpdater

Builds and updates co-occurrence relationship graphs. Users can override.

**Implementation Reference**: `backend/app/services/mind_model_vc/co_graph_updater.py`

### PatternExplorer (Optional)

Provides exploration functionality for reviewing color history. Tool for user exploration, not diagnosis.

**Implementation Reference**: `backend/app/services/mind_model_vc/pattern_explorer.py`

---

## Integration with Existing Architecture

### Event Layer Integration

**Integration Point**: `backend/app/services/stores/events_store.py`

Collects candidate Swatches from Events (status=SUGGESTED, requires user confirmation).

### Intent Governance Integration

**Integration Point**: `backend/app/services/conversation/intent_steward.py`

IntentSteward decisions can serve as Swatch candidate sources.

### ExecutionContext Integration

**Integration Point**: `backend/app/mindscape/shims/execution_context.py`

Adds optional `current_mix_id` field for referencing current confirmed recipe.

---

## API Design

### Swatch API

**Implementation Reference**: `backend/app/routes/mind_model_vc/swatches.py`

- `GET /api/v1/mind-model/swatches` - Get swatch list
- `PUT /api/v1/mind-model/swatches/{swatch_id}` - Confirm/reject swatch

### Mix API

**Implementation Reference**: `backend/app/routes/mind_model_vc/mixes.py`

- `GET /api/v1/mind-model/mixes` - Get recipe list
- `GET /api/v1/mind-model/mixes/{mix_id}` - Get single recipe
- `PUT /api/v1/mind-model/mixes/{mix_id}` - Confirm recipe
- `POST /api/v1/mind-model/mixes/draft` - Generate draft recipe

### Commit API

**Implementation Reference**: `backend/app/routes/mind_model_vc/commits.py`

- `GET /api/v1/mind-model/commits` - Get version history
- `GET /api/v1/mind-model/diff/{from_mix_id}/{to_mix_id}` - Compare recipes
- `POST /api/v1/mind-model/commits` - Create commit

### Co-Graph API

**Implementation Reference**: `backend/app/routes/mind_model_vc/co_graph.py`

- `GET /api/v1/mind-model/co-graph` - Get co-occurrence graph
- `PUT /api/v1/mind-model/co-graph/clusters/{cluster_id}` - Update cluster label

---

## Design Principles

| Principle | Description |
| --------- | ----------- |
| **Opt-in, not opt-out** | Clues require user confirmation; AI suggests, user decides |
| **User writes commit message** | Change descriptions are written by user, not AI guesses |
| **Editable, revocable** | Everything can be changed, deleted |
| **Palette, not diagnosis** | System provides tools, doesn't claim "I understand you" |
| **Trajectory mutual aid, not human betting** | Social matching based on "what to do", not "who you are" |

---

**Last Updated**: 2026-01-07
**Maintainer**: Mindscape AI Development Team
**Status**: Architecture Design
