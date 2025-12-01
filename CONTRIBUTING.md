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

### Testing

- Write tests for new features
- Ensure all tests pass before submitting PR
- Aim for good test coverage

## Questions?

Feel free to open an issue for questions or discussions.

Thank you for contributing! 🎉

