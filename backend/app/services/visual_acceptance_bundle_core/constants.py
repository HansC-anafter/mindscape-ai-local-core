"""Constants for visual acceptance bundle artifacts."""

VISUAL_ACCEPTANCE_ARTIFACT_KIND = "visual_acceptance_bundle"
VISUAL_ACCEPTANCE_PLAYBOOK_CODE = "visual_acceptance_review"

REVIEW_STATUS_PENDING = "pending_review"
SOURCE_KIND_LAF_PATCH = "laf_patch"
SOURCE_KIND_VR_RENDER = "vr_render"
SOURCE_KIND_CHARACTER_TRAINING_EVAL = "character_training_eval"
SOURCE_KIND_CHARACTER_PERFORMANCE_EVAL = "character_performance_eval"
SOURCE_KIND_PORTRAIT_ANIMATION_EVAL = "portrait_animation_eval"
SOURCE_KIND_TALKING_HEAD_EVAL = "talking_head_eval"

LINEAGE_KEYS = ("package_id", "preset_id", "binding_mode")
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
VIDEO_EXTS = {".mp4", ".mov", ".webm", ".m4v"}
JSON_EXTS = {".json"}
MAX_ARTIFACT_ID_LENGTH = 64
