# Publishing Checklist

Checklist before publishing your playbook.

## Pre-Publishing

### Package Configuration

- [ ] `package.json` has correct name (`@mindscape/playbook-*`)
- [ ] Version number is correct
- [ ] `mindscape` configuration is correct
- [ ] `register_function` matches actual function name
- [ ] All dependencies are listed

### Playbook Definition

- [ ] `playbook.json` is valid JSON
- [ ] `playbook_code` matches package name
- [ ] Version matches `package.json`
- [ ] All required fields are present
- [ ] Step IDs are unique
- [ ] Dependencies are valid

### i18n Files

- [ ] Traditional Chinese file exists (`playbook/your_playbook.md`)
- [ ] English file exists (`playbook/i18n/en/your_playbook.md`)
- [ ] All required fields are present
- [ ] Content is accurate

### Code Quality

- [ ] TypeScript compiles without errors
- [ ] No console errors in browser
- [ ] Components render correctly
- [ ] Handlers work as expected
- [ ] Error handling is in place

### UI Components (if applicable)

- [ ] Components are properly exported
- [ ] Components are registered in `src/index.ts`
- [ ] `UI_LAYOUT.json` is valid
- [ ] Components support dark mode
- [ ] Components are responsive

### Backend Handlers (if applicable)

- [ ] Handler implements `PlaybookHandler` base class
- [ ] `register_handler()` function exists
- [ ] Routes are properly registered
- [ ] Error handling is implemented
- [ ] Logging is in place

### Testing

- [ ] Playbook loads in Mindscape AI
- [ ] Playbook appears in playbook list
- [ ] Workflow executes successfully
- [ ] UI components render (if applicable)
- [ ] Handlers work (if applicable)
- [ ] No console errors

### Documentation

- [ ] README.md is complete
- [ ] Installation instructions are clear
- [ ] Usage examples are provided
- [ ] API documentation is included (if applicable)

## Publishing

### NPM

- [ ] NPM account is set up
- [ ] Package name is available
- [ ] `npm publish --access public` succeeds
- [ ] Package appears on npmjs.com

### Verification

- [ ] Install from npm: `npm install @mindscape/playbook-your-playbook`
- [ ] Playbook loads correctly
- [ ] All features work

## Post-Publishing

- [ ] Update version number for next release
- [ ] Document any known issues
- [ ] Monitor for user feedback

---

**Status**: Content completed with comprehensive checklist

