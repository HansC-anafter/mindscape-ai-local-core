# Quick Start Guide

Welcome to **Mindscape AI Local Core**! This guide will help you get started quickly.

## Prerequisites

Before starting, make sure you have:

1. ✅ Installed Mindscape AI Local Core (see [Installation Guide](./installation.md))
2. ✅ Configured at least one LLM API key (OpenAI, Anthropic, or Google Vertex AI)
3. ✅ Started the backend server (`uvicorn app.main:app --reload`)
4. ✅ (Optional) Started the frontend (`npm run dev` in `web-console/`)

## First Steps

### 1. Access the Web Interface

Open your browser and navigate to:
- **Frontend**: `http://localhost:3000` (if using web console)
- **API Docs**: `http://localhost:8000/docs` (FastAPI automatic documentation)

### 2. Create Your First Workspace

1. In the web interface, click "New Workspace" or use the API:
   ```bash
   curl -X POST "http://localhost:8000/api/v1/workspaces" \
     -H "Content-Type: application/json" \
     -d '{"name": "My First Workspace"}'
   ```

### 3. Send Your First Message

1. In the workspace, type a message in the chat interface
2. Mindscape AI will:
   - Extract intents from your message
   - Suggest relevant playbooks/workflows
   - Execute workflows automatically (if configured)

### 4. Explore Playbooks

Playbooks are multi-step workflows that can:
- Process files
- Generate content
- Organize information
- And more!

Try saying:
- "Summarize this document" (with a file attached)
- "Create a todo list for my project"
- "Extract key points from this text"

## Key Concepts

### Workspaces

A workspace is your personal AI assistant environment. Each workspace:
- Has its own conversation history
- Maintains its own timeline of activities
- Can have multiple playbooks running

### Intents

Intents are automatically extracted from your messages. They help Mindscape AI understand what you want to do.

### Playbooks

Playbooks are reusable workflows that can:
- Process files
- Generate content
- Organize information
- Execute multi-step tasks

### Timeline

The timeline shows:
- Your conversation history
- Playbook execution results
- File processing results
- Intent extraction results

## Next Steps

1. **Explore Playbooks**: Try different playbooks to see what they can do
2. **Upload Files**: Upload documents and see how Mindscape AI processes them
3. **Customize**: Configure settings and preferences
4. **Read Documentation**: Check out the [User Guides](../guides/) for more details

## Getting Help

- **Documentation**: See [Documentation Index](../../README.md)
- **Issues**: Open an issue on GitHub
- **FAQ**: Check [FAQ](../faq/README.md)

---

**Happy exploring!** 🚀

