# Getting Started

Create your first Mindscape AI playbook in 5 minutes.

## Prerequisites

- Node.js 18+ and npm
- TypeScript knowledge
- Basic React knowledge
- Python 3.8+ (for backend handlers, optional)

## Step 1: Create Playbook Repository

### Option A: Use Template (Recommended)

```bash
# TODO: Create playbook scaffolding tool
npx create-mindscape-playbook my-playbook
cd my-playbook
```

### Option B: Manual Setup

```bash
mkdir my-playbook
cd my-playbook
npm init -y
```

## Step 2: Configure Package

Edit `package.json`:

```json
{
  "name": "@mindscape/playbook-my-playbook",
  "version": "1.0.0",
  "description": "My custom playbook",
  "main": "src/index.ts",
  "types": "src/index.ts",
  "scripts": {
    "build": "tsc",
    "dev": "tsc --watch"
  },
  "mindscape": {
    "type": "playbook",
    "playbook_code": "my_playbook",
    "register_function": "registerMyPlaybook"
  },
  "peerDependencies": {
    "react": "^18.0.0",
    "react-dom": "^18.0.0"
  },
  "devDependencies": {
    "@types/react": "^18.0.0",
    "@types/react-dom": "^18.0.0",
    "typescript": "^5.0.0"
  }
}
```

## Step 3: Create Directory Structure

```bash
mkdir -p playbook/i18n/en components/my-playbook src backend
```

## Step 4: Create Playbook Definition

Create `playbook/my_playbook.json`:

```json
{
  "version": "1.0.0",
  "playbook_code": "my_playbook",
  "metadata": {
    "name": "My Playbook",
    "description": "A simple playbook example",
    "tags": ["example"],
    "scope": "user",
    "entry_agent_type": "workspace"
  },
  "steps": [
    {
      "id": "step1",
      "type": "llm_call",
      "prompt": {
        "text": "Hello, this is my first playbook step. Process: {{user_request}}"
      },
      "outputs": {
        "result": "extracted_data.result"
      }
    }
  ],
  "outputs": {
    "result": {
      "description": "Processing result",
      "source": "step.step1.result"
    }
  }
}
```

## Step 5: Create i18n Files

Create `playbook/my_playbook.md` (Traditional Chinese):

```markdown
playbook_code: my_playbook

name: 我的 Playbook
description: 一個簡單的 Playbook 範例

tags:
  - example

entry_points:
  - workspace_playbook_menu

# 我的 Playbook

這是一個簡單的 Playbook 範例，展示如何建立基本的 Playbook。

## 功能

- 基本工作流程執行
- 簡單的 LLM 呼叫
```

Create `playbook/i18n/en/my_playbook.md` (English):

```markdown
playbook_code: my_playbook

name: My Playbook
description: A simple playbook example

tags:
  - example

entry_points:
  - workspace_playbook_menu

# My Playbook

This is a simple playbook example demonstrating how to create a basic playbook.

## Features

- Basic workflow execution
- Simple LLM calls
```

## Step 6: Create Registration Function

Create `src/index.ts`:

```typescript
/**
 * PlaybookRegistry type - will be provided by core at runtime
 */
interface PlaybookRegistry {
  register(playbook: {
    playbookCode: string;
    version: string;
    uiLayout?: any;
    components?: Record<string, React.ComponentType<any>>;
  }): void;
}

import playbookSpec from '../playbook/my_playbook.json';

export function registerMyPlaybook(registry: PlaybookRegistry): void {
  registry.register({
    playbookCode: 'my_playbook',
    version: playbookSpec.version,
    // uiLayout: uiLayout,  // Optional: if you have UI components
    // components: { ... }  // Optional: if you have UI components
  });
}

export default registerMyPlaybook;
```

## Step 7: Create TypeScript Config

Create `tsconfig.json`:

```json
{
  "compilerOptions": {
    "target": "ES2020",
    "module": "commonjs",
    "lib": ["ES2020", "DOM"],
    "jsx": "react",
    "declaration": true,
    "outDir": "./dist",
    "rootDir": "./",
    "strict": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "forceConsistentCasingInFileNames": true,
    "moduleResolution": "node",
    "resolveJsonModule": true
  },
  "include": ["src/**/*", "components/**/*"],
  "exclude": ["node_modules", "dist"]
}
```

## Step 8: Install and Test

### Install in Mindscape AI Workspace

```bash
# In your Mindscape AI workspace directory
cd mindscape-ai-local-core/web-console
npm install ../my-playbook
```

### Verify Installation

1. Start Mindscape AI
2. Go to Playbooks page
3. Your playbook should appear in the list
4. Click "Execute Now" to test

## Next Steps

- [Frontend Guide](./frontend/guide.md) - Add UI components
- [Backend Guide](./backend/guide.md) - Add backend handlers
- [Examples](./examples/) - See complete examples

## Troubleshooting

### Playbook not appearing

- Check `package.json` has correct `mindscape` configuration
- Verify registration function name matches `register_function`
- Check console for errors

### Import errors

- Ensure TypeScript is properly configured
- Check that all dependencies are installed
- Verify file paths are correct

---

**Status**: Content completed with detailed steps
