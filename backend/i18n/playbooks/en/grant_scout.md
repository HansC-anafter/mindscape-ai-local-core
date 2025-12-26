---
playbook_code: grant_scout
version: 1.0.0
name: Grant Scout
description: Automatically discover and match suitable government grant programs for your project
tags:
  - grant
  - funding
  - government
  - application

kind: user_workflow
interaction_mode:
  - conversational
visible_in:
  - workspace_tools_panel
  - workspace_playbook_menu

required_tools:
  - grant_scout.index_grants
  - grant_scout.recall_candidates
  - grant_scout.match_grants
  - grant_scout.generate_draft
  - core_llm.structured_extract

language_strategy: model_native
locale: en
supported_locales:
  - zh-TW
  - en
default_locale: zh-TW
auto_localize: true

entry_agent_type: researcher
icon: 🔍
capability_code: grant_scout
---

# Grant Scout

## Objective

Help you automatically discover and match suitable government grant programs, and generate application strategies.

## Features

This Playbook supports three operations:

1. **Index Grants** (`action: index`)
   - Fetch latest grant program list from government open data platforms
   - Structure data and save to Grant Vault
   - Support multiple data sources (data.gov.tw, IRIX, etc.)

2. **Match Grants** (`action: match`)
   - Input your project description
   - Automatically match suitable grants
   - Check eligibility and rank recommendations
   - Provide strategy hints

3. **Generate Draft** (`action: draft`)
   - Generate application strategy card for specific grant
   - Output application outline and TODO list
   - Map evaluation criteria to required evidence

## Use Cases

- **Startups**: Find suitable R&D grants
- **SMEs**: Discover digital transformation grants
- **Research Institutions**: Match industry-academic collaboration programs

## Inputs

### Common Parameters
- `action`: Operation type - "index", "match", "draft" (required)
- `vault_path`: Grant Vault path (default: vault)

### Index Operation
- `sources`: Data source list (default: ["data.gov.tw"])

### Match Operation
- `user_input`: Project description (required)

### Draft Operation
- `grant_id`: Grant program ID (required)

## Outputs

### Index Operation
- `indexed_count`: Number of indexed programs
- `failed_count`: Number of failures
- `sources`: Indexed data sources
- `timestamp`: Indexing time

### Match Operation
- `matched_grants`: List of matched grants (with fit scores)
- `total_candidates`: Total candidate count
- `eligible_count`: Eligible grant count

### Draft Operation
- `strategy_card`: Application strategy card (key info & next actions)
- `outline`: Application outline
- `todos`: TODO list

## Example Usage

### 1. First Time: Index Grants

```yaml
inputs:
  action: "index"
  sources: ["data.gov.tw"]
```

Expected output:
- Indexing result (count, success/failure)
- YAML files in Grant Vault

### 2. Match Grants

```yaml
inputs:
  action: "match"
  user_input: "We are developing an AI-powered voice translation product. We have completed the prototype and are ready for market validation. The company was founded 2 years ago as a startup with 8 team members and a paid-in capital of 5 million."
```

Expected output:
- Top 10 suitable grants
- Fit score, match reasons, and gap info for each
- Strategy hints

### 3. Generate Draft

```yaml
inputs:
  action: "draft"
  grant_id: "moeaic-sbir-2025q1"
```

Expected output:
- Application strategy card (why suitable, what to prepare)
- Application outline (aligned with evaluation criteria)
- TODO list (documents, evidence, contacts)

## Workflow

### Index Flow
```
1. Call grant_scout.index_grants
2. Fetch data from API
3. Map to Grant Schema
4. Save to Grant Vault (YAML)
5. Update vector index
```

### Match Flow
```
1. Structure project info using LLM (core_llm.structured_extract)
2. Multi-path recall (grant_scout.recall_candidates)
   - Vector search (semantic similarity)
   - Keyword matching (exact match)
   - Rule matching (industry/stage)
3. Filter and rank (grant_scout.match_grants)
   - Hard constraint filtering (deadline, region, capital)
   - Eligibility checking (LLM)
   - Calculate fit score
4. Return top 10 recommendations
```

### Draft Flow
```
1. Load grant details
2. Check eligibility
3. Generate strategy card (key info, next actions)
4. Generate application outline (aligned with criteria)
5. Generate TODO list (documents, evidence, contacts)
```

## Notes

- Default Grant Vault path: `vault/`
- Recommended to run indexing weekly for updates
- Deep parsing requires LLM API with high token limits
- Data sources must comply with robots.txt and licensing terms

## Limitations

- Currently only supports data.gov.tw data source
- Deep parsing (PDF download) not yet implemented
- LLM eligibility checking is placeholder, needs Local-Core LLM service integration
- Vector search integration pending

## Future Enhancements

- Support more data sources (IRIX, ministry websites)
- Automatic deep parsing for popular grants
- Historical case learning
- Application progress tracking
- Multi-user collaborative editing

