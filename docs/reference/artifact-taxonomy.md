# Artifact Taxonomy

This page defines the public-safe artifact names used across the README, architecture docs, demo gallery, and use-case deep dives.

The goal is simple:

- readers should understand the artifact first
- pack names should stay secondary
- status words should remain consistent across every demo page

## Core Artifact Names

| Public-safe name | What it means | What not to claim |
| --- | --- | --- |
| `TaskIR` | The bounded control-plane artifact that says what work should happen and in what execution context | Do not describe it as a spatial planning artifact |
| `SpatialSchedulingIR` | The bounded planning artifact that describes spatial/world execution intent | Do not describe it as a provider-native runtime payload |
| `World summary` | The bounded continuity record that tells the operator what the world currently remembers about the run | Do not confuse it with raw runtime state or provider request bodies |
| `World card` | A prompt-safe or operator-safe projection of the current world summary | Do not treat it as a complete debug dump |
| `Preview mesh` | A reviewable, inspectable preview geometry output, often candidate-grade rather than final-grade | Do not market it as production-ready reconstruction |
| `Scene package` | A reusable scene-side artifact that can be handed to downstream consumers | Do not claim every downstream import lane is already closed |
| `Operator handoff manifest` | The bounded record that ties `meeting_id`, `task_id`, `schedule_id`, artifact refs, and receipt refs together | Do not replace it with manual path copying |
| `Downstream consumer receipt` | The first pack-facing receipt that proves the schedule was actually consumed | Do not confuse it with a final quality guarantee |
| `Stronger consumer receipt` | A receipt from a second, stronger consumer lane that reuses the same schedule spine | Do not present it as a central schema change |
| `Stable-ID spine` | The traceable identity path across meeting, schedule, summary, handoff, and receipts | Do not rely on manual file-path transcription when this should exist |

## Status Words

Use these words consistently across public docs.

| Status word | Use when | Do not use when |
| --- | --- | --- |
| `preview` | The output is inspectable and useful for operator review | The lane is only hypothetical |
| `candidate` | The lane has meaningful evidence but is not a final quality guarantee | The lane is already a stable production claim |
| `fallback` | The degraded path stays bounded and explainable when the stronger path is unavailable | The output is equivalent to the primary lane |
| `closed milestone` | The acceptance gate is genuinely closed with real receipts and supporting evidence | Only the host-side schema or synthetic smoke exists |
| `active productization track` | The lane is being documented and shaped into a public story, but not all evidence is landed yet | The lane is already closed |

## Naming Rules

1. First-layer headings should prefer artifact or workflow names over pack names.
2. Pack names belong in implementation notes, not public titles.
3. If a page uses `preview`, it must also explain what that preview does not prove.
4. If a page uses `candidate`, it must include a current status note.
5. If a page mentions a stronger backend, it must still preserve the same stable-ID story.

## Minimal Public Demo Bundle

When a public demo claims a bounded spatial/world story, the minimum readable bundle should include:

- one plain-language input or scenario statement
- one artifact or summary excerpt
- one operator-facing explanation of what was handed off
- one receipt or evidence pointer
- one honest statement about what remains outside the claim

## Related Docs

- [Demo Gallery](../demo-gallery/README.md)
- [Use Case Gallery](../use-cases/README.md)
- [Spatial Runtime Planning](../core-architecture/spatial-runtime-planning.md)
- [Glossary](../getting-started/glossary.md)
