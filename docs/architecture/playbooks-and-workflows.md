---
title: Playbooks & Multi-step Workflow Architecture
status: public-draft-v1
last_updated: 2025-12-02
---

# Playbooks & Multi-step Workflow Architecture

This document explains how **Playbooks** and **multi-step workflows** work in Mindscape AI, using concepts that should feel familiar if you've used tools like LangChain, Claude Skills, GitHub Actions, or n8n.

It's meant for **open-source contributors and plugin authors**.
If you're looking for the low-level internal spec, see the internal doc
`MULTI_STEP_WORKFLOW_ARCHITECTURE_2025-12-01.md` (not published here).

---

## 1. Why we need Playbooks (instead of just prompts)

Large language models are good at answering questions, but:

- They **tend to "just answer"** instead of
  - planning multi-step tasks,
  - choosing the right tools,
  - wiring data between steps.
- Real-world tasks (content pipelines, data processing, system operations) are:
  - **multi-step**
  - **stateful**
  - often require **tools** and **APIs**, not just text.

Mindscape AI's answer is:

> **Playbooks**: reusable, inspectable workflows that the LLM can _invoke_,
> instead of reinventing a new ad-hoc plan on every prompt.

---

## 2. Mental model (high level)

At a high level, we separate two concerns:

1. **Talking to humans**
   – understanding what the user wants, explaining what will happen, summarizing results.

2. **Running workflows**
   – calling tools, processing files, updating indices, generating content.

We therefore use **two LLM roles** plus a workflow runtime:

```text
User
  ↓
Workspace LLM  (Mindscape Assistant)
  ↓  HandoffPlan (JSON)
Playbook LLM + Workflow Runtime
  ↓
Playbooks (playbook.run = md + json)
  ↓
Tools / APIs / Remote services
```

* **Workspace LLM**

  * "Front-of-house" assistant.
  * Chats with the user.
  * Decides whether a Playbook should be used.
  * Builds a structured `HandoffPlan` when a workflow is needed.

* **Playbook LLM + Workflow Runtime**

  * "Back-of-house" orchestrator.
  * Reads the `HandoffPlan`.
  * Chooses and executes `playbook.run` instances.
  * Manages step ordering, dependencies, and tool calls.

---

## 3. What is a Playbook?

A **Playbook** is a reusable workflow definition.
In Mindscape AI, **an executable playbook is always a pair**:

> `playbook.run = playbook.md + playbook.json`

This is similar in spirit to **Claude Skills** or **GitHub Actions**:

* a **human-readable description** (`playbook.md`)
* plus a **machine-readable execution spec** (`playbook.json`).

### 3.1 `playbook.md` – human-readable spec (for LLMs and humans)

`playbook.md` is a Markdown file with YAML frontmatter:

```markdown
---
playbook_code: pdf_ocr_and_index
kind: system_tool          # "user_workflow" | "system_tool"
interaction_mode:
  - silent                 # "silent" | "needs_review" | "conversational"
visible_in:
  - workspace_tools_panel  # workspace menu / tools panel / console-only
required_tools:
  - pdf_ocr
  - embedding
  - vector_store
---

# PDF OCR & Index

## Goal

Given one or more PDF files, perform OCR (if needed) and store
the resulting text + embeddings into the vector store.

## Steps (conceptual)

1. Normalize file list.
2. Run OCR where necessary.
3. Chunk text into passages.
4. Call embedding API.
5. Store embeddings + metadata into the vector DB.

## Examples

- Input: a research paper PDF
- Output: indexed document ready for RAG queries.
```

`playbook.md` is where you explain:

* **what** the playbook does
* **when** it should be used
* **roughly how** (conceptual steps, examples, edge cases)

It's written **for humans and LLMs**.
The system (plus the Playbook LLM) can then derive or refine the execution plan.

---

### 3.2 `playbook.json` – unified workflow spec (for the runtime)

`playbook.json` uses a **unified schema** that the workflow runtime understands.
While `playbook.md` is free-form, `playbook.json` is structured and consistent across all Playbooks.

A simplified example:

```jsonc
{
  "version": "1.0",
  "playbook_code": "pdf_ocr_and_index",
  "kind": "system_tool",
  "steps": [
    {
      "id": "normalize_files",
      "tool": "file_normalizer",
      "inputs": {
        "files": "{{input.pdf_files}}"
      },
      "outputs": {
        "normalized_files": "normalized_files"
      }
    },
    {
      "id": "run_ocr",
      "tool": "pdf_ocr",
      "inputs": {
        "files": "{{step.normalize_files.normalized_files}}"
      },
      "outputs": {
        "texts": "ocr_texts"
      }
    },
    {
      "id": "embed",
      "tool": "embedding",
      "inputs": {
        "texts": "{{step.run_ocr.ocr_texts}}"
      },
      "outputs": {
        "vector_ids": "vector_ids"
      }
    }
  ]
}
```

Key ideas:

* `playbook.json` is **runtime-friendly**:

  * each `step` has a `tool`, `inputs`, and `outputs`
  * inputs can reference:

    * `{{input.xxx}}` – playbook inputs
    * `{{step.<id>.<output_field>}}` – previous step outputs
    * `{{context.xxx}}` – external context (workspace, user, etc.)

* The schema is **shared across all Playbooks**, so:

  * we can build generic tooling (validators, visualizers, debuggers)
  * we can run workflows locally or remotely with the same format

Internally, `playbook.json` can be:

* hand-written (for precise control), or
* **LLM-assisted**, derived from `playbook.md` and some GUI inputs.

---

## 4. Two types of Playbooks

For contributors, it's useful to distinguish two categories:

### 4.1 User-facing Playbooks (`kind: user_workflow`)

These are Playbooks that **produce things for humans**:

* `content_drafting` – given some source text, produce IG posts / blog drafts
* `daily_planning` – given tasks and constraints, generate a daily plan
* `yt_script_from_paper` – convert a paper into a 5-minute YouTube script

Typical properties:

* `kind: user_workflow`
* `interaction_mode` often includes `conversational` or `needs_review`
* input / output are **user-visible** (shown in the UI, edited, reviewed)

### 4.2 System-tool Playbooks (`kind: system_tool`)

These Playbooks primarily serve the system:

* `pdf_ocr_and_index` – run OCR + embeddings + vector insert
* `sync_wordpress_posts` – pull posts, transform, embed, and index
* `workspace_health_check` – check MCP servers, DB connections, quotas

Typical properties:

* `kind: system_tool`
* often `interaction_mode: ["silent"]` and `visible_in: console_only`
* outputs are internal artifacts (logs, IDs, status), not end-user content

System-tool Playbooks are where we centralize:

* **indexing**
* **synchronization**
* **maintenance tasks**

User-facing Playbooks can chain them, e.g.:

> "From this PDF → run `pdf_ocr_and_index` → then generate 5 IG posts."

---

## 5. How Workspace LLM and Playbook LLM work together

The key contract between the two LLM roles is a JSON object we call **`HandoffPlan`**.

### 5.1 What Workspace LLM does

When a user asks for something non-trivial, the Workspace LLM:

1. chats / asks clarifying questions
2. decides whether to involve Playbooks
3. if yes, creates a `HandoffPlan`:

```jsonc
{
  "steps": [
    {
      "playbook_code": "pdf_ocr_and_index",
      "kind": "system_tool",
      "interaction_mode": ["silent"],
      "inputs": {
        "pdf_files": "$context.uploaded_files"
      }
    },
    {
      "playbook_code": "content_drafting",
      "kind": "user_workflow",
      "interaction_mode": ["conversational"],
      "inputs": {
        "source_content": "$previous.pdf_ocr_and_index.outputs.ocr_text",
        "content_type": "ig_post",
        "post_count": 5
      }
    }
  ],
  "context": {
    "workspace_id": "ws_123",
    "thread_id": "thread_456"
  }
}
```

Conceptually:

* Workspace LLM creates a **coarse plan**: *which Playbooks, in what order, with which high-level inputs*.
* It does **not** micro-manage internal steps of each Playbook – that's `playbook.json`'s job.

The `HandoffPlan` is then sent to the backend / Remote Agent Service, which invokes the Playbook LLM + workflow runtime.

### 5.2 What Playbook LLM + Workflow Runtime do

Given a `HandoffPlan`:

1. **Playbook LLM**:

   * validates and possibly refines the plan
   * ensures each step matches a known `playbook.run`
   * wires outputs → inputs using `playbook.json` and template rules

2. **Workflow Runtime**:

   * executes each `playbook.json` step, in order or DAG form
   * calls tools / APIs / MCP servers / remote clusters
   * records logs, partial results, error states

When the workflow is done (or at useful checkpoints), a **workflow result** is sent back to the Workspace thread:

* The next turn of Workspace LLM can:

  * summarize what happened;
  * present drafts (e.g. 5 IG posts);
  * ask the user whether to tweak or re-run.

---

## 6. Safety & UX principles

Mindscape AI follows a few simple rules:

1. **No hidden system changes**

   * The front-facing assistant will not silently change settings or mutate external systems.
   * Any dangerous or irreversible Playbook routes through explicit confirmation (`needs_review`).

2. **Playbooks are inspectable**

   * `playbook.md` is plain text in the repo.
   * `playbook.json` has a shared schema and lives next to it.
   * Contributors can see exactly what a Playbook is allowed to do.

3. **End users never see md/json**

   * End users only interact with:

     * a **Playbook card** (title + description)
     * a minimal **input form**
     * a **Run** button and progress display

   * The `md` & `json` layers are for authors / maintainers and the runtime.

---

## 7. Contributing a new Playbook

If you want to add a Playbook to Mindscape AI, the general workflow is:

1. **Create `playbook.md`**

   * Pick a unique `playbook_code`.
   * Choose `kind: user_workflow` or `system_tool`.
   * Write the goal, steps, examples, and edge cases.
   * Add a short description suitable for a UI card.

2. **Define or refine `playbook.json`**

   * Start from a template JSON.
   * Describe step ordering, tools, inputs, and outputs.
   * Use the shared schema so the runtime can execute it.
   * Optionally, use an LLM-assisted helper to draft the JSON from the md.

3. **Register it**

   * Add it to whatever registry / manifest the project uses
     (e.g. a `playbooks/registry.yaml` or similar).
   * Ensure `kind`, `interaction_mode`, `visible_in` are set correctly.

4. **Test it**

   * Run it from a CLI or dev UI with mock inputs.
   * Make sure:

     * tools are called with the right parameters;
     * outputs look reasonable;
     * error cases are handled.

5. **Wire it into the Workspace experience**

   * Optionally add hints so the Workspace LLM can discover it for relevant intents.
   * Or expose it as an explicit Playbook card in the workspace UI.

We'll gradually add helper scripts and templates to make authoring easier.

---

## 8. Relation to other parts of the system

Very briefly:

* **Memory & Intent Layer**

  * decides *what* the user is trying to achieve
  * may propose a draft `workflow_steps` list
  * feeds into the Workspace LLM, which builds the final `HandoffPlan`

* **Remote Agent Service / CRS-hub**

  * can host Playbook LLM + Workflow Runtime remotely
  * local Mindscape AI only needs to send `HandoffPlan` + context and receive results
  * allows heavy workflows (OCR, embeddings, indexing) to run on remote infra

---

## 9. Status & roadmap

Current status (v1, draft):

* The architecture and data models are defined:

  * `playbook.run = playbook.md + playbook.json`
  * `PlaybookKind`, `InteractionMode`, `VisibleIn`
  * `HandoffPlan` & `WorkflowStep` structure

* Initial Playbooks:

  * `pdf_ocr_and_index` (system_tool)
  * `content_drafting` / `daily_planning` (user_workflow)

* Early CLI / dev tooling is being built to:

  * execute a `HandoffPlan` end-to-end;
  * validate `playbook.json` schemas;
  * log and inspect workflow runs.

Planned:

* Helper commands for:

  * scaffolding new Playbooks (`playbook init`)
  * validating md/json pairs
  * running Playbooks locally with test data

* A simple web UI inside Mindscape AI to:

  * browse Playbooks
  * run them with minimal input
  * see logs and artifacts

---

If you'd like to contribute Playbooks or tooling around this system:

* open an issue with your use case,
* or submit a PR with a new `playbook.md` + `playbook.json` pair,
* or help improve the workflow runtime / validation layer.

We're especially interested in:

* high-quality content workflows (research → draft → publish),
* robust system-tool Playbooks (sync, indexing, health checks),
* and better developer ergonomics for authoring and debugging Playbooks.

