---
playbook_code: ai_seo_pipeline
version: 1.0.0
capability_code: openseo
name: AI SEO Complete Optimization Pipeline
description: End-to-end AI SEO optimization pipeline: semantic optimization → structured data → E-E-A-T → engine-specific optimization → save. Automatically selects optimization strategies based on target engines. Supports single or batch processing.
tags:
  - ai-seo
  - optimization
  - pipeline
  - semantic-search
  - structured-data
  - eeat

kind: user_workflow
interaction_mode:
  - conversational
  - needs_review
visible_in:
  - workspace_tools_panel
  - workspace_playbook_menu

required_tools:
  - openseo.read_obsidian_vault
  - openseo.generate_claims_to_sources
  - openseo.generate_ai_seo_scorecard
  - openseo.save_to_markdown
  - core_llm.generate
  - core_llm.structured_extract

language_strategy: model_native
locale: en
supported_locales:
  - zh-TW
  - en
default_locale: en
auto_localize: true

entry_agent_type: consultant
icon: 🤖
---

# AI SEO Complete Optimization Pipeline

## Goal

Provide an end-to-end AI search engine optimization pipeline that automatically selects optimization strategies based on target engines and generates optimized content that complies with the AI SEO Common Contract.

## Execution Flow

### Phase 1: Parse Content Source

Automatically identify and load content based on `content_source` format:
- `obsidian://vault/path/to/note.md` → Read Obsidian vault
- `workspace://workspace_id/content_id` → Read Mindscape workspace content
- `url://https://example.com/article` → Fetch web page content
- `pasted_text` → Use directly pasted text

### Phase 2: Semantic Optimization (semantic_optimization)

Unless skipped in `skip_steps`:
- Extract keywords and entities
- Build topic clusters
- Optimize semantic search score
- Improve content semantic understanding

### Phase 3: Structured Data Optimization (structured_data_optimization)

Unless skipped in `skip_steps`:
- Generate Schema.org JSON-LD structured data
- Select appropriate schema based on `content_type` (Article, FAQ, HowTo, Product, etc.)
- Ensure structured data meets target engine requirements

### Phase 4: E-E-A-T Optimization (eeat_optimization)

Unless skipped in `skip_steps`:
- Validate and optimize author information (`author_profile_id`)
- Validate and optimize brand entity (`brand_entity_id`)
- Enhance content expertise, authoritativeness, and trustworthiness

### Phase 5: Engine-Specific Optimization (automatically selected based on target_engines)

#### SGE Optimization (sge_optimization)
- Executed when `target_engines` includes `"sge"`
- Optimize conversational structure
- Generate step-by-step content
- Enhance FAQ and HowTo schema

#### Perplexity Optimization (perplexity_optimization)
- Executed when `target_engines` includes `"perplexity"`
- Generate `claims_to_sources` mapping (when `citation_mode != "none"`)
- Strengthen citations and factuality
- Ensure source traceability

#### Bing Chat / You.com Optimization
- When `target_engines` includes `"bing_chat"` or `"you_com"`
- Currently falls back to generic (only runs semantic/structured/eeat)
- Can be extended with dedicated optimization steps in the future

### Phase 6: Merge Optimization Results (merge_optimizations)

Merge outputs from all optimization steps:
- **content_md**: Later playbook overwrites earlier ones
- **schema_jsonld**: Union after deduplication by @type
- **claims_to_sources**: Merge by claim_id; deduplicate sources for same claim_id, retain highest confidence

### Phase 7: Generate Scorecard (generate_scorecard)

Generate complete AI SEO scorecard:
- semantic_score
- structured_data_score
- eeat_score
- citation_coverage (when `citation_mode != "none"`)
- overall_score (required for pipeline final output)

### Phase 8: Prepare Metadata (prepare_metadata)

Prepare complete metadata object:
- continuity_graph (wikilink relationships extracted from Obsidian)
- seo_scores (SEO score history)
- optimization_history (optimization history)
- version (version number)
- trace_id (trace ID)

### Phase 9: Save to Markdown (save_to_markdown)

Save to corresponding directory based on `content_status`:
- `draft` → `openseo/generated/draft/`
- `in_review` → `openseo/generated/in_review/`
- `published` → `openseo/generated/published/`
- `archived` → `openseo/generated/archived/`

Also save metadata to `openseo/metadata/` directory.

## Batch Processing Mode

When `run_mode=batch`:
- Process multiple `content_source` items
- Generate independent output for each item
- Return batch summary (`batch_summary`) including:
  - total, success, failed, skipped
  - avg_score
  - errors[]

## Output Format

Complies with AI SEO Common Contract:
- `content_md`: Optimized Markdown content (with frontmatter)
- `title`: Article title
- `meta_description`: Meta description
- `claims_to_sources`: Claim-to-source mapping (when `citation_mode != "none"`)
- `schema_jsonld`: Schema.org JSON-LD structured data
- `scorecard`: SEO scorecard
- `metadata`: Complete metadata (when `save_metadata=true`)
- `trace_id`: Trace ID
- `result_status`: Processing result status (success/error/skipped)

## Mindscape Event Governance Alignment

Output flags:
- `is_artifact=true`: Reusable, comparable stable artifact
- `has_structured_output=true`: Contains structured output
- `should_embed=true`: Only true when `content_status=published`
- `is_final=true`: True when `content_status=published` or `archived`

## Usage Examples

### Single Item Processing

```yaml
content_source: "obsidian://vault/path/to/note.md"
content_type: "article"
target_engines: ["sge", "perplexity"]
citation_mode: "strict"
content_status: "draft"
output_path: "openseo/generated"
```

### Batch Processing

```yaml
run_mode: "batch"
content_sources:
  - "obsidian://vault/path/to/note1.md"
  - "obsidian://vault/path/to/note2.md"
content_type: "article"
target_engines: ["generic"]
citation_mode: "light"
content_status: "draft"
```

## Notes

1. **Content Source Format**: Must conform to `obsidian://`, `workspace://`, `url://`, or `pasted_text` format
2. **Skip Steps**: Use `skip_steps` to skip specific optimization steps (for debugging or partial optimization)
3. **Citation Mode**: When `citation_mode=strict`, `claims_to_sources` must include `anchor` information
4. **Batch Processing**: In batch mode, each item has independent `trace_id` and `result_status`

