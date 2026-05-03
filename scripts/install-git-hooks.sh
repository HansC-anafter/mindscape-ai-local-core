#!/bin/bash
# Install Git hooks for capability file protection

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
HOOKS_DIR="$REPO_ROOT/.git/hooks"
TEMPLATES_DIR="$SCRIPT_DIR/git-hooks"

echo "Installing Git hooks for capability file protection..."

# Check if .git directory exists
if [ ! -d "$REPO_ROOT/.git" ]; then
    echo "Error: Not a git repository"
    exit 1
fi

# Install pre-commit hook
if [ -f "$TEMPLATES_DIR/pre-commit.template" ]; then
    cp "$TEMPLATES_DIR/pre-commit.template" "$HOOKS_DIR/pre-commit"
    chmod +x "$HOOKS_DIR/pre-commit"
    echo "OK Installed pre-commit hook"
else
    echo "WARNING  Warning: pre-commit.template not found"
fi

# Install pre-push hook
if [ -f "$TEMPLATES_DIR/pre-push.template" ]; then
    cp "$TEMPLATES_DIR/pre-push.template" "$HOOKS_DIR/pre-push"
    chmod +x "$HOOKS_DIR/pre-push"
    echo "OK Installed pre-push hook"
else
    echo "WARNING  Warning: pre-push.template not found"
fi

echo ""
echo "Git hooks installed successfully!"
echo ""
echo "These hooks will prevent committing files that should be installed via CapabilityInstaller:"
echo "  - Feature-specific playbooks"
echo "  - Feature-specific model packages"
echo "  - Capability files"
echo ""
echo "See: docs/contributor-guide/capability-installer-guard.md"
