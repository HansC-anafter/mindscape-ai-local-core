# Publishing Your Playbook

## Overview

This guide explains how to publish your playbook as an NPM package.

## Prerequisites

- NPM account
- Package name follows `@mindscape/playbook-*` convention
- All required files are in place

## Publishing Steps

### 1. Prepare Package

Ensure your `package.json` is correctly configured:

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

### 2. Build

```bash
npm run build
```

### 3. Publish

```bash
npm publish --access public
```

## Versioning

Follow semantic versioning:
- `1.0.0` - Major release
- `1.1.0` - Minor release (new features)
- `1.1.1` - Patch release (bug fixes)

## Installation

Users install your playbook:

```bash
npm install @mindscape/playbook-your-playbook
```

The playbook will be automatically loaded by Mindscape AI core.

## Checklist

Before publishing:
- [ ] All required files are present
- [ ] `package.json` is correctly configured
- [ ] Playbook definition is valid
- [ ] Components are properly exported
- [ ] Handler is properly implemented (if applicable)
- [ ] README.md is complete
- [ ] Version number is correct

---

**Status**: Framework ready, content to be expanded with detailed steps

