# Repository Structure

## Playbook Repository Structure

A playbook repository should follow this structure:

```
your-playbook/
├── package.json              # NPM package configuration
├── tsconfig.json             # TypeScript configuration
├── README.md                 # Project documentation
├── .gitignore                # Git ignore rules
│
├── playbook/                 # Playbook definition
│   ├── your_playbook.json    # Workflow definition (required)
│   ├── your_playbook.md      # i18n (zh-TW, required)
│   ├── i18n/                 # Additional i18n files
│   │   └── en/
│   │       └── your_playbook.md
│   └── UI_LAYOUT.json        # UI layout configuration (optional)
│
├── components/               # React UI components (optional)
│   └── your-playbook/
│       ├── YourComponent.tsx
│       └── index.ts
│
├── backend/                  # Python handlers (optional)
│   └── handlers.py
│
└── src/                      # Registration and exports
    └── index.ts              # Registration function (required)
```

## File Descriptions

### package.json

**Required fields**:
```json
{
  "name": "@mindscape/playbook-your-playbook",
  "version": "1.0.0",
  "main": "src/index.ts",
  "types": "src/index.ts",
  "mindscape": {
    "type": "playbook",
    "playbook_code": "your_playbook",
    "register_function": "registerYourPlaybook"
  }
}
```

### playbook/your_playbook.json

Workflow definition in JSON format. See [Playbook Definition Schema](../playbook-definition/schema.md).

### playbook/your_playbook.md

Internationalization file in Traditional Chinese. See [i18n Format](#i18n-format).

### playbook/UI_LAYOUT.json

UI layout configuration (optional). Only needed if your playbook has custom UI components.

```json
{
  "type": "your_playbook_type",
  "left_sidebar": {
    "type": "your_sidebar_type",
    "component": "YourSidebarComponent",
    "config": {}
  },
  "main_surface": {
    "layout": "three_column",
    "components": [
      {
        "type": "YourComponent",
        "position": "center",
        "config": {}
      }
    ]
  }
}
```

### src/index.ts

Registration function that registers your playbook with the core system.

```typescript
interface PlaybookRegistry {
  register(playbook: {
    playbookCode: string;
    version: string;
    uiLayout?: any;
    components?: Record<string, React.ComponentType<any>>;
  }): void;
}

import playbookSpec from '../playbook/your_playbook.json';
import uiLayout from '../playbook/UI_LAYOUT.json';
import { YourComponent } from '../components/your-playbook';

export function registerYourPlaybook(registry: PlaybookRegistry): void {
  registry.register({
    playbookCode: 'your_playbook',
    version: playbookSpec.version,
    uiLayout: uiLayout,
    components: {
      'YourComponent': YourComponent,
    }
  });
}
```

## i18n Format

The i18n file (`your_playbook.md`) should follow this format:

```markdown
playbook_code: your_playbook

name: Your Playbook Name
description: Your playbook description

tags:
  - tag1
  - tag2

entry_points:
  - workspace_playbook_menu

# Your Playbook Name

Your playbook description in Traditional Chinese.

## Features

- Feature 1
- Feature 2
```

## Naming Conventions

- **Package name**: `@mindscape/playbook-{kebab-case}`
- **Playbook code**: `{snake_case}`
- **Component directory**: `{kebab-case}`
- **Component files**: `PascalCase.tsx`

## Example

See [Yearly Book Example](../examples/yearly-book.md) for a complete example.

---

**Status**: Framework ready, content to be expanded

