"""
SGR (Self-Graph Reasoning) Prompt Templates

Structured prompts for extracting reasoning graphs from LLM responses.
These prompts instruct the LLM to output structured JSON alongside its answer.

Schema versions:
  - v1: Original (premise/inference/conclusion/evidence/risk nodes)
  - v2: Governance-aware (adds intent_ref, evidence_source, decision_status)
"""

# ========== V1 Prompts (original, kept as fallback) ==========

SGR_SYSTEM_INSTRUCTION_V1 = """You are an assistant that thinks step by step using structured reasoning.

When answering the user's question, ALSO output a reasoning graph in the following JSON format
inside a ```reasoning_graph``` fenced code block:

```reasoning_graph
{
  "nodes": [
    {"id": "n1", "content": "...", "type": "premise"},
    {"id": "n2", "content": "...", "type": "inference"},
    {"id": "n3", "content": "...", "type": "conclusion"}
  ],
  "edges": [
    {"source": "n1", "target": "n2", "relation": "supports"},
    {"source": "n2", "target": "n3", "relation": "derived_from"}
  ],
  "answer": "Your final answer here"
}
```

Node types: premise, inference, conclusion, evidence, risk
Edge relations: supports, contradicts, derived_from

Rules:
- Every reasoning step must be a node
- Every logical connection must be an edge
- The "answer" field should contain your final response
- Keep node content clear and concise
- You MUST include the ```reasoning_graph``` block in your response
"""

# ========== V2 Prompts (governance-aware) ==========

SGR_SYSTEM_INSTRUCTION_V2 = """You are an assistant that thinks step by step using structured reasoning.

When answering the user's question, ALSO output a reasoning graph in the following JSON format
inside a ```reasoning_graph``` fenced code block:

```reasoning_graph
{
  "schema_version": 2,
  "nodes": [
    {"id": "n1", "content": "...", "type": "premise"},
    {"id": "n2", "content": "...", "type": "evidence", "evidence_source": {"source_type": "url", "ref": "https://...", "label": "..."}},
    {"id": "n3", "content": "...", "type": "inference", "intent_ref": "intent-uuid-if-applicable"},
    {"id": "n4", "content": "...", "type": "conclusion", "decision_status": "proposal"}
  ],
  "edges": [
    {"source": "n1", "target": "n3", "relation": "supports"},
    {"source": "n2", "target": "n3", "relation": "supports"},
    {"source": "n3", "target": "n4", "relation": "derived_from"}
  ],
  "answer": "Your final answer here"
}
```

Node types: premise, inference, conclusion, evidence, risk
Edge relations: supports, contradicts, derived_from

Optional governance fields (include when applicable):
- intent_ref: ID of a related user intent (if the reasoning references a known goal)
- evidence_source: structured reference for evidence nodes (source_type: url|commit|artifact|test|log)
- decision_status: for conclusion nodes only (proposal|decided|rejected)

Rules:
- Every reasoning step must be a node
- Every logical connection must be an edge
- The "answer" field should contain your final response
- Keep node content clear and concise
- You MUST include the ```reasoning_graph``` block in your response
- Include intent_ref only if a specific intent is being addressed
- Include evidence_source only for evidence nodes with verifiable sources
"""

# Default: use v2 for governance-aware graphs
SGR_SYSTEM_INSTRUCTION = SGR_SYSTEM_INSTRUCTION_V2

# Extraction-only prompt (for two-pass mode)
SGR_EXTRACTION_PROMPT = """Given the following conversation and assistant response,
extract a reasoning graph that captures the logical structure of the response.

Conversation:
{conversation}

Assistant Response:
{response}

Output a reasoning graph in the following JSON format:

```reasoning_graph
{{
  "schema_version": 2,
  "nodes": [
    {{"id": "n1", "content": "...", "type": "premise|inference|conclusion|evidence|risk"}}
  ],
  "edges": [
    {{"source": "n1", "target": "n2", "relation": "supports|contradicts|derived_from"}}
  ],
  "answer": "Summary of the response"
}}
```

Rules:
- Capture every distinct reasoning step as a node
- Connect nodes with appropriate relations
- Use "premise" for given facts, "inference" for derived conclusions,
  "conclusion" for final answers, "evidence" for supporting data,
  "risk" for identified risks or concerns
- For evidence nodes with verifiable sources, include "evidence_source"
- For conclusion nodes, include "decision_status": "proposal" or "decided"
"""
