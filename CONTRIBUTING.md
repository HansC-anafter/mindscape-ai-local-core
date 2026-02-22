# Contributing to Mindscape AI Local Core

Thank you for your interest in contributing to the `mindscape-ai-local-core` repository!

## Code of Conduct

- Be respectful and inclusive
- Focus on constructive feedback
- Help maintain a welcoming environment

## How to Contribute

### Reporting Issues

- Use GitHub Issues to report bugs or request features
- Include clear descriptions and reproduction steps
- Check existing issues before creating new ones

### Submitting Changes

1. **Fork the repository**
2. **Create a feature branch**: `git checkout -b feature/your-feature-name`
3. **Make your changes**
4. **Follow coding standards**:
   - Use English for all code comments and docstrings
   - Follow PEP 8 for Python code
   - Write clear commit messages
5. **Test your changes**: `pytest tests/`
6. **Commit your changes**: Use conventional commits format
   - `feat:` for new features
   - `fix:` for bug fixes
   - `docs:` for documentation
   - `refactor:` for code refactoring
7. **Push to your fork**: `git push origin feature/your-feature-name`
8. **Create a Pull Request**

## Development Guidelines

### Code Style

- **Python**: Follow PEP 8, use type hints
- **TypeScript/JavaScript**: Follow ESLint rules
- **Comments**: Use English, be clear and concise
- **Docstrings**: Required for all public functions and classes

### Architecture Principles

- **Keep core clean**: Core domain should not contain tenant/group concepts
- **Use Port/Adapter pattern**: All external dependencies should go through Ports
- **Local-first**: This is a local-only version, no cloud-specific code

### Terminology Guardrails

These rules prevent semantic collisions in code, docs, and PR reviews:

| Term | Scope | Rule |
|------|-------|------|
| **Agent** | Identity + long-term consistency | Only refers to AgentSpec / AgentCore (intent, lens, memory + actuator). Never use "agent" to mean a model, a framework, or a tool. |
| **Executor / Runtime** | Execution environment / dispatch | Refers to external integrations (Gemini CLI, OpenClaw, LangGraph, etc.) that provide compute + sandbox. Never call a runtime an "agent". |
| **Tool / Skill** | Atomic callable capability | A function or MCP tool. Never personify tools as "agents" — tools don't have identity. |

**Examples:**
- ✅ "The OpenClaw **runtime** executed the task"
- ❌ "The OpenClaw **agent** executed the task"
- ✅ "AgentSpec defines the **agent's** identity"
- ❌ "The Gemini CLI **agent** is connected"

### Testing

- Write tests for new features
- Ensure all tests pass before submitting PR
- Aim for good test coverage

## Questions?

Feel free to open an issue for questions or discussions.

Thank you for contributing! 🎉

