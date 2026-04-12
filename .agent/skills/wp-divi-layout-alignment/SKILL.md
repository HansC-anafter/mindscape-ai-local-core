---
name: wp-divi-layout-alignment
description: Evidence-based workflow for repairing imported Divi or Divi Pixel layouts that do not visually match the source demo. Enforces local-first WordPress repair, template isolation, asset localization, and ordered rollout.
---

# WordPress Divi Layout Alignment

## Core Rule

**Never repair a production WordPress layout by guessing which CSS file is missing.**

Imported Divi layouts must be repaired in this order:

1. fingerprint the actual runtime stack
2. isolate page body vs Theme Builder/template influence
3. localize external demo assets
4. verify version compatibility
5. identify site-specific theme or plugin overlays
6. only then implement the minimum viable fix locally

If a production site is involved, all content or template mutations must follow the local-first sync workflow. Do not write remote database state before local validation.

---

## When To Use This Skill

Use this skill when:

- a Divi or Divi Pixel layout was imported and does not match the vendor demo
- a WordPress page looks correct in the importer preview but wrong on the live site
- an imported layout is being wrapped by an unexpected header, footer, or global template
- imported sections still hotlink to external demo assets
- the site uses a child theme or custom plugins that may override the imported layout

Do not use this skill for generic CSS bugs unrelated to Divi layouts.

---

## Non-Negotiable Constraints

### 1. Local-First Repair Boundary

For any production WordPress site:

- read-only runtime inspection on production is allowed
- content, template, or database writes must be prepared and validated in local-first workflow first
- if data or template state may be overwritten, require an explicit backup step before implementation

### 2. Evidence Before Fix

Every claim about the layout mismatch must be backed by one of:

- page HTML output
- enqueued CSS or JS handles
- active theme or plugin versions
- Theme Builder assignment data
- external asset URLs still present in rendered output
- child theme or plugin source code

### 3. Page vs Template Separation

Never say "the imported layout is wrong" until you have separated:

- page body CSS
- Theme Builder header/footer/body template CSS
- child theme CSS or JS
- site-specific plugins that rewrite or proxy assets

---

## Mandatory Workflow

### Phase 0: Site Fingerprint

Collect the exact runtime fingerprint before planning a fix.

Required evidence:

- page URL and page ID
- active parent theme and child theme
- Divi version
- Divi Pixel version
- active custom plugins related to layout, caching, asset rewriting, or demo import
- body classes from rendered HTML
- dynamic CSS handles rendered for the page

Minimum command set:

```bash
curl -sS https://example.com/page/
wp option get page_on_front --allow-root
wp theme list --status=active --allow-root
wp plugin list --status=active --allow-root
```

Record whether the page is using:

- `et_pb_pagebuilder_layout`
- `et-tb-has-template`
- `et-tb-has-header`
- `et-tb-has-footer`
- child theme body classes

### Phase 1: Template Isolation

Determine whether the mismatch is caused by the page body or by Theme Builder.

Required checks:

1. identify page-level dynamic CSS handle
2. identify deferred Theme Builder CSS handles
3. map those handles back to actual `et_header_layout`, `et_footer_layout`, or template posts
4. compare page modified time vs template modified time

Decision rule:

- if template CSS exists and template timestamps are newer than the page, treat template interference as first-class cause
- if only page CSS exists, continue with page-level diagnosis

### Phase 2: Demo Asset Audit

Count and classify every external demo asset still referenced by rendered HTML.

Classify by:

- source demo pack, for example `club`, `portfolio`, `yoga`
- asset type: image, SVG, background image, JS data attribute
- whether the site has a proxy or rewrite plugin that already supports that demo family

Required output:

```text
Total external demo assets: N
- club: X
- portfolio: Y
- yoga: Z
```

If the site has a demo proxy or CORS fix, verify the exact patterns it supports. Do not assume a `demo.divi-pixel.com` rewrite is generic; many site fixes only match one demo path.

### Phase 3: Version Compatibility Matrix

Compare vendor demo stack against the target site.

Minimum matrix:

| Layer | Demo | Target Site | Risk |
|---|---|---|---|
| Divi | | | |
| Divi Pixel | | | |
| Child Theme | none / custom | | |
| Cache Layer | | | |

Prioritize this as a root cause when:

- Divi major versions differ
- Divi Pixel minor versions differ in modules used on the page

### Phase 4: Site-Specific Overlay Audit

Inspect the child theme and custom plugins for code that can alter imported layouts.

Audit for:

- unconditional `wp_enqueue_style`
- unconditional `wp_enqueue_script`
- host-based project CSS or JS loaders
- asset proxy rewrites
- DOM mutation scripts
- animation or parallax scripts attached globally

Required conclusion format:

```text
Overlay O1: [component] alters [scope] via [file:line]
Overlay O2: [component] rewrites only [demo family], leaving [other demo family] untouched
```

### Phase 5: Ordered Repair Design

Write the repair in the smallest safe tranche.

Repair order must be:

1. stop wrong template wrapping
2. fix external demo asset handling
3. align versions or explicitly document incompatibility
4. scope site-specific CSS or JS overlays more narrowly
5. regenerate or invalidate dynamic CSS caches only after the above are in place

Do not start by clearing caches. Cache invalidation without correcting the upstream cause wastes time and makes evidence stale.

### Phase 6: Local Implementation

Before any write:

- confirm correct repo
- confirm the change belongs in code, not direct production content edits
- use explicit file edits only

Examples of safe first-tranche code fixes:

- extending a demo asset rewrite plugin to support additional demo families
- scoping child theme assets to a smaller host or page set
- documenting and staging template assignment corrections in a local workflow doc

Examples of unsafe first-tranche actions:

- editing production Theme Builder assignments without local validation
- bulk search-and-replace against live WordPress content
- clearing or regenerating caches without a recorded baseline

### Phase 7: Validation

Validation must prove the visual alignment moved in the right direction.

Required checks:

- rendered HTML no longer references unsupported external demo assets
- page and template CSS handles match expected ownership
- page body still loads required Divi Pixel assets
- screenshots or structured HTML diffs confirm the repaired section changed

If the repair affects production content or templates, include rollback instructions and the exact backup location.

---

## Problem Prioritization

Use this priority order unless evidence contradicts it:

| Priority | Problem Type | Why it comes first |
|---|---|---|
| P1 | Wrong Theme Builder wrapper | It can invalidate every page-level style comparison |
| P2 | Unsupported external demo assets | Missing backgrounds or SVGs make the page look broken even if CSS is correct |
| P3 | Divi / Divi Pixel version skew | Module rendering can differ structurally |
| P4 | Child theme or plugin overlays | Site-specific styling can distort otherwise valid imports |
| P5 | Cache artifacts | Usually derivative, not root cause |

---

## Required Deliverables

Every repair task using this skill should produce:

1. a concise evidence summary
2. a numbered problem list
3. the first safe repair tranche
4. verification commands
5. the next deferred repair tranche, if any

If implementation is blocked by production-only template edits, say so explicitly and stop before guessing.

---

## Prohibited Patterns

### 1. CSS Cargo Culting

**WRONG**: "It must be missing `style.css`; enqueue more CSS."

**RIGHT**: Prove which layer owns the mismatch before adding or changing assets.

### 2. Page-Only Diagnosis

**WRONG**: Compare the imported page body to the vendor demo while ignoring Theme Builder header/footer wrappers.

**RIGHT**: Identify every `tb-*` CSS handle and template post involved.

### 3. Generic Demo Rewrite Assumption

**WRONG**: "The proxy already handles demo.divi-pixel.com."

**RIGHT**: Verify the exact regex path. Many fixes only support one demo family such as `/yoga/`.

### 4. Production-First Template Editing

**WRONG**: Change live Theme Builder assignments to see what happens.

**RIGHT**: prepare the repair locally, document the intended template change, then push through the approved workflow.

### 5. Cache-First Debugging

**WRONG**: Clear WP Rocket and Divi caches before establishing the root cause.

**RIGHT**: capture the evidence first, then invalidate caches only after the underlying mismatch is corrected.

---

## Pre-Delivery Checklist

- [ ] The page fingerprint is recorded
- [ ] Theme Builder influence is either proven or ruled out
- [ ] External demo asset counts are recorded by source family
- [ ] Divi and Divi Pixel versions are compared against the demo
- [ ] Child theme and custom plugin overlays were audited
- [ ] The first repair tranche is local-safe and minimal
- [ ] Verification steps are explicit
- [ ] No production write has been performed without local-first workflow
