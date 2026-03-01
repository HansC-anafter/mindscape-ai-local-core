---
name: scaffold-pack
description: Scaffold a new Capability Pack project alongside local-core, including manifest, playbook, and tool templates. Sets up Docker volume mount for live development.
---

# Scaffold a New Capability Pack

> Registry loader: `backend/app/capabilities/registry.py`

Creates a standalone project directory alongside `mindscape-ai-local-core` for developing a new Capability Pack. The pack is loaded via Docker volume mount during development and can later be packaged as `.mindpack` for distribution.

---

## Prerequisites

- `mindscape-ai-local-core` cloned and running via Docker Compose
- Docker Compose available on host

**Gather from user before starting:**

| Parameter | Example | Description |
|-----------|---------|-------------|
| `PACK_NAME` | `my_assistant` | Capability pack code (snake_case, no hyphens) |
| `PROJECT_DIR` | `mindscape-ai-playbook` | Project directory name (created next to local-core) |
| `PLAYBOOK_CODE` | `my_assistant.analyze` | First playbook code (convention: `{pack}.{action}`) |
| `DISPLAY_NAME` | `My Assistant` | Human-readable pack name |

---

## Step 1: Create Project Directory

```bash
# Determine local-core parent directory
LOCAL_CORE_DIR="<absolute path to mindscape-ai-local-core>"
PARENT_DIR="$(dirname "$LOCAL_CORE_DIR")"
PROJECT_DIR="$PARENT_DIR/<PROJECT_DIR>"

mkdir -p "$PROJECT_DIR/capabilities/<PACK_NAME>"
cd "$PROJECT_DIR"
git init
```

---

## Step 2: Scaffold Pack Structure

Create the following directory tree inside `capabilities/<PACK_NAME>/`:

```bash
PACK_DIR="$PROJECT_DIR/capabilities/<PACK_NAME>"

mkdir -p "$PACK_DIR/playbooks/specs"
mkdir -p "$PACK_DIR/playbooks/zh-TW"
mkdir -p "$PACK_DIR/playbooks/en"
mkdir -p "$PACK_DIR/tools"
mkdir -p "$PACK_DIR/services"
mkdir -p "$PACK_DIR/api"
mkdir -p "$PACK_DIR/schema"
mkdir -p "$PACK_DIR/docs"
```

---

## Step 3: Create manifest.yaml

Write `capabilities/<PACK_NAME>/manifest.yaml`:

```yaml
code: <PACK_NAME>
display_name: "<DISPLAY_NAME>"
version: "0.1.0"
type: feature
description: |
  <One-line description of what this capability does.>

playbooks:
  - code: <PLAYBOOK_CODE>
    display_name: "<Playbook Display Name>"
    locales:
      - zh-TW
      - en
    path: playbooks/{locale}/<playbook_basename>.md
    spec_path: playbooks/specs/<playbook_basename>.json
    description: "<Playbook description>"

tools:
  - name: <tool_name>
    description: "<Tool description>"
    backend: "capabilities.<PACK_NAME>.tools.<tool_name>:run"
    input_schema:
      type: object
      properties:
        query:
          type: string
          description: "Input query"
      required:
        - query
```

> Replace `<playbook_basename>` with the part after the dot in `<PLAYBOOK_CODE>`. For example, if `PLAYBOOK_CODE` is `my_assistant.analyze`, the basename is `analyze`.

---

## Step 4: Create Playbook Spec (JSON)

Write `capabilities/<PACK_NAME>/playbooks/specs/<playbook_basename>.json`:

```json
{
  "playbook_code": "<PLAYBOOK_CODE>",
  "name": "<Playbook Display Name>",
  "description": "<Playbook description>",
  "version": "0.1.0",
  "input_schema": {
    "type": "object",
    "properties": {
      "target": {
        "type": "string",
        "description": "Primary input for this playbook"
      }
    },
    "required": ["target"]
  },
  "steps": [
    {
      "step_id": "step_1",
      "name": "analyze",
      "description": "Run the analysis tool",
      "tool_slot": "<PACK_NAME>.<tool_name>",
      "params": {
        "query": "{{input.target}}"
      }
    }
  ],
  "required_capabilities": ["<PACK_NAME>"]
}
```

> ⚠️ Use `tool_slot` (not `tool`). Format: `<PACK_NAME>.<tool_name>`.

---

## Step 5: Create Playbook Markdown

Write locale-specific playbook instructions:

**`capabilities/<PACK_NAME>/playbooks/en/<playbook_basename>.md`**:

```markdown
# <Playbook Display Name>

## Goal
<Describe what this playbook accomplishes.>

## Steps
1. <Step description>

## Expected Output
<Describe the expected artifacts or results.>
```

Copy and translate for other locales (e.g. `zh-TW/`).

---

## Step 6: Create Tool Template

Write `capabilities/<PACK_NAME>/tools/__init__.py`:

```python
```

Write `capabilities/<PACK_NAME>/tools/<tool_name>.py`:

```python
import logging

logger = logging.getLogger(__name__)


async def run(query: str, **kwargs) -> dict:
    """
    Execute the tool logic.

    Args:
        query: Input query string

    Returns:
        dict with result data
    """
    logger.info(f"Running with query: {query}")

    result = {
        "status": "success",
        "data": {
            "query": query,
            "output": "Replace this with real logic",
        }
    }

    return result
```

---

## Step 7: Set Up Docker Volume Mount (Dev Mode)

Edit or create `docker-compose.override.yml` in the **local-core** directory:

```yaml
# docker-compose.override.yml
# Mount external capability pack for live development.
# This file is gitignored — do not commit.

services:
  backend:
    volumes:
      - <PROJECT_DIR>:/mindscape-ai-playbook:ro
```

> Replace `<PROJECT_DIR>` with the **absolute path** to the project directory created in Step 1.

Ensure `docker-compose.override.yml` is in `.gitignore`:

```bash
cd <LOCAL_CORE_DIR>
grep -q 'docker-compose.override.yml' .gitignore || echo 'docker-compose.override.yml' >> .gitignore
```

---

## Step 8: Restart & Verify

```bash
cd <LOCAL_CORE_DIR>
docker compose restart backend
```

// turbo
```bash
cd <LOCAL_CORE_DIR>
echo "--- Registered capabilities ---"
curl -s http://localhost:8200/api/v1/capability-packs/ | python3 -m json.tool | grep '"code"'
echo "--- Registered playbooks ---"
curl -s http://localhost:8200/api/v1/playbooks/ | python3 -m json.tool | grep '"playbook_code"'
echo "--- Registered tools ---"
curl -s http://localhost:8200/api/v1/tools/ | python3 -m json.tool | grep '"name"'
```

**Expected**: `<PACK_NAME>`, `<PLAYBOOK_CODE>`, and `<PACK_NAME>.<tool_name>` appear in the output.

---

## Step 9: Create .gitignore for Pack Project

Write `.gitignore` in the project root:

```
__pycache__/
*.pyc
.env
node_modules/
*.mindpack
.DS_Store
```

---

## Summary of Created Files

```
<PROJECT_DIR>/
├── .gitignore
├── capabilities/
│   └── <PACK_NAME>/
│       ├── manifest.yaml
│       ├── playbooks/
│       │   ├── specs/
│       │   │   └── <playbook_basename>.json
│       │   ├── en/
│       │   │   └── <playbook_basename>.md
│       │   └── zh-TW/
│       │       └── <playbook_basename>.md
│       ├── tools/
│       │   ├── __init__.py
│       │   └── <tool_name>.py
│       ├── services/
│       ├── api/
│       ├── schema/
│       └── docs/
└── (optional) scripts/
```

---

## Packaging for Distribution (Optional)

To share the pack as a `.mindpack` file for installation on other local-core instances:

```bash
cd <PROJECT_DIR>
tar czf <PACK_NAME>.mindpack -C capabilities/<PACK_NAME> manifest.yaml -C <PROJECT_DIR> capabilities/<PACK_NAME>
```

Install on target local-core:

```bash
curl -X POST http://localhost:8200/api/v1/capability-packs/install-from-file \
  -F "file=@<PACK_NAME>.mindpack"
```

---

## FATAL Rules

- **NEVER** commit capability source directly into `local-core/backend/app/capabilities/`
- **NEVER** commit `docker-compose.override.yml` to Git
- **NEVER** hardcode secrets in tool or service files
- **ALWAYS** use `tool_slot` format `<pack>.<tool>` in playbook specs (not legacy `tool` field)
- **ALWAYS** keep the pack project in a **separate directory** from local-core
