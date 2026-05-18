"""Whitelisted agent CLI catalog."""

AGENT_CLI_MAP = {
    "openclaw": {
        "command": "openclaw",
        "package": "openclaw",
        "github_repo": "https://github.com/openclaw/openclaw",
        "install_methods": [
            {"method": "npm", "command": "npm install -g openclaw"},
            {
                "method": "github",
                "command": "npm install -g https://github.com/openclaw/openclaw",
            },
        ],
        "install_guide": """
## Install OpenClaw

OpenClaw is a powerful AI agent focused on code generation and task automation.

### Option 1: npm install
```bash
npm install -g openclaw
```

### Option 2: Install from GitHub (recommended)
```bash
npm install -g https://github.com/openclaw/openclaw
```

### Verify installation
After installation, run the following command to confirm:
```bash
openclaw --version
```
""",
    },
    "langgraph": {
        "command": "uv",
        "package": "uv",
        "install_methods": [
            {
                "method": "curl",
                "command": "curl -LsSf https://astral.sh/uv/install.sh | sh",
            },
            {"method": "pip", "command": "pip install uv"},
        ],
        "install_guide": """
## Install uv (required by LangGraph)

uv is a fast Python package manager. The LangGraph Agent requires it to manage dependencies.

### Recommended (official script)
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### Alternative (pip)
```bash
pip install uv
```

### Verify installation
```bash
uv --version
```
""",
    },
    "aider": {
        "command": "aider",
        "package": "aider-chat",
        "install_methods": [
            {"method": "pipx", "command": "pipx install aider-chat"},
            {"method": "pip", "command": "pip install aider-chat"},
        ],
        "install_guide": """
## Install Aider

Aider is an AI pair programming assistant.

### Recommended (pipx)
```bash
pipx install aider-chat
```

### Alternative (pip)
```bash
pip install aider-chat
```

### Verify installation
```bash
aider --version
```
""",
    },
    "codex_cli": {
        "command": "codex",
        "package": "codex-cli",
        "install_methods": [
            {"method": "npm", "command": "npm install -g @openai/codex"},
        ],
        "install_guide": """
## Install Codex CLI

OpenAI Codex CLI is an AI coding agent.

### Install via npm
```bash
npm install -g @openai/codex
```

### Verify installation
```bash
codex --version
```
""",
    },
    "claude_code_cli": {
        "command": "claude",
        "package": "claude-code",
        "install_methods": [
            {"method": "npm", "command": "npm install -g @anthropic-ai/claude-code"},
        ],
        "install_guide": """
## Install Claude Code CLI

Anthropic Claude Code CLI is an AI coding agent.

### Install via npm
```bash
npm install -g @anthropic-ai/claude-code
```

### Verify installation
```bash
claude --version
```
""",
    },
    "gemini_cli": {
        "command": "gemini",
        "package": "@anthropic-ai/gemini-cli",
        "install_methods": [
            {"method": "npm", "command": "npm install -g @anthropic-ai/gemini-cli"},
        ],
        "install_guide": """
## Install Gemini CLI

Google Gemini CLI is an AI coding agent.

### Install via npm
```bash
npm install -g @google/gemini-cli
```

### Verify installation
```bash
gemini --version
```
""",
    },
}


# ============================================================
# Models
# ============================================================
