# Minimal Playbook Example

A minimal playbook with no UI components or backend handlers - just the workflow definition.

## Structure

```
minimal-playbook/
├── package.json
├── playbook/
│   ├── minimal.json
│   └── minimal.md
└── src/
    └── index.ts
```

## package.json

```json
{
  "name": "@mindscape/playbook-minimal",
  "version": "1.0.0",
  "main": "src/index.ts",
  "types": "src/index.ts",
  "mindscape": {
    "type": "playbook",
    "playbook_code": "minimal",
    "register_function": "registerMinimal"
  }
}
```

## playbook/minimal.json

```json
{
  "version": "1.0.0",
  "playbook_code": "minimal",
  "kind": "user_workflow",
  "metadata": {
    "name": "Minimal Playbook",
    "description": "A minimal playbook example",
    "tags": ["example"],
    "scope": "user",
    "entry_agent_type": "workspace"
  },
  "steps": [
    {
      "id": "process",
      "type": "llm_call",
      "tool": "core_llm.structured_extract",
      "inputs": {
        "text": "Process the following request: {{input.user_request}}"
      },
      "outputs": {
        "result": "extracted_data.result"
      }
    }
  ],
  "inputs": {
    "user_request": {
      "type": "string",
      "description": "User's request",
      "required": true
    }
  },
  "outputs": {
    "result": {
      "description": "Processing result",
      "source": "step.process.result"
    }
  }
}
```

## playbook/minimal.md

```markdown
playbook_code: minimal

name: Minimal Playbook
description: A minimal playbook example

tags:
  - example

entry_points:
  - workspace_playbook_menu

# Minimal Playbook

This is a minimal playbook example with no UI components or backend handlers.

## Features

- Basic workflow execution
- Simple LLM processing
```

## src/index.ts

```typescript
interface PlaybookRegistry {
  register(playbook: {
    playbookCode: string;
    version: string;
  }): void;
}

import playbookSpec from '../playbook/minimal.json';

export function registerMinimal(registry: PlaybookRegistry): void {
  registry.register({
    playbookCode: 'minimal',
    version: playbookSpec.version
  });
}

export default registerMinimal;
```

## Usage

This playbook will:
1. Appear in the playbook list
2. Execute the workflow when triggered
3. Use the default workspace UI (no custom surface)

---

**Status**: Complete minimal example

