# Version Management

Guidelines for managing playbook versions.

## Semantic Versioning

Follow [Semantic Versioning](https://semver.org/) (MAJOR.MINOR.PATCH):

- **MAJOR** (1.0.0): Breaking changes
- **MINOR** (1.1.0): New features (backward compatible)
- **PATCH** (1.1.1): Bug fixes (backward compatible)

## Version in package.json

```json
{
  "version": "1.0.0"
}
```

## Version in playbook.json

```json
{
  "version": "1.0.0",
  "playbook_code": "your_playbook"
}
```

**Note**: Keep versions in sync between `package.json` and `playbook.json`.

## Versioning Strategy

### Initial Release

Start with `1.0.0` for the first stable release.

### Feature Additions

Increment MINOR version:
- `1.0.0` → `1.1.0` - Added new UI component
- `1.1.0` → `1.2.0` - Added new handler endpoint

### Bug Fixes

Increment PATCH version:
- `1.1.0` → `1.1.1` - Fixed component bug
- `1.1.1` → `1.1.2` - Fixed handler error

### Breaking Changes

Increment MAJOR version:
- `1.2.0` → `2.0.0` - Changed API structure
- `2.0.0` → `3.0.0` - Removed deprecated features

## Breaking Changes

Examples of breaking changes:
- Changing component prop names
- Removing API endpoints
- Changing data structure
- Requiring new dependencies

## Migration Guide

When making breaking changes, provide a migration guide:

```markdown
## Migration from 1.x to 2.0

### Component Props

Old:
```typescript
<YourComponent data={items} />
```

New:
```typescript
<YourComponent items={items} />
```
```

## Changelog

Maintain a CHANGELOG.md:

```markdown
# Changelog

## [2.0.0] - 2025-12-05

### Breaking Changes
- Changed component prop `data` to `items`

### Added
- New handler endpoint `/custom-data`

### Fixed
- Fixed component rendering issue
```

---

**Status**: Content completed with versioning guidelines

