---
playbook_code: yogacoach_upload_policy_and_presign
version: 1.0.0
locale: en
name: "Upload Policy & Presign"
description: "Generate upload policy and presigned URLs based on upload method, set TTL, generate privacy receipt"
capability_code: yogacoach
tags:
  - yoga
  - upload
  - privacy
---

# Playbook: Upload Policy & Presign

**Playbook Code**: `yogacoach_upload_policy_and_presign`
**Version**: 1.0.0
**Purpose**: Generate upload policy and presigned URLs based on upload method, set TTL, generate privacy receipt

---

## Input Data

**Note**: Cloud-specific fields like `tenant_id`, `session_id` are provided by runtime from execution envelope, not in playbook inputs.

```json
{
  "upload_method": "backend_video",
  "file_metadata": {
    "filename": "yoga_session.mp4",
    "content_type": "video/mp4",
    "size_bytes": 12345678
  },
  "ttl_seconds": 3600,
  "callback_webhook": "https://example.com/webhook/upload-complete"
}
```

## Output Data

```json
{
  "upload_config": {
    "method": "backend_video",
    "endpoint": "https://storage.example.com/upload",
    "http_method": "PUT",
    "headers": {
      "X-Session-ID": "session-abc123",
      "X-Idempotency-Key": "idemp-xyz789"
    },
    "fields": {
      "key": "temp/session-abc123/video.mp4",
      "acl": "private"
    }
  },
  "ttl_seconds": 3600,
  "privacy_receipt_id": "PR-xxxxx",
  "callback_webhook": "https://example.com/webhook/upload-complete",
  "expected_payload": "video"
}
```

## Execution Steps

1. **Get Session Info**
   - Get session information from `session_id` (provided by runtime)
   - Verify session exists and is valid

2. **Generate Upload Policy**
   - Generate corresponding upload policy based on `upload_method`
   - `frontend_keypoints`: Frontend directly uploads keypoints data
   - `backend_video`: Generate presigned URL for backend video upload

3. **Generate Presigned URL** (if needed)
   - If `upload_method` is `backend_video`, generate presigned URL
   - Set TTL (temporary storage, not permanent)
   - Configure object lifecycle rules (auto-delete)

4. **Generate Privacy Receipt**
   - Generate privacy receipt proving "no permanent storage"
   - Record object key, expiration time, lifecycle policy
   - Generate audit log

5. **Configure Callback Webhook**
   - Set callback webhook for upload completion
   - Configure callback parameters

## Capability Dependencies

- `yogacoach.upload_policy_generator`: Upload policy generation
- `yogacoach.storage_manager`: Storage management
- `yogacoach.privacy_receipt_manager`: Privacy receipt management

**Note**: Use capability_code to describe requirements, not hardcoded tool paths. Actual tools are resolved by runtime based on capability_code.

## Privacy Protection Mechanism

- ✅ S3/GCS Object Lifecycle Rule (TTL auto-delete)
- ✅ Server-side Audit Log (record deletion schedule and expiration time)
- ✅ Receipt contains `object_key` (encrypted), `expires_at`, `lifecycle_policy_id`
- ❌ Do not use "hash" as deletion proof (hash can only prove generation, not deletion)

## Error Handling

- Session not found: Return error, log details
- Invalid upload method: Return error, only frontend_keypoints/backend_video supported
- Storage configuration error: Return error, log details

