import type { DeviceSessionEntry } from '@/lib/device-binding/deviceBindingClient';
import type { CaptureSourceReferenceLessonState } from '@/components/workspace/device-binding/capture-bridge/CaptureSourceBridgeProvider';
import type { MotionPracticeLaunchInput } from '@/components/workspace/device-binding/motionPracticeLauncher';
import {
  buildInstructionRefsFromLessonHandoff,
  type MotionPracticeLessonHandoff,
} from '@/components/workspace/device-binding/practice/motionPracticeLessonHandoff';

import type {
  MotionCoachCapabilityCode,
  MotionCoachWorkbenchStateInput,
  TimelineSegment,
} from './motionCoachWorkbenchStateTypes';

export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

export function readString(value: unknown): string {
  return typeof value === 'string' && value.trim() ? value.trim() : '';
}

export function readNumber(value: unknown): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : 0;
}

export function readOptionalNumber(value: unknown): number | undefined {
  return typeof value === 'number' && Number.isFinite(value) ? value : undefined;
}

export function readStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value
    .filter((item): item is string => typeof item === 'string' && item.trim().length > 0)
    .map((item) => item.trim());
}

export function readRecordArray(value: unknown): Record<string, unknown>[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.filter((item): item is Record<string, unknown> => isRecord(item));
}

export function readThumbnailUrl(value: unknown): string {
  if (!isRecord(value)) {
    return '';
  }
  const direct = readString(value.thumbnail_url)
    || readString(value.thumbnailUrl)
    || readString(value.preview_url)
    || readString(value.previewUrl)
    || readString(value.thumbnail_ref)
    || readString(value.thumbnailRef);
  if (direct) {
    return direct;
  }
  const thumbnail = value.thumbnail;
  if (isRecord(thumbnail)) {
    return readString(thumbnail.url);
  }
  return '';
}

export function clamp01(value: number): number {
  if (!Number.isFinite(value)) {
    return 0;
  }
  return Math.max(0, Math.min(1, value));
}

function capitalize(value: string): string {
  const normalized = value.trim();
  if (!normalized) {
    return '';
  }
  return normalized.charAt(0).toUpperCase() + normalized.slice(1);
}

function decodeDisplayText(value: string): string {
  try {
    return decodeURIComponent(value);
  } catch {
    return value;
  }
}

export function formatLessonDisplayTitle(value: string): string {
  const decoded = decodeDisplayText(value).trim();
  if (!decoded) {
    return '';
  }
  const slugLike = /[_-]{2,}|_/.test(decoded);
  if (!slugLike) {
    return decoded;
  }
  return decoded
    .replace(/[_-]+/g, ' ')
    .split(/\s+/)
    .filter(Boolean)
    .map((part) => {
      if (/^\d+$/.test(part)) {
        return part;
      }
      return capitalize(part);
    })
    .join(' ');
}

export function titleFromToken(value: string, fallback: string): string {
  const normalized = value.trim();
  if (!normalized) {
    return fallback;
  }
  return normalized
    .split(/[_\s-]+/)
    .filter(Boolean)
    .map((part) => capitalize(part))
    .join(' ');
}

function formatSourceProviderLabel(value: string): string {
  const normalized = value.trim().toLowerCase();
  if (normalized === 'youtube') {
    return 'YouTube';
  }
  return titleFromToken(value, value);
}

function extractYouTubeVideoId(value: string): string {
  const normalized = value.trim();
  if (!normalized) {
    return '';
  }
  try {
    const url = new URL(normalized);
    const host = url.hostname.toLowerCase();
    if (host === 'youtu.be' || host.endsWith('.youtu.be')) {
      return url.pathname.split('/').filter(Boolean)[0] || '';
    }
    if (host.includes('youtube.com') || host.includes('youtube-nocookie.com')) {
      const watchId = url.searchParams.get('v')?.trim();
      if (watchId) {
        return watchId;
      }
      const parts = url.pathname.split('/').filter(Boolean);
      const markerIndex = parts.findIndex((part) => ['embed', 'shorts', 'live'].includes(part));
      if (markerIndex >= 0 && parts[markerIndex + 1]) {
        return parts[markerIndex + 1];
      }
    }
  } catch {
    // Fall through to regex parsing for non-URL handoff values.
  }
  const matched = normalized.match(/(?:v=|youtu\.be\/|embed\/|shorts\/|live\/)([A-Za-z0-9_-]{6,})/);
  if (matched?.[1]) {
    return matched[1];
  }
  return /^[A-Za-z0-9_-]{8,}$/.test(normalized) ? normalized : '';
}

export function resolveYouTubeThumbnailUrl(value: string): string {
  const videoId = extractYouTubeVideoId(value);
  return videoId ? `https://i.ytimg.com/vi/${encodeURIComponent(videoId)}/hqdefault.jpg` : '';
}

function formatTimeLabel(totalMs: number): string {
  const totalSeconds = Math.max(0, Math.floor(totalMs / 1000));
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
}

export function formatTimeRangeLabel(startMs: number, endMs: number): string {
  return `${formatTimeLabel(startMs)}-${formatTimeLabel(endMs)}`;
}

export function dedupeStrings(values: string[], maxItems = 4): string[] {
  const seen = new Set<string>();
  const next: string[] = [];
  for (const value of values) {
    const normalized = value.trim();
    if (!normalized || seen.has(normalized)) {
      continue;
    }
    seen.add(normalized);
    next.push(normalized);
    if (next.length >= maxItems) {
      break;
    }
  }
  return next;
}

export function mapCaptureSourceType(session: DeviceSessionEntry | null): 'phone' | 'pad' | 'desktop_camera' | 'external_provider' | 'obs' | 'file' | 'unknown' {
  if (!session) {
    return 'unknown';
  }
  if (session.source_types.includes('external_provider_camera')) {
    return 'external_provider';
  }
  if (session.source_types.includes('virtual_camera')) {
    return 'obs';
  }
  if (session.source_types.includes('phone_camera')) {
    const label = `${session.display_name || ''} ${session.device_id || ''}`.toLowerCase();
    return label.includes('ipad') || label.includes('tablet') ? 'pad' : 'phone';
  }
  if (session.source_types.includes('desktop_camera') || session.source_types.includes('usb_camera')) {
    return 'desktop_camera';
  }
  return 'unknown';
}

export function mapCaptureTransport(session: DeviceSessionEntry | null): 'webrtc' | 'lan_qr' | 'local_file' | 'unknown' {
  if (!session) {
    return 'unknown';
  }
  if (session.source_types.includes('phone_camera')) {
    return 'webrtc';
  }
  if (
    session.source_types.includes('desktop_camera') ||
    session.source_types.includes('usb_camera') ||
    session.source_types.includes('virtual_camera') ||
    session.source_types.includes('external_provider_camera')
  ) {
    return 'webrtc';
  }
  return 'unknown';
}

export function mapCaptureStatus(session: DeviceSessionEntry | null): 'ready' | 'pairing' | 'offline' {
  if (!session) {
    return 'pairing';
  }
  if (session.state === 'active' || session.state === 'paired') {
    return 'ready';
  }
  if (session.state === 'pairing') {
    return 'pairing';
  }
  return 'offline';
}

export function extractCourseSegments(
  instructionRefs: Record<string, unknown>[] | null | undefined,
): TimelineSegment[] {
  const segments: TimelineSegment[] = [];
  for (const ref of instructionRefs || []) {
    if (!isRecord(ref)) {
      continue;
    }
    for (const chapter of readRecordArray(ref.course_chapters)) {
      const id = readString(chapter.chapter_id) || readString(chapter.phrase_id);
      const title = readString(chapter.title);
      if (!id || !title) {
        continue;
      }
      segments.push({
        id,
        title,
        startMs: readNumber(chapter.start_ms),
        endMs: readNumber(chapter.end_ms),
        thumbnailUrl: readThumbnailUrl(chapter) || undefined,
      });
    }
  }
  return segments.sort((left, right) => left.startMs - right.startMs);
}

export function resolveInstructionRefs(input: MotionCoachWorkbenchStateInput): Record<string, unknown>[] {
  if (input.launchInput?.instructionRefs?.length) {
    return input.launchInput.instructionRefs.filter(isRecord);
  }
  return buildInstructionRefsFromLessonHandoff(input.pendingLessonHandoff);
}

function readReferenceLessonId(
  referenceLessonState: CaptureSourceReferenceLessonState | null,
): string {
  if (!isRecord(referenceLessonState)) {
    return '';
  }
  const lessonStateRecord = referenceLessonState as Record<string, unknown>;
  return readString(lessonStateRecord.lesson_id);
}

export function resolveLessonId(
  launchInput: MotionPracticeLaunchInput | null,
  referenceLessonState: CaptureSourceReferenceLessonState | null,
  pendingLessonHandoff: MotionPracticeLessonHandoff | null | undefined,
): string {
  return launchInput?.expertLibraryRef?.trim()
    || pendingLessonHandoff?.sourceValue?.trim()
    || readReferenceLessonId(referenceLessonState)
    || 'lesson_pending';
}

export function resolveSegmentForWindow(
  startMs: number,
  endMs: number,
  segments: TimelineSegment[],
  fallbackId: string,
): TimelineSegment | null {
  const midpoint = startMs + Math.max(0, endMs - startMs) / 2;
  for (const segment of segments) {
    if (midpoint >= segment.startMs && midpoint <= segment.endMs) {
      return segment;
    }
  }
  return segments.find((segment) => segment.id === fallbackId) || null;
}

export function resolveLessonTitle(
  capabilityCode: MotionCoachCapabilityCode,
  referenceLessonState: CaptureSourceReferenceLessonState | null,
  segments: TimelineSegment[],
  pendingLessonHandoff: MotionPracticeLessonHandoff | null | undefined,
): string {
  if (pendingLessonHandoff?.sourceTitle?.trim()) {
    return formatLessonDisplayTitle(pendingLessonHandoff.sourceTitle);
  }
  if (referenceLessonState?.title?.trim()) {
    return formatLessonDisplayTitle(referenceLessonState.title);
  }
  if (segments.length) {
    return capabilityCode === 'dance_motion_coach'
      ? 'Dance Practice Reference'
      : 'Yoga Practice Reference';
  }
  return capabilityCode === 'dance_motion_coach'
    ? 'Dance lesson pending'
    : 'Yoga lesson pending';
}

export function resolveLessonSourceProvider(
  launchInput: MotionPracticeLaunchInput | null,
  pendingLessonHandoff: MotionPracticeLessonHandoff | null | undefined,
): string {
  const firstInstructionRef = launchInput?.instructionRefs?.find((item) => isRecord(item)) || null;
  const provider = readString(firstInstructionRef?.source_provider)
    || readString(firstInstructionRef?.provider)
    || pendingLessonHandoff?.sourceProvider?.trim()
    || '';
  if (provider) {
    return provider;
  }
  if (pendingLessonHandoff?.sourceKind === 'youtube_instruction_ref') {
    return 'youtube';
  }
  if (pendingLessonHandoff?.sourceKind === 'local_video_smoke_ref') {
    return 'local';
  }
  if (launchInput?.expertLibraryRef?.trim()) {
    return 'manual';
  }
  return 'missing';
}

export function resolveLessonSourceLabel(
  launchInput: MotionPracticeLaunchInput | null,
  pendingLessonHandoff: MotionPracticeLessonHandoff | null | undefined,
): string {
  const teacherRef = launchInput?.expertLibraryRef?.trim();
  if (teacherRef) {
    return teacherRef;
  }
  const firstInstructionRef = launchInput?.instructionRefs?.find((item) => isRecord(item)) || null;
  if (firstInstructionRef) {
    return readString(firstInstructionRef.video_ref)
      || readString(firstInstructionRef.media_ref)
      || readString(firstInstructionRef.teacher_ref)
      || readString(firstInstructionRef.ref_type)
      || 'Instruction ref';
  }
  const handoffProvider = pendingLessonHandoff?.sourceProvider?.trim();
  const handoffValue = pendingLessonHandoff?.sourceValue?.trim();
  if (handoffProvider && handoffValue) {
    return `${formatSourceProviderLabel(handoffProvider)} · ${handoffValue}`;
  }
  if (handoffProvider) {
    return formatSourceProviderLabel(handoffProvider);
  }
  if (pendingLessonHandoff?.sourceTitle?.trim()) {
    return formatLessonDisplayTitle(pendingLessonHandoff.sourceTitle);
  }
  if (handoffValue) {
    return handoffValue;
  }
  return 'Instruction source pending';
}

export function resolveLessonThumbnailUrl(input: {
  instructionRefs: Record<string, unknown>[];
  segments: TimelineSegment[];
  pendingLessonHandoff: MotionPracticeLessonHandoff | null | undefined;
}): string {
  const handoffThumbnail = input.pendingLessonHandoff?.thumbnailUrl?.trim();
  if (handoffThumbnail) {
    return handoffThumbnail;
  }
  for (const segment of input.segments) {
    if (segment.thumbnailUrl) {
      return segment.thumbnailUrl;
    }
  }
  for (const ref of input.instructionRefs) {
    const thumbnail = readThumbnailUrl(ref);
    if (thumbnail) {
      return thumbnail;
    }
    const provider = readString(ref.source_provider) || readString(ref.provider);
    if (provider.toLowerCase() === 'youtube') {
      const youtubeThumbnail = resolveYouTubeThumbnailUrl(
        readString(ref.video_ref)
        || readString(ref.canonical_url)
        || readString(ref.provider_video_id),
      );
      if (youtubeThumbnail) {
        return youtubeThumbnail;
      }
    }
  }
  const handoff = input.pendingLessonHandoff;
  const handoffProvider = handoff?.sourceProvider?.trim().toLowerCase() || '';
  if (handoff?.sourceKind === 'youtube_instruction_ref' || handoffProvider === 'youtube') {
    return resolveYouTubeThumbnailUrl(handoff.sourceValue);
  }
  return '';
}

export function buildYogaReferenceLessonImportRef(input: {
  lessonId: string;
  segments: TimelineSegment[];
  sourceProvider: string;
  hasSelectedLesson: boolean;
}): Record<string, unknown> {
  const importId = input.lessonId === 'lesson_pending'
    ? 'reference-lesson-import-missing'
    : `reference-lesson-import:${input.lessonId}`;
  if (input.segments.length > 0) {
    return {
      id: importId,
      status: 'ready',
      artifact_ref: input.lessonId,
      confidence: 0.84,
      human_patch_required: false,
      ready_chapter_count: input.segments.length,
      contract_version: 'yogacoach.reference_lesson_import.v1',
      artifact_schema_id: 'vcs_instruction_video_prepared_bundle.v1',
      source_provider: input.sourceProvider,
    };
  }
  if (input.hasSelectedLesson) {
    return {
      id: importId,
      status: 'materializing',
      artifact_ref: input.lessonId,
      confidence: 0.32,
      human_patch_required: true,
      ready_chapter_count: 0,
      blocked_reason: 'Reference lesson is selected, but bounded chapters are not attached yet.',
      contract_version: 'yogacoach.reference_lesson_import.v1',
      artifact_schema_id: 'vcs_instruction_video_prepared_bundle.v1',
      source_provider: input.sourceProvider,
    };
  }
  return {
    id: importId,
    status: 'missing',
    confidence: 0,
    human_patch_required: true,
    ready_chapter_count: 0,
    blocked_reason: 'Reference lesson import is not attached to this workbench state.',
    contract_version: 'yogacoach.reference_lesson_import.v1',
    artifact_schema_id: 'vcs_instruction_video_prepared_bundle.v1',
    source_provider: 'missing',
  };
}
