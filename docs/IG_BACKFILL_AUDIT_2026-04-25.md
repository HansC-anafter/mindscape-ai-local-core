# IG Backfill Audit 2026-04-25

## Status

- Audit mode only.
- No live metadata writes were performed as part of this audit.
- No capability pack was deployed from this audit pass.
- A tentative source-only parser patch was tried locally and then reverted before this report; current source and live behavior remain unchanged.

## Scope

- Workspace: `bac7ce63-e768-454d-96f3-3a00e8e1df69`
- Population audited: latest `200` `COMPLETED` refs from live `ig_reference_catalog`, ordered by `validated_at DESC`
- Artifacts generated during audit:
  - `/tmp/ig_recent200.tsv`
  - `/tmp/ig_recent200_audit.json`

## Method

1. Queried live Postgres `ig_reference_catalog` for the latest `200` completed refs.
2. Loaded each ref's on-disk metadata under:
   - `/Volumes/OWC Ultra 4T/mindscape-ai-local-core-runtime/data/secrets/workspaces/bac7ce63-e768-454d-96f3-3a00e8e1df69/ig/references/...`
3. Flagged refs whose backfilled metadata contained obvious parser-token pollution, including:
   - object labels like `{`, `label`, `confidence`, `region`, `]`
   - list fields containing literal `[` / `{`
   - nested fields such as `hair.color = "{"`
   - material payloads collapsed into `material_type = "material_type"` or dict-string literals
4. Reproduced the same corruption against the current source parser using:
   - `capabilities/ig/models/vision_prose_salvage.py`
   - `capabilities/ig/models/vision_output_parser.py`

## Headline Finding

Out of the latest `200` completed refs, `10` show backfill corruption or partial structured-prose misparse.

- Severe corruption: `5`
- Moderate corruption: `5`

The problem is not "raw is empty". The affected refs all retain substantial `analysis_debug.raw_text`; the corruption happens during the fallback/backfill parse path.

## Affected Refs

### Severe

| Shortcode | Ref ID | Validated At (UTC) | Symptom |
| --- | --- | --- | --- |
| `DPNh8tVkmep` | `ref_59ab7ffb` | `2026-04-25 07:05:35` | `scene_summary="{"`; object labels include prompt/output-structure text |
| `DD4f8asSDf8` | `ref_12ab8293` | `2026-04-24 18:57:43` | object labels became `{`, `label`, `confidence`, `region`, `}`, `]`; list fields contain `[` |
| `DTU-oZok5gn` | `ref_7a9fbb3b` | `2026-04-24 16:27:14` | object labels include stray `]`; scene evidence polluted with `[` |
| `DFDDyIOBYOs` | `ref_efc41174` | `2026-04-24 11:20:26` | object labels became `{`, `label`, `confidence`, `region`, `}`, `]` |
| `DI1U3KeBr0y` | `ref_35e53948` | `2026-04-24 10:37:29` | object labels became `{`, `label`, `confidence`, `region`, `}`, `]` |

### Moderate

| Shortcode | Ref ID | Validated At (UTC) | Symptom |
| --- | --- | --- | --- |
| `CQaes1Xj_2B` | `ref_8a49d757` | `2026-04-25 06:16:50` | structured fields partially drifted (`environment.foreground_elements=["texture"]`, object label `light_source`) |
| `DUp3v_5Eu-A` | `ref_216416c5` | `2026-04-25 00:35:38` | `material.materials[0].material_type="material_type"` |
| `DThm2wyEirA` | `ref_dc289c81` | `2026-04-24 23:25:42` | `material.materials[0].material_type="material_type"` |
| `DUAc7N4ErDj` | `ref_30d50a79` | `2026-04-24 21:53:00` | `material.materials[0].material_type="material_type"` |
| `DSKTuDbD2Jv` | `ref_d9f5e9b8` | `2026-04-24 16:37:41` | `material.materials[0].material_type="material_type"` |

## Direct Evidence

### 1. User-supplied raw vs live metadata (`DD4f8asSDf8`)

Raw file contains a coherent inline object list and then later transitions into JSON construction:

- `/Users/shock/Downloads/vision_DD4f8asSDf8_raw.txt:55`
- `/Users/shock/Downloads/vision_DD4f8asSDf8_raw.txt:56`
- `/Users/shock/Downloads/vision_DD4f8asSDf8_raw.txt:158`
- `/Users/shock/Downloads/vision_DD4f8asSDf8_raw.txt:247`

Live metadata for the same ref shows token pollution instead of parsed values:

- `/Volumes/OWC Ultra 4T/mindscape-ai-local-core-runtime/data/secrets/workspaces/bac7ce63-e768-454d-96f3-3a00e8e1df69/ig/references/@attractive_hotness_girls/DD4f8asSDf8.json:53`
- `/Volumes/OWC Ultra 4T/mindscape-ai-local-core-runtime/data/secrets/workspaces/bac7ce63-e768-454d-96f3-3a00e8e1df69/ig/references/@attractive_hotness_girls/DD4f8asSDf8.json:58`
- `/Volumes/OWC Ultra 4T/mindscape-ai-local-core-runtime/data/secrets/workspaces/bac7ce63-e768-454d-96f3-3a00e8e1df69/ig/references/@attractive_hotness_girls/DD4f8asSDf8.json:192`
- `/Volumes/OWC Ultra 4T/mindscape-ai-local-core-runtime/data/secrets/workspaces/bac7ce63-e768-454d-96f3-3a00e8e1df69/ig/references/@attractive_hotness_girls/DD4f8asSDf8.json:202`

The ref was validated on:

- `/Volumes/OWC Ultra 4T/mindscape-ai-local-core-runtime/data/secrets/workspaces/bac7ce63-e768-454d-96f3-3a00e8e1df69/ig/references/@attractive_hotness_girls/DD4f8asSDf8.json:504`

### 2. Current parser reproduces the corruption on the same raw

Using the current source `salvage_structured_prose_payload(...)` against `/Users/shock/Downloads/vision_DD4f8asSDf8_raw.txt` reproduced:

- `scene_evidence_notes = ["["]`
- `object_labels = ["{", "label", "confidence", "region", "}", "]"]`
- `training_lane_hints = ["["]`
- `environment_foreground = ["["]`
- `hair.color = "{"`
- `material.materials[0].material_type = "["`

This proves the corruption is not only historical data drift; the current salvage code still reproduces the same failure mode.

### 3. Prompt/output scaffold contamination is present in other severe refs

For `DPNh8tVkmep`, the live `analysis_debug.raw_text` includes prompt/meta-output text such as:

- `Output ONLY the raw JSON object`
- `Return ONLY valid JSON with this structure`
- `Start your response with '{' immediately`

and then a top-level JSON block starts later in the same raw payload.

This was extracted directly from the live metadata during audit. The important point is that the salvage path is not stopping before prompt/output scaffolding or JSON examples.

### 4. Inline material dict-lists are misparsed even without full token pollution

Current source logic for materials does not parse inline dict/list literals before falling back to text splitting:

- `<capability-source-root>/capabilities/ig/models/vision_prose_salvage.py:676`
- `<capability-source-root>/capabilities/ig/models/vision_prose_salvage.py:708`

Synthetic reproduction during this audit:

Input:

```text
**Material:**
- materials: [{"material_type": "fabric", "surface_finish": "matte", "region": "top"}, {"material_type": "denim", "surface_finish": "textured", "region": "skirt"}] (visible clothing materials)
```

Output:

```text
[{'material_type': "{'material_type': 'fabric', 'surface_finish': 'matte', 'region': 'top'}", ...},
 {'material_type': "{'material_type': 'denim', 'surface_finish': 'textured', 'region': 'skirt'}", ...}]
```

This directly explains the moderate `material_type="material_type"` / dict-string corruption pattern.

## Writer Attribution

The corrupted refs do **not** currently prove a standalone repair-script write.

Direct live task history for the 10 affected refs shows:

- all `10` map to `pack_id = ig_analyze_pinned_reference`
- all `10` reached `status = succeeded`
- all `10` completed on `2026-04-24` or `2026-04-25`
- all `10` carry `error = Runtime execution returned None`

This strongly points to the main `ig_analyze_pinned_reference` fallback/backfill path, not `repair_failed_reference_salvage.py`.

Relevant code path:

- `_backfill(...)` is the path that validates/salvages raw output and writes metadata:
  - `<capability-source-root>/capabilities/ig/tools/ig_analyze_reference_pipeline.py:1062`
- It calls `analyze_vision_output(...)` on the captured raw text:
  - `<capability-source-root>/capabilities/ig/tools/ig_analyze_reference_pipeline.py:1115`
- It then writes `vision_description`, `training_annotations`, and `auto_tags` back into metadata:
  - `<capability-source-root>/capabilities/ig/tools/ig_analyze_reference_pipeline.py:1343`
  - `<capability-source-root>/capabilities/ig/tools/ig_analyze_reference_pipeline.py:1352`

Also note:

- `analysis_provenance.model_id` is written from `vision_result.get("model_id", "")`, so blank `model_id` is expected when this fallback path lacks a model id:
  - `<capability-source-root>/capabilities/ig/tools/ig_analyze_reference_pipeline.py:1359`
- `parse_mode` is not persisted into `analysis_provenance` by this path, so blank parse-mode in metadata is not enough to identify the writer.

## Root-Cause Assessment

### Primary defect: stop-line coverage is too narrow

Current stop logic:

- `<capability-source-root>/capabilities/ig/models/vision_prose_salvage.py:751`
- `<capability-source-root>/capabilities/ig/models/vision_prose_salvage.py:768`

What is missing from the stop conditions:

- `Let's construct the JSON`
- `Let's assemble the JSON`
- `Output ONLY the raw JSON object`
- `Return ONLY valid JSON with this structure`
- `Start your response with '{' immediately`
- a bare top-level `{`
- fenced ` ```json ` scaffolds

Consequence:

- salvage continues reading prompt-output scaffolding and/or partial JSON blocks
- section payloads get reset by quoted JSON headings
- list/array punctuation and field names are reinterpreted as user data

### Secondary defect: inline material literals are not parsed as literals

Current material salvage only handles:

- parenthetical text patterns like `fabric (top, sleeve)`
- generic comma/semicolon text splitting

It does **not** first parse inline dict/list literals the way hair/clothing already do.

Consequence:

- material payloads degrade into:
  - `material_type="material_type"`
  - dict-string literals stored as `material_type`

## Quantified Summary

From the audited `200` refs:

- suspicious/corrupted refs: `10`
- severe token pollution: `5`
- moderate structured misparse: `5`
- affected refs with blank `analysis_provenance.model_id`: `10/10`
- affected refs with blank persisted parse-mode: `10/10`

Additional marker distribution across the `10` affected refs:

- contains `Let's construct/assemble the JSON`: `4`
- contains `Output ONLY the raw JSON object`: `4`
- contains `Return ONLY valid JSON with this structure`: `1`
- contains top-level JSON start `\n{\n`: `6`

## Known False-Negative Under The Current Detector

The first-pass detector used in this audit is intentionally narrow: it catches token pollution such as `[` / `{` / `label` / `confidence` being written into metadata fields.

Ref `DMw6bNJyfwN` is a counterexample that does **not** trip those token-pollution rules, but is still structurally degraded.

- Analysis artifact:
  - `/Users/shock/Downloads/vision_DMw6bNJyfwN_analysis.md:43`
  - `/Users/shock/Downloads/vision_DMw6bNJyfwN_analysis.md:48`
  - `/Users/shock/Downloads/vision_DMw6bNJyfwN_analysis.md:49`
  - `/Users/shock/Downloads/vision_DMw6bNJyfwN_analysis.md:51`
- Live metadata:
  - `estimated_age_range` contains deliberation text instead of a normalized value:
    - `/Volumes/OWC Ultra 4T/mindscape-ai-local-core-runtime/data/secrets/workspaces/bac7ce63-e768-454d-96f3-3a00e8e1df69/ig/references/@university.tw/DMw6bNJyfwN.json:129`
  - `clothing` collapsed into `garment_type="garment"` and multi-item prose in `color`:
    - `/Volumes/OWC Ultra 4T/mindscape-ai-local-core-runtime/data/secrets/workspaces/bac7ce63-e768-454d-96f3-3a00e8e1df69/ig/references/@university.tw/DMw6bNJyfwN.json:143`
  - `coverage` fields are empty while the actual key/value payload is stuffed into `coverage_notes`:
    - `/Volumes/OWC Ultra 4T/mindscape-ai-local-core-runtime/data/secrets/workspaces/bac7ce63-e768-454d-96f3-3a00e8e1df69/ig/references/@university.tw/DMw6bNJyfwN.json:153`
  - `pose` fields are empty while the whole mapping is stuffed into `gesture`:
    - `/Volumes/OWC Ultra 4T/mindscape-ai-local-core-runtime/data/secrets/workspaces/bac7ce63-e768-454d-96f3-3a00e8e1df69/ig/references/@university.tw/DMw6bNJyfwN.json:165`

This means the current audit should be extended with a second detector family for:

- scalar fields containing deliberation phrases (`looks`, `let's say`, `or`)
- `coverage_notes` / `gesture` / `evidence_notes` that still contain embedded schema keys
- collapsed nested mappings where child fields are blank but the parent note contains `key: value` text

## Conclusion

This is not random tag drift and not "raw had no value".

The current evidence supports:

1. the latest corrupted refs were written by the **main `ig_analyze_pinned_reference` fallback/backfill path**
2. the fallback parser is still vulnerable today
3. the primary failure mode is **structured-prose salvage reading too far into prompt/output scaffold or JSON scaffold**
4. the secondary failure mode is **inline material dict-list coercion**

## Recommended Next Step Order

No changes were applied in this audit, but the safest remediation order is:

1. Fix parser stop-lines and inline material literal parsing in source.
2. Add regression tests covering:
   - `DD4f8asSDf8`-style `Let's construct the JSON` + partial JSON tail
   - prompt/output scaffold contamination (`Output ONLY...`, `Return ONLY valid JSON...`)
   - inline material dict-list literals with explanatory tails
3. Run a **dry-run** against at least these `10` refs first.
4. Verify corrected payloads against raw before any live apply.
5. Only then package/deploy and perform a targeted repair.
