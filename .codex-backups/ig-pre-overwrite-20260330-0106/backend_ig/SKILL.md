# Instagram Pack

> Instagram content generation, management, and workflow automation capabilities

---

## What This Pack Can Do

| Category | Skills |
|----------|--------|
| **Content Creation** | Generate posts, apply templates, batch processing |
| **Content Management** | Hashtag groups, asset management, series tracking |
| **Analytics** | Account snapshot, following analysis, metrics backfill |
| **Publishing** | Validate media, publish posts, sync content |
| **Quality Control** | Content compliance check, frontmatter validation, review workflow |

---

## Skills (Capabilities)

### Content Creation Skills

| Skill | Description |
|-------|-------------|
| `ig.post_generation` | Generate Instagram posts with AI-powered style matching |
| `ig.template_engine` | Apply templates for carousel, reel, and story formats |
| `ig.batch_processor` | Process multiple posts in batch operations |

### Content Management Skills

| Skill | Description |
|-------|-------------|
| `ig.hashtag_manager` | Manage hashtag groups (brand, theme, campaign) |
| `ig.asset_manager` | Validate and organize media assets |
| `ig.series_manager` | Track content series and post navigation |
| `ig.vault_structure` | Initialize and validate workspace structure |

### Analytics Skills

| Skill | Description |
|-------|-------------|
| `ig.analyze_following` | Extract and analyze Instagram following list |
| `ig.capture_account_snapshot` | Capture account profile snapshot (bio, stats, avatar) |
| `ig.metrics_backfill` | Backfill post-publication metrics |

### Publishing Skills

| Skill | Description |
|-------|-------------|
| `ig.sync_content` | Fetch posts, reels, stories from Instagram |
| `ig.publish_content` | Publish content to Instagram |
| `ig.validate_media` | Validate media format and size limits |

### Quality Control Skills

| Skill | Description |
|-------|-------------|
| `ig.content_checker` | Check compliance (medical claims, copyright, brand tone) |
| `ig.frontmatter_validator` | Validate against Unified Frontmatter Schema |
| `ig.review_system` | Manage review workflow and changelog |

---

## Tools Included

| Tool | Purpose |
|------|---------|
| `ig_post_style_analyzer` | Analyze reference image and generate design recommendations |
| `ig_following_analyzer` | Browser automation for following list extraction |
| `ig_account_snapshot` | Browser automation for account profile capture |
| `ig_data_fetcher` | Fetch content from Instagram API |
| `ig_publisher` | Publish content to Instagram |

---

## UI Components

| Component | Description |
|-----------|-------------|
| **IG Workbench** | Unified control panel with three-panel layout |
| **IG Grid View** | Posts grid view and timeline view |
| **Following Analyzer** | Real-time progress and background execution UI |

---

## Requirements

- **Mindscape AI Local-Core** v0.9.0+
- **Optional**: Site-Hub Integration (for OAuth publishing)
- **Optional**: Playwright (for browser automation features)

---

## Installation

```bash
# Package the capability
cd mindscape-ai-cloud
python3 scripts/package_capability.py ig

# Install to Local-Core
curl -X POST http://localhost:8200/api/v1/capability-packs/install-from-file \
  -F "file=@ig.mindpack"
```

---

## Quick Start

1. **Initialize workspace structure**
   ```
   Run playbook: ig_vault_structure_manager
   ```

2. **Generate your first post**
   ```
   Run playbook: ig_post_generation
   Input: topic, style reference, hashtag groups
   ```

3. **Validate and export**
   ```
   Run playbook: ig_content_checker → ig_export_pack_generator
   ```

---

## Related Packs

- `unsplash` — Stock photo search
- `mindscape_cloud_integration` — Instagram OAuth setup
- `brand_identity` — Brand guidelines and tone
