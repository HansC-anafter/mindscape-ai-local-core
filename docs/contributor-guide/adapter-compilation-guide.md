# Mindscape Adapter Compilation Guide (ABI)

**Version**: 1.0.0
**Date**: 2025-12-22
**Status**: Public Contributor Guide

## Overview

This guide provides the **Application Binary Interface (ABI)** for integrating external tools into Mindscape. It defines the **3 deliverables + 1 validation** that contributors must provide to make their tools **readable, governable, and orchestratable** by Mindscape.

> **Mindscape doesn't compete in the tool market; we provide *Tool ABI + Pack Registry + Playbook Runtime*, enabling every tool you build to be governed, orchestrated, and collaboratively replayed.**

---

## The 3 Deliverables + 1 Validation

### Deliverable 1: Tool Adapter

Wrap your tool into one of three adapter levels (from easiest to most complete):

#### L0 — CLI Adapter (Lowest Barrier, Best for Vibe Coding)

**Requirement**: Your tool must be executable as a command that:
- Reads JSON from `stdin`
- Writes JSON to `stdout`
- Uses exit code to indicate success/failure (0 = success, non-zero = failure)

**Template**:

```bash
#!/bin/bash
# tool.sh - Your tool wrapper

# Read input from stdin
input=$(cat)

# Parse JSON (using jq or similar)
# Process your tool logic
# ...

# Output JSON to stdout
echo '{"result": "your_output", "status": "success"}'

# Exit code
exit 0  # or non-zero for failure
```

**Example**:

```python
#!/usr/bin/env python3
import json
import sys

# Read input from stdin
input_data = json.load(sys.stdin)

# Your tool logic
result = your_tool_function(input_data)

# Output JSON to stdout
print(json.dumps({
    "result": result,
    "status": "success"
}))

# Exit code
sys.exit(0)
```

**Mindscape Integration**:

```yaml
# tool.manifest.yaml
runtime:
  type: cli
  command: "python3 /path/to/your_tool.py"
  working_directory: "/path/to/workspace"
```

---

#### L1 — HTTP Adapter (Suitable for Deployed Services)

**Requirement**: Your tool must expose an HTTP endpoint:
- `POST /run` (or custom endpoint)
- Request body: JSON
- Response: JSON with `ok` / `error` status

**Template**:

```python
from flask import Flask, request, jsonify

app = Flask(__name__)

@app.route('/run', methods=['POST'])
def run_tool():
    try:
        input_data = request.json

        # Your tool logic
        result = your_tool_function(input_data)

        return jsonify({
            "ok": True,
            "result": result
        })
    except Exception as e:
        return jsonify({
            "ok": False,
            "error": str(e)
        }), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
```

**Mindscape Integration**:

```yaml
# tool.manifest.yaml
runtime:
  type: http
  endpoint: "http://localhost:8080/run"
  method: POST
  timeout: 30
```

---

#### L2 — MCP Server (Best Integration, Enters Tool Bus)

**Requirement**: Your tool must implement the [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) server interface.

**Benefits**:
- Tool discovery
- Schema validation
- Capability descriptions
- Native integration with Mindscape tool bus

**Template**:

```python
from mcp.server import Server
from mcp.types import Tool, TextContent

server = Server("your-tool-name")

@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="your_tool",
            description="Your tool description",
            inputSchema={
                "type": "object",
                "properties": {
                    "input": {"type": "string"}
                },
                "required": ["input"]
            }
        )
    ]

@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    if name == "your_tool":
        result = your_tool_function(arguments)
        return [TextContent(type="text", text=json.dumps(result))]
    raise ValueError(f"Unknown tool: {name}")

if __name__ == "__main__":
    server.run()
```

**Mindscape Integration**:

```yaml
# tool.manifest.yaml
runtime:
  type: mcp
  server_url: "http://localhost:8080"
  transport: stdio  # or sse, websocket
```

---

### Deliverable 2: Tool Manifest

Every tool must have a `tool.manifest.yaml` (or JSON) that enables:
- Playbook references
- Governance enforcement
- Runtime configuration

**Required Fields**:

```yaml
code: "your_namespace.your_tool"  # Unique identifier (e.g., "obsidian.outline.extract")
version: "1.0.0"
description: "Clear description of what your tool does"

# Input/Output Schema (JSON Schema)
input_schema:
  type: object
  properties:
    input_field:
      type: string
      description: "Field description"
  required:
    - input_field

output_schema:
  type: object
  properties:
    result:
      type: string
    status:
      type: string
  required:
    - result
    - status

# Runtime Configuration (NO SECRETS HERE)
runtime:
  type: cli | http | mcp
  # CLI
  command: "python3 /path/to/tool.py"
  working_directory: "/path/to/workspace"
  # OR HTTP
  endpoint: "http://localhost:8080/run"
  method: POST
  timeout: 30
  # OR MCP
  server_url: "http://localhost:8080"
  transport: stdio

# Governance (CRITICAL for controlled execution)
governance:
  side_effects: none | writes_files | network | modifies_remote
  risk_level: low | medium | high
  requires_confirmation: true | false
  idempotent: true | false
  max_execution_time: 30  # seconds
  allowed_workspaces: []  # empty = all workspaces
  requires_approval: false  # for high-risk tools
```

**Governance Field Explanations**:

- **`side_effects`**: What the tool does to the system
  - `none`: Pure computation, no side effects
  - `writes_files`: Writes to local filesystem
  - `network`: Makes network requests
  - `modifies_remote`: Modifies remote resources (databases, APIs, etc.)

- **`risk_level`**: Potential impact if misused
  - `low`: Safe, reversible operations
  - `medium`: May affect data but recoverable
  - `high`: Irreversible or critical operations

- **`requires_confirmation`**: Whether user confirmation is needed before execution

- **`idempotent`**: Whether running the tool multiple times produces the same result

**Example**:

```yaml
code: "obsidian.outline.extract"
version: "1.0.0"
description: "Extract outline structure from Obsidian markdown files"

input_schema:
  type: object
  properties:
    file_path:
      type: string
      description: "Path to Obsidian markdown file"
  required:
    - file_path

output_schema:
  type: object
  properties:
    outline:
      type: array
      items:
        type: object
        properties:
          level: {type: integer}
          title: {type: string}
    status: {type: string}
  required:
    - outline
    - status

runtime:
  type: cli
  command: "python3 /usr/local/bin/obsidian-outline-extract"
  working_directory: "/workspace"

governance:
  side_effects: none
  risk_level: low
  requires_confirmation: false
  idempotent: true
  max_execution_time: 10
```

---

### Deliverable 3: Playbook

Define a workflow that orchestrates multiple tools into a repeatable process.

**Format**: Markdown + YAML frontmatter

**Required Fields**:

```markdown
---
playbook_code: "your_playbook_name"
version: "1.0.0"
name: "Human-Readable Name"
description: "What this playbook does"

# Intent tags for discovery
intent_tags:
  - content-generation
  - seo
  - automation

# Required tools (must be available)
required_tools:
  - "namespace.tool1"
  - "namespace.tool2"

# Steps definition
steps:
  - id: "step1"
    tool: "namespace.tool1"
    inputs:
      input_field: "{{input.user_request}}"
    outputs:
      result1: "result"
    error_strategy: retry | terminate | skip
    retry_count: 3

  - id: "step2"
    tool: "namespace.tool2"
    inputs:
      input_field: "{{step.step1.result1}}"
    outputs:
      result2: "result"
    error_strategy: terminate

# Input schema
inputs:
  user_request:
    type: string
    required: true
    description: "User's request"

# Output schema
outputs:
  final_result:
    type: string
    source: "step.step2.result2"
---
```

**Step I/O Mapping**:

- **Input mapping**: Use `{{input.field_name}}` for playbook inputs, `{{step.step_id.output_field}}` for previous step outputs
- **Output mapping**: Define output field names and their sources

**Error Strategy**:

- **`retry`**: Retry the step on failure (with `retry_count`)
- **`terminate`**: Stop execution on failure
- **`skip`**: Skip the step and continue (use default values)

**Example**:

```markdown
---
playbook_code: "content_drafting"
version: "1.0.0"
name: "Content Drafting Workflow"
description: "Generate content draft from user requirements"

intent_tags:
  - content-generation
  - drafting

required_tools:
  - "core_llm.structured_extract"
  - "core_llm.generate"

steps:
  - id: "understand_requirements"
    tool: "core_llm.structured_extract"
    inputs:
      text: "{{input.user_request}}\n\nUnderstand content requirements."
      schema_description: "JSON object with target_audience, content_purpose, key_points"
    outputs:
      target_audience: "extracted_data.target_audience"
      content_purpose: "extracted_data.content_purpose"
      key_points: "extracted_data.key_points"
    error_strategy: terminate

  - id: "generate_draft"
    tool: "core_llm.generate"
    inputs:
      prompt: "Generate content based on:\nTarget Audience: {{step.understand_requirements.target_audience}}\nPurpose: {{step.understand_requirements.content_purpose}}\nKey Points: {{step.understand_requirements.key_points}}"
    outputs:
      draft_content: "text"
    error_strategy: retry
    retry_count: 2

inputs:
  user_request:
    type: string
    required: true
    description: "User's content request"

outputs:
  draft_content:
    type: string
    source: "step.generate_draft.draft_content"
---

# Content Drafting Workflow

This playbook generates content drafts based on user requirements.

## Steps

1. **Understand Requirements**: Extract structured information from user request
2. **Generate Draft**: Create content draft based on extracted requirements

## Usage

Provide a `user_request` describing the content you want to generate.
```

---

### Validation

Before submitting your pack, validate:

1. **Schema Validation**: Tool manifest and playbook must conform to schemas
2. **Compatibility Check**: Tools must be compatible with Mindscape core version
3. **Dependency Check**: All required tools must be available
4. **Governance Check**: Governance fields must be properly configured

**Validation Commands**:

```bash
# Validate tool manifest
mindscape tool validate tool.manifest.yaml

# Validate playbook
mindscape playbook validate playbook.md

# Validate pack
mindscape pack validate pack.yaml
```

---

## Pack Publishing

### What is a Pack?

A **Pack** is a distributable unit that combines:
- One or more **Capabilities** (containing tools, playbooks, schemas)
- **Pack manifest** (metadata, dependencies, versioning)

### Pack Structure

```
your-pack/
├── capabilities/
│   └── your_capability/
│       ├── manifest.yaml          # Capability manifest
│       ├── tools/
│       │   └── tool.manifest.yaml  # Tool manifests
│       └── playbooks/
│           ├── zh-TW/
│           │   └── playbook.md     # Playbook (Markdown)
│           └── specs/
│               └── playbook.json  # Playbook spec (JSON)
└── pack.yaml                       # Pack manifest
```

### Pack Manifest (Minimum Required Fields)

```yaml
name: "your-pack-name"
version: "1.0.0"
description: "What this pack does"
author: "Your Name"
license: "MIT"  # or your license
core_version_required: ">=1.0.0,<2.0.0"

capabilities:
  - code: "your_capability"
    version: "1.0.0"
    path: "capabilities/your_capability"
    manifest_path: "capabilities/your_capability/manifest.yaml"

tags:
  - content-generation
  - automation

created_at: "2025-12-22T00:00:00Z"
updated_at: "2025-12-22T00:00:00Z"
```

### Publishing Options

#### Option 1: Community Pack (Public)

**Repository**: `mindscape-ai-registry-community` (public repo)

**Process**:
1. Fork `mindscape-ai-registry-community`
2. Create your pack manifest in `packs/your-pack-name.yaml`
3. Submit a Pull Request
4. Community maintainers review and merge

**Access**:
- Anyone can search and install
- No authentication required
- Visible to all users

**Example**:

```bash
# Search community packs
mindscape pack search --registry community

# Install a community pack
mindscape pack install alice-seo --registry community
```

#### Option 2: Official Pack (Private/Commercial)

**Repository**: `mindscape-ai-registry` (private repo)

**Process**:
1. Contact Mindscape team for access
2. Submit pack manifest for review
3. Upon approval, pack is added to private registry

**Access**:
- Requires API token
- Cannot be searched (privacy protection)
- Direct install with known pack name + token

**Example**:

```bash
# Configure token (one-time)
mindscape pack config --token <your-token> --registry official

# Install a private pack (requires token)
mindscape pack install openseo --registry official
```

---

## IDE LLM Prompt Templates

### Template A: "Wrap Your Tool as Mindscape Tool"

Copy this prompt to your IDE LLM:

```
I have a tool that [describe what your tool does].

Please help me:
1. Create a tool adapter (choose L0 CLI / L1 HTTP / L2 MCP based on my tool)
2. Generate tool.manifest.yaml with:
   - Input/output schema (JSON Schema)
   - Runtime configuration
   - Governance fields (side_effects, risk_level, requires_confirmation, idempotent)
3. Provide an example input/output that can be tested

My tool details:
- Language: [Python/Node/Bash/etc.]
- Current interface: [CLI command / HTTP endpoint / MCP server / other]
- Input format: [describe]
- Output format: [describe]
- Side effects: [none/writes_files/network/modifies_remote]
- Risk level: [low/medium/high]
```

### Template B: "Create a Playbook Using These Tools"

Copy this prompt to your IDE LLM:

```
I have these tools:
- tool1: [description]
- tool2: [description]

Please create a Mindscape playbook (Markdown + YAML frontmatter) that:
1. Defines playbook_code, name, description
2. Lists required_tools
3. Defines steps with:
   - Tool references
   - Input/output mapping (using {{input.field}} and {{step.step_id.output_field}})
   - Error strategy (retry/terminate/skip)
4. Defines input/output schemas

Workflow description:
[Describe your workflow step by step]
```

---

## Complete Example: From Tool to Pack

### Step 1: Create Tool Adapter

**Tool**: Python script that extracts headings from markdown

```python
#!/usr/bin/env python3
# markdown-headings.py
import json
import sys
import re

input_data = json.load(sys.stdin)
file_path = input_data['file_path']

with open(file_path, 'r') as f:
    content = f.read()

headings = []
for line in content.split('\n'):
    match = re.match(r'^(#{1,6})\s+(.+)$', line)
    if match:
        level = len(match.group(1))
        title = match.group(2)
        headings.append({'level': level, 'title': title})

print(json.dumps({
    'headings': headings,
    'status': 'success'
}))
```

### Step 2: Create Tool Manifest

```yaml
# tool.manifest.yaml
code: "markdown.headings.extract"
version: "1.0.0"
description: "Extract heading structure from markdown files"

input_schema:
  type: object
  properties:
    file_path:
      type: string
      description: "Path to markdown file"
  required:
    - file_path

output_schema:
  type: object
  properties:
    headings:
      type: array
      items:
        type: object
        properties:
          level: {type: integer}
          title: {type: string}
    status: {type: string}
  required:
    - headings
    - status

runtime:
  type: cli
  command: "python3 /usr/local/bin/markdown-headings.py"
  working_directory: "/workspace"

governance:
  side_effects: none
  risk_level: low
  requires_confirmation: false
  idempotent: true
  max_execution_time: 5
```

### Step 3: Create Playbook

```markdown
---
playbook_code: "markdown_analyzer"
version: "1.0.0"
name: "Markdown Structure Analyzer"
description: "Analyze markdown file structure"

intent_tags:
  - analysis
  - markdown

required_tools:
  - "markdown.headings.extract"

steps:
  - id: "extract_headings"
    tool: "markdown.headings.extract"
    inputs:
      file_path: "{{input.file_path}}"
    outputs:
      headings: "headings"
    error_strategy: terminate

inputs:
  file_path:
    type: string
    required: true
    description: "Path to markdown file"

outputs:
  headings:
    type: array
    source: "step.extract_headings.headings"
---

# Markdown Structure Analyzer

This playbook extracts heading structure from markdown files.
```

### Step 4: Create Pack

```yaml
# pack.yaml
name: "markdown-tools"
version: "1.0.0"
description: "Markdown analysis and processing tools"
author: "Your Name"
license: "MIT"
core_version_required: ">=1.0.0,<2.0.0"

capabilities:
  - code: "markdown_tools"
    version: "1.0.0"
    path: "capabilities/markdown_tools"
    manifest_path: "capabilities/markdown_tools/manifest.yaml"

tags:
  - markdown
  - analysis

created_at: "2025-12-22T00:00:00Z"
updated_at: "2025-12-22T00:00:00Z"
```

### Step 5: Publish to Community Registry

1. Fork `mindscape-ai-registry-community`
2. Add `packs/markdown-tools.yaml`
3. Submit PR
4. After merge, users can install:

```bash
mindscape pack install markdown-tools --registry community
```

---

## Summary

**What Mindscape Provides**:
- **Tool ABI**: Three adapter levels (CLI/HTTP/MCP) for tool integration
- **Pack Registry**: Public (community) and private (official) distribution
- **Playbook Runtime**: Orchestration, governance, and traceability

**What Contributors Deliver**:
1. **Tool Adapter** (L0/L1/L2)
2. **Tool Manifest** (with governance fields)
3. **Playbook** (Markdown + YAML frontmatter)
4. **Validation** (schema, compatibility, dependencies)

**Result**: Every tool you build can be **governed, orchestrated, and collaboratively replayed** within Mindscape.

---

## Next Steps

1. **Read**: [Playbook Development Guide](../playbook-development/getting-started.md)
2. **Try**: Use IDE LLM templates to wrap your first tool
3. **Publish**: Submit your pack to community registry
4. **Iterate**: Build more tools and playbooks

## Support

- **Questions**: Open a discussion in `mindscape-ai-local-core`
- **Issues**: Report bugs or request features
- **Contributions**: Submit PRs to improve this guide


