# Rollout Phases And Runtime Adoption

## Purpose

Provide the runtime-side adoption sequence for introducing the Addressable
Object Layer without a mega-branch rewrite.

## Delivery Strategy

Ship this as a phased platform evolution:

- define contracts first
- index only a small set of object kinds first
- onboard a limited number of owner packs
- add richer UI surfaces only after the object layer is stable

## P0

Target:

- `ObjectRef` and resolver contract
- install-time object catalog
- meeting attachment API
- first object kinds:
  - `ig.reference`
  - `pd.storyboard`
  - `pd.storyboard_scene`
  - `mms.run`
  - `mms.scene`
  - `pps.handoff`

## P1

Target:

- contextual action popover
- proposal/materialization APIs
- graph-aware object projections
- first cross-pack scenarios:
  - IG ref to storyboard expansion
  - MMS scene to PD review proposal

## P2

Target:

- richer object relations and lineage
- multi-object meeting invocation
- yogacoach object onboarding
- pack-authored meeting projections/materializers at scale

## P3

Target:

- advanced selection capture
- host-level overlay targeting where needed
- reusable review, compare, and governance surfaces

## Verification Themes

- no direct cloud-source dependency from Local-Core runtime
- no duplicate owner truth introduced by projections
- all canonical writebacks remain explicit and auditable
