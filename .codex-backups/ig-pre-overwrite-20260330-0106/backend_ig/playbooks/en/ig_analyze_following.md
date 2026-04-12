# IG Following Account Analysis

## Overview

Extract Instagram following list and analyze account pages with browser automation. The tool uses Playwright to automate browser navigation, extract following list, and visit account pages for statistics and data extraction.

## Features

- ✅ Extract following list from target Instagram account
- ✅ Auto-scroll to load all following accounts
- ✅ Extract account information (username, display name, bio, avatar, verified status)
- ✅ Visit each account page for statistical analysis (optional)
- ✅ Generate analysis summary report

## Inputs

### Required Parameters

- `target_username` (string): Target Instagram username to extract following list from
- `workspace_id` (string): Mindscape workspace ID

### Optional Parameters

- `max_accounts` (integer): Maximum number of accounts to process (None = all)
- `visit_account_pages` (boolean): Whether to visit each account page for statistics (default: true)
- `run_mode` (string): Execution mode (`full` / `list` / `visit`, default: `full`)
  - `full`: scroll & capture the list first; if `visit_account_pages=true`, continue to visiting pages after preconditions are met
  - `list`: list capture only (forces `visit_account_pages=false`)
  - `visit`: visit pages only (forces `visit_account_pages=true`, reuses an existing saved list; errors if no usable list is found and instructs to run `list` first)
- `allow_partial_resume` (boolean): Allow `run_mode=visit` even when captured list is below expected (default: false)
  - By default, visits are only allowed when the list is `full` or `exhausted_incomplete` (evidence shows the UI cannot load more)

## Outputs

- `summary`: Analysis summary statistics
  - `total_accounts`: Total number of accounts
  - `verified_accounts`: Number of verified accounts
  - `accounts_with_bio`: Number of accounts with bio
  - `accounts_with_page_stats`: Number of accounts with page statistics
  - `verified_percentage`: Percentage of verified accounts
  - `bio_percentage`: Percentage of accounts with bio

- `accounts`: List of account data
  - `username`: Username
  - `display_name`: Display name
  - `bio`: Bio text
  - `is_verified`: Whether account is verified
  - `avatar_url`: Avatar URL
  - `account_link`: Account profile link
  - `follower_count_text`: Follower count text (if page visited)
  - `following_count_text`: Following count text (if page visited)
  - `post_count_text`: Post count text (if page visited)
  - `profile_bio`: Profile bio (if page visited)
  - `profile_image_url`: Profile image URL (if page visited)
  - `page_analyzed_at`: Page analysis timestamp (if page visited)

- `metadata`: Analysis metadata
  - `target_username`: Target username
  - `workspace_id`: Workspace ID
  - `analyzed_at`: Analysis timestamp
  - `total_accounts`: Total number of accounts
  - `visit_account_pages`: Whether pages were visited
  - `list_capture_status`: List capture status (`full` / `exhausted_incomplete` / `interrupted_incomplete` / `blocked` / `unknown_incomplete`)

## Usage Examples

### Basic Usage (Extract List and Visit Pages)

```json
{
  "target_username": "university.tw",
  "workspace_id": "ws_abc123",
  "run_mode": "full",
  "visit_account_pages": true
}
```

### Extract List Only (No Page Visits)

```json
{
  "target_username": "university.tw",
  "workspace_id": "ws_abc123",
  "run_mode": "list",
  "visit_account_pages": false
}
```

### Visit Pages Only (Reuse Existing List, Skip Scrolling)

```json
{
  "target_username": "university.tw",
  "workspace_id": "ws_abc123",
  "run_mode": "visit",
  "visit_account_pages": true
}
```

### Limit Processing Count

```json
{
  "target_username": "university.tw",
  "workspace_id": "ws_abc123",
  "max_accounts": 100,
  "run_mode": "full",
  "visit_account_pages": true
}
```

## Notes

1. **Browser Automation**: This tool uses Playwright for browser automation and requires Playwright browsers to be installed
2. **Login Required**: Must be logged into Instagram account to access following list
3. **Execution Time**: Processing large numbers of accounts with `visit_account_pages` enabled may take significant time
4. **Rate Limiting**: Automatic delays are added when visiting account pages to avoid triggering Instagram rate limits
5. **Full vs exhausted**: When `expected_following_count` is available, the system attempts a strict "reach expected" capture; if evidence shows the UI is exhausted, it ends list capture with `list_capture_status=exhausted_incomplete` and (when `visit_account_pages=true`) may proceed to visit pages on the captured list (since it's the complete result available via DOM)

## Related Tools

- `ig.ig_analyze_following`: Core analysis tool
