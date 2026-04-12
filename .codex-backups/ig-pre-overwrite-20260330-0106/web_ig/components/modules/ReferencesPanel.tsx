import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { VirtuosoGrid } from 'react-virtuoso';
import { Pin, Search, Trash2, Loader2, AlertCircle, FolderOpen, Plus, ChevronDown, RefreshCw, CheckSquare, Square, Eye, ExternalLink, Layers } from 'lucide-react';
import { getReferenceImageUrl } from './accounts/utils';
import { applyExecutionBackendHint } from './accounts/api';
import { BaseModal } from '../../../../../components/BaseModal';
import AddToTrainingCandidateModal from './AddToTrainingCandidateModal';
import VisionAnalysisDetail from './VisionAnalysisDetail';
import { injectWorkspaceIGBrowserProfileInputs } from '../browserProfile';
import { hasIGRefreshHint, useIGWorkspaceEvents } from '../hooks/useIGWorkspaceEvents';

interface ProjectItem {
  id: string;
  title: string;
  type: string;
}

interface ReferenceEntry {
  reference_id: string;
  content_hash: string;
  source_handle: string;
  source_shortcode: string;
  tags: string[];
  auto_tags: string[];
  collections: string[];
  pinned_at: string;
  deleted: boolean;
  has_analysis: boolean;
  analysis_status: string;
  analysis_profile?: string;
  schema_version?: string;
  validated_at?: string;
  task_id?: string;
  carousel_index?: number;
  carousel_total?: number;
  carousel_parent_id?: string;
  post_caption?: string;
  analysis_error?: string;
  analysis_failure_stage?: string;
  analysis_excerpt?: string;
  has_thinking?: boolean;
}

interface ReferencesPanelProps {
  workspaceId: string;
  apiUrl?: string;
}

type ViewState = 'loading' | 'empty' | 'error' | 'loaded';

interface FacetOption {
  value: string;
  count: number;
}

interface ReferenceFacets {
  source_handles: string[];
  tags: string[];
  analysis_profiles: string[];
  training_readiness_values: string[];
  training_lane_hint_values: string[];
  training_style_tag_values: string[];
  training_quality_flag_values: string[];
  identity_cluster_hint_values: string[];
  look_state_hint_values: string[];
  source_handle_options: FacetOption[];
  tag_options: FacetOption[];
  analysis_profile_options: FacetOption[];
  training_readiness_options: FacetOption[];
  training_lane_hint_options: FacetOption[];
  training_style_tag_options: FacetOption[];
  training_quality_flag_options: FacetOption[];
  identity_cluster_hint_options: FacetOption[];
  look_state_hint_options: FacetOption[];
}

interface ReferenceCounts {
  total: number;
  completed: number;
  running: number;
  pending: number;
  failed: number;
}

interface ReferencesListCacheSnapshot {
  references: ReferenceEntry[];
  totalReferences: number;
  counts: ReferenceCounts;
  viewState: Extract<ViewState, 'loaded' | 'empty'>;
  hasMore: boolean;
}

type ReferenceFetchMode = 'reset' | 'append' | 'refresh_loaded' | 'refresh_head';

type ReferenceFetchOutcome = 'applied' | 'dropped' | 'aborted' | 'error';

interface ReferenceFetchResult {
  outcome: ReferenceFetchOutcome;
  headReferenceId?: string | null;
  total?: number;
  errorMessage?: string;
}

type ReferencesDebugEventType =
  | 'start'
  | 'apply'
  | 'drop_stale_query'
  | 'drop_stale_request'
  | 'abort'
  | 'error';

interface ReferencesDebugEvent {
  ts: string;
  type: ReferencesDebugEventType;
  requestId: number;
  mode: ReferenceFetchMode;
  sortBy: string;
  offset: number;
  limit: number;
  queryKey: string;
  currentQueryKey: string;
  message?: string;
}

interface ReferencesDebugStore {
  currentSortBy: string;
  currentQueryKey: string;
  latestStartedRequestId: number;
  latestAppliedRequestId: number;
  events: ReferencesDebugEvent[];
}

interface BatchPinExecutionSummary {
  execution_id: string;
  status: string;
  created_at?: string | null;
}

interface LatestBatchPinSummaryResponse {
  latest_attempt?: BatchPinExecutionSummary | null;
}

type InstagramExternalTarget = {
  url: string;
  mode: 'account' | 'post';
};

declare global {
  interface Window {
    __igReferencesDebug?: ReferencesDebugStore;
    __igReferencesDebugEcho?: boolean;
  }
}

const REFERENCES_PAGE_SIZE = 40;
const BACKGROUND_REFRESH_PAGE_SIZE = REFERENCES_PAGE_SIZE;
const ANALYZED_LATEST_HEAD_SYNC_INTERVAL_MS = 5_000;
const AUTO_APPEND_NEAR_END_THRESHOLD_PX = 800;
// Only flush deferred latest-sort refreshes once the user is effectively back at
// the very top. Allowing "near top" refreshes causes visible snap-back because
// new head items increase the grid height while the user is still scrolling.
const BACKGROUND_REFRESH_NEAR_TOP_THRESHOLD_PX = 1;
const ENABLE_REFERENCES_PANEL_CACHE = process.env.NODE_ENV !== 'test';
const referencesListCache = new Map<string, ReferencesListCacheSnapshot>();
const referencesFacetsCache = new Map<string, ReferenceFacets>();
const INSTAGRAM_BASE_URL = 'https://www.instagram.com';
const BATCH_PIN_START_SOFT_TIMEOUT_MS = 8_000;
const BATCH_PIN_START_HARD_TIMEOUT_MS = 30_000;
const BATCH_PIN_SUMMARY_POLL_ATTEMPTS = 4;
const BATCH_PIN_SUMMARY_POLL_INTERVAL_MS = 1_000;
let lastInstagramExternalOpen: { url: string; at: number } | null = null;

function normalizeInstagramHandle(handle: string | null | undefined): string {
  return (handle || '')
    .toString()
    .trim()
    .replace(/^@+/, '')
    .replace(/^https?:\/\/(www\.)?instagram\.com\//i, '')
    .replace(/\/+$/, '')
    .split('/')[0]
    .trim();
}

function normalizeInstagramShortcode(shortcode: string | null | undefined): string {
  return (shortcode || '').toString().trim().replace(/\/+$/, '');
}

function buildInstagramAccountUrl(handle: string | null | undefined): string | null {
  const normalized = normalizeInstagramHandle(handle);
  if (!normalized) return null;
  return `${INSTAGRAM_BASE_URL}/${normalized}/`;
}

function formatInstagramHandle(handle: string | null | undefined): string {
  const normalized = normalizeInstagramHandle(handle);
  return normalized ? `@${normalized}` : 'Unknown';
}

function buildInstagramPostUrl(shortcode: string | null | undefined): string | null {
  const normalized = normalizeInstagramShortcode(shortcode);
  if (!normalized) return null;
  return `${INSTAGRAM_BASE_URL}/p/${normalized}/`;
}

function getReferenceInstagramTarget(
  ref: Pick<ReferenceEntry, 'source_handle' | 'source_shortcode'>,
): InstagramExternalTarget | null {
  const postUrl = buildInstagramPostUrl(ref.source_shortcode);
  if (postUrl) {
    return { url: postUrl, mode: 'post' };
  }
  const accountUrl = buildInstagramAccountUrl(ref.source_handle);
  if (accountUrl) {
    return { url: accountUrl, mode: 'account' };
  }
  return null;
}

function openInstagramExternalTarget(target: InstagramExternalTarget) {
  if (typeof window === 'undefined') return;
  const now = Date.now();
  if (
    lastInstagramExternalOpen &&
    lastInstagramExternalOpen.url === target.url &&
    now - lastInstagramExternalOpen.at < 1200
  ) {
    return;
  }
  lastInstagramExternalOpen = { url: target.url, at: now };
  window.open(target.url, '_blank', 'noopener,noreferrer');
}

function parseJsonSafely<T>(raw: string): T | null {
  if (!raw) return null;
  try {
    return JSON.parse(raw) as T;
  } catch {
    return null;
  }
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function shouldSyncHeadForSort(sortBy: string): boolean {
  return sortBy === 'analyzed_latest' || sortBy === 'pending_latest';
}

function mergeRefHeadWindow(
  previous: ReferenceEntry[],
  nextHead: ReferenceEntry[],
  nextTotal: number,
): ReferenceEntry[] {
  const nextIds = new Set(nextHead.map((entry) => entry.reference_id));
  const tail = previous.filter((entry) => !nextIds.has(entry.reference_id));
  const targetLength = nextTotal > 0
    ? Math.min(Math.max(previous.length, nextHead.length), nextTotal)
    : nextHead.length;
  return [...nextHead, ...tail].slice(0, targetLength);
}

function withReferencesDebugStore(mutator: (store: ReferencesDebugStore) => void) {
  if (typeof window === 'undefined') return;
  const store = window.__igReferencesDebug ?? {
    currentSortBy: '',
    currentQueryKey: '',
    latestStartedRequestId: 0,
    latestAppliedRequestId: 0,
    events: [],
  };
  mutator(store);
  if (store.events.length > 100) {
    store.events = store.events.slice(-100);
  }
  window.__igReferencesDebug = store;
}

function recordReferencesDebugEvent(
  event: ReferencesDebugEvent,
  snapshot?: Partial<Omit<ReferencesDebugStore, 'events'>>,
) {
  withReferencesDebugStore((store) => {
    if (snapshot?.currentSortBy !== undefined) {
      store.currentSortBy = snapshot.currentSortBy;
    }
    if (snapshot?.currentQueryKey !== undefined) {
      store.currentQueryKey = snapshot.currentQueryKey;
    }
    if (snapshot?.latestStartedRequestId !== undefined) {
      store.latestStartedRequestId = snapshot.latestStartedRequestId;
    }
    if (snapshot?.latestAppliedRequestId !== undefined) {
      store.latestAppliedRequestId = snapshot.latestAppliedRequestId;
    }
    store.events.push(event);
  });
  if (
    process.env.NODE_ENV !== 'production'
    && typeof window !== 'undefined'
    && window.__igReferencesDebugEcho === true
  ) {
    console.info('[IGRefs]', event.type, event);
  }
}

function isScrollContainerNearEnd(
  container: HTMLDivElement,
  thresholdPx = AUTO_APPEND_NEAR_END_THRESHOLD_PX,
): boolean {
  const remaining = container.scrollHeight - container.scrollTop - container.clientHeight;
  return remaining <= thresholdPx;
}

function normalizeFacetOptions(rawOptions: unknown, rawValues: unknown): FacetOption[] {
  const options: FacetOption[] = [];
  const seen = new Set<string>();

  if (Array.isArray(rawOptions)) {
    rawOptions.forEach((option) => {
      if (option && typeof option === 'object' && 'value' in option) {
        const value = String((option as { value?: unknown }).value || '').trim();
        if (!value || seen.has(value)) return;
        seen.add(value);
        options.push({
          value,
          count: Number((option as { count?: unknown }).count || 0),
        });
      }
    });
  }

  if (Array.isArray(rawValues)) {
    rawValues.forEach((value) => {
      const normalized = String(value || '').trim();
      if (!normalized || seen.has(normalized)) return;
      seen.add(normalized);
      options.push({ value: normalized, count: 0 });
    });
  }

  return options;
}

function buildFacetOptions(options: FacetOption[], selectedValue: string): FacetOption[] {
  const seen = new Set<string>();
  const merged: FacetOption[] = [];

  if (selectedValue) {
    const selected = options.find((option) => option.value === selectedValue);
    merged.push(selected || { value: selectedValue, count: 0 });
    seen.add(selectedValue);
  }

  options.forEach((option) => {
    if (seen.has(option.value)) return;
    seen.add(option.value);
    merged.push(option);
  });

  return merged;
}

function FacetPicker(props: {
  allLabel: string;
  value: string;
  options: FacetOption[];
  onChange: (value: string) => void;
  searchPlaceholder: string;
  browseLabel: string;
  className?: string;
}) {
  const {
    allLabel,
    value,
    options,
    onChange,
    searchPlaceholder,
    browseLabel,
    className,
  } = props;
  const [isOpen, setIsOpen] = useState(false);
  const [query, setQuery] = useState('');
  const wrapperRef = useRef<HTMLDivElement | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    if (!isOpen) {
      setQuery('');
      return;
    }

    const handlePointerDown = (event: MouseEvent) => {
      if (!wrapperRef.current?.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };
    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setIsOpen(false);
      }
    };

    const focusTimer = window.setTimeout(() => {
      inputRef.current?.focus();
    }, 0);

    document.addEventListener('mousedown', handlePointerDown);
    document.addEventListener('keydown', handleEscape);
    return () => {
      window.clearTimeout(focusTimer);
      document.removeEventListener('mousedown', handlePointerDown);
      document.removeEventListener('keydown', handleEscape);
    };
  }, [isOpen]);

  const filteredOptions = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();
    if (!normalizedQuery) return options;
    return options.filter((option) => option.value.toLowerCase().includes(normalizedQuery));
  }, [options, query]);

  const selectedCount = useMemo(() => {
    if (!value) return null;
    return options.find((option) => option.value === value)?.count ?? null;
  }, [options, value]);

  return (
    <div ref={wrapperRef} className={`relative min-w-0 flex-[1_1_15%] ${className || ''}`}>
      <button
        type="button"
        onClick={() => setIsOpen((current) => !current)}
        className="flex w-full items-center gap-2 rounded border border-gray-200 bg-gray-50 px-2 py-1 text-xs text-left transition-colors hover:border-rose-300 hover:bg-white dark:border-gray-700 dark:bg-gray-800 dark:hover:border-rose-500/60 dark:hover:bg-gray-900"
      >
        <span className={`min-w-0 flex-1 truncate ${value ? 'text-gray-800 dark:text-gray-100' : 'text-gray-500 dark:text-gray-400'}`}>
          {value || allLabel}
        </span>
        {selectedCount !== null && (
          <span className="shrink-0 rounded-full bg-rose-100 px-1.5 py-0.5 text-[10px] font-medium text-rose-600 dark:bg-rose-900/30 dark:text-rose-300">
            {selectedCount}
          </span>
        )}
        <ChevronDown className={`h-3.5 w-3.5 shrink-0 text-gray-400 transition-transform ${isOpen ? 'rotate-180' : ''}`} />
      </button>

      {isOpen && (
        <div className="absolute left-0 top-[calc(100%+0.35rem)] z-40 w-full min-w-[18rem] max-w-[24rem] overflow-hidden rounded-xl border border-gray-200 bg-white shadow-xl dark:border-gray-700 dark:bg-gray-900">
          <div className="border-b border-gray-100 p-2 dark:border-gray-800">
            <div className="relative">
              <Search className="pointer-events-none absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-gray-400" />
              <input
                ref={inputRef}
                type="text"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder={searchPlaceholder}
                className="w-full rounded-md border border-gray-200 bg-gray-50 py-1.5 pl-7 pr-2 text-xs text-gray-800 outline-none focus:border-rose-300 focus:bg-white focus:ring-1 focus:ring-rose-300 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100 dark:focus:border-rose-500/60 dark:focus:bg-gray-900 dark:focus:ring-rose-500/40"
              />
            </div>
          </div>

          <div className="max-h-72 overflow-y-auto py-1">
            <button
              type="button"
              onClick={() => {
                onChange('');
                setIsOpen(false);
              }}
              className={`flex w-full items-center justify-between gap-3 px-3 py-2 text-xs transition-colors ${!value ? 'bg-rose-50 text-rose-600 dark:bg-rose-950/30 dark:text-rose-300' : 'text-gray-600 hover:bg-gray-50 dark:text-gray-300 dark:hover:bg-gray-800'}`}
            >
              <span className="truncate">{allLabel}</span>
              {!value && (
                <span className="rounded-full bg-rose-100 px-1.5 py-0.5 text-[10px] font-medium text-rose-600 dark:bg-rose-900/30 dark:text-rose-300">
                  active
                </span>
              )}
            </button>

            {filteredOptions.length === 0 ? (
              <div className="px-3 py-6 text-center text-xs text-gray-400">
                No matches for &quot;{query.trim()}&quot;
              </div>
            ) : (
              filteredOptions.map((option) => {
                const isSelected = option.value === value;
                return (
                  <button
                    key={option.value}
                    type="button"
                    onClick={() => {
                      onChange(option.value);
                      setIsOpen(false);
                    }}
                    className={`flex w-full items-center justify-between gap-3 px-3 py-2 text-xs transition-colors ${isSelected ? 'bg-rose-50 text-rose-600 dark:bg-rose-950/30 dark:text-rose-300' : 'text-gray-700 hover:bg-gray-50 dark:text-gray-200 dark:hover:bg-gray-800'}`}
                    title={option.value}
                  >
                    <span className="min-w-0 flex-1 truncate text-left">{option.value}</span>
                    <span className="shrink-0 rounded-full bg-gray-100 px-1.5 py-0.5 text-[10px] font-medium text-gray-500 dark:bg-gray-800 dark:text-gray-300">
                      {option.count}
                    </span>
                  </button>
                );
              })
            )}
          </div>

          <div className="border-t border-gray-100 px-3 py-1.5 text-[10px] text-gray-500 dark:border-gray-800 dark:text-gray-400">
            {browseLabel}
          </div>
        </div>
      )}
    </div>
  );
}

/** Inline component: fetches and renders carousel sibling thumbnails. */
function CarouselSiblings({ referenceId, workspaceId, apiUrl }: { referenceId: string; workspaceId: string; apiUrl: string }) {
  const [siblings, setSiblings] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const res = await fetch(`${apiUrl}/api/v1/ig/references/${referenceId}/carousel-group?workspace_id=${workspaceId}`);
        if (res.ok) {
          const data = await res.json();
          setSiblings(data.siblings || []);
        }
      } catch { /* ignore */ }
      finally { setLoading(false); }
    })();
  }, [referenceId, workspaceId, apiUrl]);

  if (loading) return <div className="text-[10px] text-gray-400 py-2">Loading carousel...</div>;
  if (siblings.length <= 1) return null;

  return (
    <div className="pt-3 border-t border-gray-200 dark:border-gray-700">
      <h4 className="text-xs font-medium text-gray-500 mb-2 flex items-center gap-1">
        <Layers className="w-3 h-3" />
        Carousel ({siblings.length} slides)
      </h4>
      <div className="flex gap-1.5 overflow-x-auto pb-1">
        {siblings.map((sib: any) => (
          <div
            key={sib.reference_id}
            className={`shrink-0 w-14 h-14 rounded border overflow-hidden ${sib.reference_id === referenceId ? 'border-rose-400 ring-1 ring-rose-400/50' : 'border-gray-200 dark:border-gray-700'}`}
          >
            {sib.reference_id && (
              <img
                src={getReferenceImageUrl(apiUrl, workspaceId, sib.reference_id)}
                className="w-full h-full object-cover"
                alt={`Slide ${(sib.carousel_index ?? 0) + 1}`}
                loading="lazy"
                decoding="async"
              />
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

const ReferenceGridCard = React.memo(function ReferenceGridCard(props: {
  refData: ReferenceEntry;
  apiUrl: string;
  workspaceId: string;
  selected: boolean;
  onToggleSelect: (referenceId: string) => void;
  onViewDetail: (referenceId: string) => void;
  onAddToTraining: (referenceId: string) => void;
  onDelete: (referenceId: string) => void;
}) {
  const { refData, apiUrl, workspaceId, selected, onToggleSelect, onViewDetail, onAddToTraining, onDelete } = props;
  const instagramTarget = getReferenceInstagramTarget(refData);
  const instagramAccountUrl = buildInstagramAccountUrl(refData.source_handle);
  const displayHandle = formatInstagramHandle(refData.source_handle);
  const instagramTitle = instagramTarget?.mode === 'account'
    ? 'Open source account on Instagram'
    : 'View post on Instagram';

  return (
    <div
      data-testid={`ref-card-${refData.reference_id}`}
      data-reference-id={refData.reference_id}
      className={`group relative bg-gray-50 dark:bg-gray-800 rounded-lg overflow-hidden border transition-colors ${selected ? 'border-blue-400 ring-1 ring-blue-400/50' : 'border-gray-200 dark:border-gray-700 hover:border-rose-300'}`}
    >
      <button
        onClick={(e) => { e.stopPropagation(); onToggleSelect(refData.reference_id); }}
        className="absolute top-1 left-1 z-10 p-0.5 rounded bg-black/30 text-white hover:bg-black/50 transition-colors"
      >
        {selected ? <CheckSquare className="w-3 h-3" /> : <Square className="w-3 h-3 opacity-0 group-hover:opacity-100 transition-opacity" />}
      </button>

      <div
        className="aspect-square bg-gray-100 dark:bg-gray-900 flex items-center justify-center overflow-hidden cursor-pointer"
        onClick={() => onViewDetail(refData.reference_id)}
      >
        {refData.reference_id ? (
          <img
            src={getReferenceImageUrl(apiUrl, workspaceId, refData.reference_id)}
            alt={refData.source_shortcode || refData.reference_id}
            className="w-full h-full object-cover"
            loading="lazy"
            decoding="async"
            onError={(e) => {
              (e.target as HTMLImageElement).style.display = 'none';
              (e.target as HTMLImageElement).parentElement!.querySelector('.ref-placeholder')?.classList.remove('hidden');
            }}
          />
        ) : null}
        <Pin className={`w-6 h-6 text-gray-300 ref-placeholder ${refData.reference_id ? 'hidden' : ''}`} />
      </div>

      {refData.carousel_total && refData.carousel_total > 1 && (
        <div className="absolute bottom-[calc(100%-2rem)] right-1 flex items-center gap-0.5 bg-black/60 text-white text-[9px] font-medium px-1.5 py-0.5 rounded-full">
          <Layers className="w-2.5 h-2.5" />
          {refData.carousel_index !== undefined ? `${refData.carousel_index + 1}/` : ''}{refData.carousel_total}
        </div>
      )}

      <div className="p-2">
        <div className="text-[10px] font-medium text-gray-600 dark:text-gray-400 truncate">
          {instagramAccountUrl ? (
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                openInstagramExternalTarget({ url: instagramAccountUrl, mode: 'account' });
              }}
              className="max-w-full truncate hover:text-purple-500 hover:underline underline-offset-2"
              title="Open source account on Instagram"
              aria-label={`Open ${displayHandle} on Instagram`}
            >
              {displayHandle}
            </button>
          ) : (
            displayHandle
          )}
        </div>
        <div className="text-[9px] text-gray-400 truncate">
          {refData.source_shortcode}
        </div>

        {(refData.tags.length > 0 || refData.auto_tags.length > 0) && (
          <div className="flex flex-wrap gap-0.5 mt-1 max-w-full overflow-hidden">
            {[...refData.tags.slice(0, 2), ...refData.auto_tags.slice(0, 1)].map((tag) => (
              <span
                key={tag}
                className="text-[8px] bg-rose-100 dark:bg-rose-900/30 text-rose-600 dark:text-rose-400 px-1 py-0.5 rounded inline-block max-w-[120px] truncate align-bottom"
                title={tag}
              >
                {tag}
              </span>
            ))}
          </div>
        )}

        {refData.analysis_status && (
          <div className="mt-1">
            <span
              className={`text-[8px] px-1 py-0.5 rounded ${
                refData.analysis_status === 'COMPLETED'
                  ? 'bg-green-100 text-green-600 dark:bg-green-900/30 dark:text-green-400'
                  : refData.analysis_status === 'FAILED'
                  ? 'bg-red-100 text-red-600 dark:bg-red-900/30 dark:text-red-400'
                  : 'bg-yellow-100 text-yellow-600 dark:bg-yellow-900/30 dark:text-yellow-400'
              }`}
            >
              {refData.analysis_status}
            </span>
          </div>
        )}

        {refData.analysis_status !== 'COMPLETED' && (refData.analysis_excerpt || refData.analysis_error) && (
          <div className="mt-1 space-y-0.5">
            {refData.analysis_failure_stage && (
              <div className="text-[7px] uppercase tracking-wide text-amber-600 dark:text-amber-400">
                {refData.analysis_failure_stage.replace(/_/g, ' ')}
              </div>
            )}
            <div
              className="text-[9px] leading-3 text-gray-500 dark:text-gray-400 line-clamp-3"
              title={refData.analysis_excerpt || refData.analysis_error}
            >
              {refData.analysis_excerpt || refData.analysis_error}
            </div>
          </div>
        )}

        {(refData.analysis_profile || refData.schema_version) && (
          <div className="flex gap-1 mt-0.5 flex-wrap">
            {refData.analysis_profile && (
              <span className="text-[7px] bg-purple-100 dark:bg-purple-900/30 text-purple-600 dark:text-purple-400 px-1 py-0 rounded">
                {refData.analysis_profile === 'full' ? 'visual_anatomy' : refData.analysis_profile}
              </span>
            )}
            {refData.schema_version && (
              <span className="text-[7px] bg-cyan-100 dark:bg-cyan-900/30 text-cyan-600 dark:text-cyan-400 px-1 py-0 rounded">
                v{refData.schema_version}
              </span>
            )}
          </div>
        )}

        <div className="mt-1 space-y-0.5">
          <div className="text-[8px] text-gray-300 dark:text-gray-600 font-mono truncate" title={refData.reference_id}>
            ref:{refData.reference_id.replace('ref_', '').slice(0, 8)}
          </div>
          {refData.task_id && (
            <div className="text-[8px] text-gray-300 dark:text-gray-600 font-mono truncate" title={refData.task_id}>
              task:{refData.task_id.slice(0, 8)}
            </div>
          )}
        </div>
      </div>

      <div className="absolute top-1 right-1 opacity-0 group-hover:opacity-100 transition-opacity flex gap-1">
        <button
          onClick={(e) => { e.stopPropagation(); onAddToTraining(refData.reference_id); }}
          className="p-1 bg-black/50 rounded text-white hover:bg-emerald-500 transition-colors"
          title="Add to training candidate"
        >
          <Plus className="w-3 h-3" />
        </button>
        <button
          onClick={(e) => { e.stopPropagation(); onViewDetail(refData.reference_id); }}
          className="p-1 bg-black/50 rounded text-white hover:bg-blue-500 transition-colors"
          title="View analysis detail"
        >
          <Eye className="w-3 h-3" />
        </button>
        {instagramTarget && (
          <button
            onClick={(e) => {
              e.stopPropagation();
              openInstagramExternalTarget(instagramTarget);
            }}
            className="p-1 bg-black/50 rounded text-white hover:bg-purple-500 transition-colors"
            title={instagramTitle}
          >
            <ExternalLink className="w-3 h-3" />
          </button>
        )}
        <button
          onClick={(e) => { e.stopPropagation(); onDelete(refData.reference_id); }}
          className="p-1 bg-black/50 rounded text-white hover:bg-red-500 transition-colors"
          title="Delete reference"
        >
          <Trash2 className="w-3 h-3" />
        </button>
      </div>
    </div>
  );
}, (prevProps, nextProps) => (
  prevProps.refData === nextProps.refData &&
  prevProps.apiUrl === nextProps.apiUrl &&
  prevProps.workspaceId === nextProps.workspaceId &&
  prevProps.selected === nextProps.selected &&
  prevProps.onToggleSelect === nextProps.onToggleSelect &&
  prevProps.onViewDetail === nextProps.onViewDetail &&
  prevProps.onAddToTraining === nextProps.onAddToTraining &&
  prevProps.onDelete === nextProps.onDelete
));

export default function ReferencesPanel({ workspaceId, apiUrl = '' }: ReferencesPanelProps) {
  // Analysis detail modal
  const [detailRef, setDetailRef] = useState<any>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const detailInstagramTarget = useMemo(() => {
    if (!detailRef) return null;
    return getReferenceInstagramTarget({
      source_handle: detailRef.source_handle,
      source_shortcode: detailRef.source_shortcode,
    });
  }, [detailRef]);
  const detailPermalinkUrl = useMemo(
    () => buildInstagramPostUrl(detailRef?.source_shortcode),
    [detailRef],
  );

  const handleViewDetail = useCallback(async (refId: string) => {
    setDetailLoading(true);
    try {
      const res = await fetch(`${apiUrl}/api/v1/ig/references/${refId}/detail?workspace_id=${workspaceId}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setDetailRef(await res.json());
    } catch (e) {
      console.error('[RefPanel] Detail fetch failed:', e);
    } finally {
      setDetailLoading(false);
    }
  }, [apiUrl, workspaceId]);

  const [references, setReferences] = useState<ReferenceEntry[]>([]);
  const [totalReferences, setTotalReferences] = useState(0);
  const [counts, setCounts] = useState<ReferenceCounts>({
    total: 0,
    completed: 0,
    running: 0,
    pending: 0,
    failed: 0,
  });
  const [facets, setFacets] = useState<ReferenceFacets>({
    source_handles: [],
    tags: [],
    analysis_profiles: [],
    training_readiness_values: [],
    training_lane_hint_values: [],
    training_style_tag_values: [],
    training_quality_flag_values: [],
    identity_cluster_hint_values: [],
    look_state_hint_values: [],
    source_handle_options: [],
    tag_options: [],
    analysis_profile_options: [],
    training_readiness_options: [],
    training_lane_hint_options: [],
    training_style_tag_options: [],
    training_quality_flag_options: [],
    identity_cluster_hint_options: [],
    look_state_hint_options: [],
  });
  const [viewState, setViewState] = useState<ViewState>('loading');
  const [errorMessage, setErrorMessage] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
  const [debouncedSearchQuery, setDebouncedSearchQuery] = useState('');
  const [filterHandle, setFilterHandle] = useState('');
  const [filterTag, setFilterTag] = useState('');
  const [filterStatus, setFilterStatus] = useState('');
  const [filterProject, setFilterProject] = useState('');
  const [loadingMore, setLoadingMore] = useState(false);
  
  // V2.0 Hard Filters
  const [filterLocation, setFilterLocation] = useState('');
  const [filterShotType, setFilterShotType] = useState('');
  const [filterFocal, setFilterFocal] = useState('');
  const [filterAperture, setFilterAperture] = useState('');
  const [filterDof, setFilterDof] = useState('');
  const [filterLightTemp, setFilterLightTemp] = useState('');
  const [filterTrainingReadiness, setFilterTrainingReadiness] = useState('');
  const [filterTrainingLaneHint, setFilterTrainingLaneHint] = useState('');
  const [filterTrainingStyleTag, setFilterTrainingStyleTag] = useState('');
  const [filterTrainingQualityFlag, setFilterTrainingQualityFlag] = useState('');
  const [filterIdentityClusterHint, setFilterIdentityClusterHint] = useState('');
  const [filterLookStateHint, setFilterLookStateHint] = useState('');

  // Multi-select state
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [batchRetrying, setBatchRetrying] = useState(false);
  const [batchResult, setBatchResult] = useState<string>('');
  const [batchProfile, setBatchProfile] = useState('visual_anatomy');
  const [batchFilterStatus, setBatchFilterStatus] = useState('FAILED');
  const [batchAction, setBatchAction] = useState<'retry' | 'carousel' | 'training'>('retry');
  const [trainingModalOpen, setTrainingModalOpen] = useState(false);
  const [trainingModalReferences, setTrainingModalReferences] = useState<ReferenceEntry[]>([]);

  // Provenance filters
  const [filterProfile, setFilterProfile] = useState('');

  // Sort
  const [sortBy, setSortBy] = useState('analyzed_latest');
  const [filterSchemaVersion, setFilterSchemaVersion] = useState('');

  // Projects
  const [projects, setProjects] = useState<ProjectItem[]>([]);

  // Fetch projects for filter
  useEffect(() => {
    (async () => {
      try {
        const res = await fetch(`${apiUrl}/api/v1/workspaces/${workspaceId}/projects?state=active`);
        if (res.ok) {
          const data = await res.json();
          setProjects(data.projects || data || []);
        }
      } catch { /* ignore */ }
    })();
  }, [workspaceId, apiUrl]);

  // Pin form state (smart account input)
  const [showPinForm, setShowPinForm] = useState(false);
  const [pinAccountInput, setPinAccountInput] = useState('');
  const [pinPostCount, setPinPostCount] = useState(100);
  const [pinning, setPinning] = useState(false);
  const [pinStartSlow, setPinStartSlow] = useState(false);
  const [pinError, setPinError] = useState('');
  const [pinNotice, setPinNotice] = useState('');
  const [pinSuccess, setPinSuccess] = useState('');
  const referencesRef = useRef<ReferenceEntry[]>([]);
  const facetsRef = useRef<ReferenceFacets>({
    source_handles: [],
    tags: [],
    analysis_profiles: [],
    training_readiness_values: [],
    training_lane_hint_values: [],
    training_style_tag_values: [],
    training_quality_flag_values: [],
    identity_cluster_hint_values: [],
    look_state_hint_values: [],
    source_handle_options: [],
    tag_options: [],
    analysis_profile_options: [],
    training_readiness_options: [],
    training_lane_hint_options: [],
    training_style_tag_options: [],
    training_quality_flag_options: [],
    identity_cluster_hint_options: [],
    look_state_hint_options: [],
  });
  const scrollContainerRef = useRef<HTMLDivElement | null>(null);
  const [gridScrollParent, setGridScrollParent] = useState<HTMLDivElement | null>(null);
  const endSentinelRef = useRef<HTMLDivElement | null>(null);
  const loadingMoreRef = useRef(false);
  const hasMoreRef = useRef(false);
  const currentQueryKeyRef = useRef('');
  const requestSeqRef = useRef(0);
  const latestAppliedRequestIdRef = useRef(0);
  const latestRequestIdByQueryKeyRef = useRef<Map<string, number>>(new Map());
  const inflightRequestsRef = useRef<Map<number, AbortController>>(new Map());
  const blockingNonAppendRequestIdRef = useRef<number | null>(null);
  const headRefreshInFlightRef = useRef(false);
  const deferredBackgroundRefreshModeRef = useRef<Extract<ReferenceFetchMode, 'refresh_loaded' | 'refresh_head'> | null>(null);
  const fetchReferencesRef = useRef<((mode?: ReferenceFetchMode, isBackgroundRefresh?: boolean) => Promise<ReferenceFetchResult>) | null>(null);
  const fetchFacetsRef = useRef<(() => Promise<void>) | null>(null);
  const facetsRefreshTimerRef = useRef<number | null>(null);

  useEffect(() => {
    referencesRef.current = references;
  }, [references]);

  useEffect(() => {
    facetsRef.current = facets;
  }, [facets]);

  const handleScrollContainerRef = useCallback((node: HTMLDivElement | null) => {
    scrollContainerRef.current = node;
    setGridScrollParent(node);
  }, []);

  useEffect(() => {
    loadingMoreRef.current = loadingMore;
  }, [loadingMore]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setDebouncedSearchQuery(searchQuery.trim());
    }, 250);
    return () => window.clearTimeout(timer);
  }, [searchQuery]);

  const queryStateKey = useMemo(() => JSON.stringify({
    workspaceId,
    search: debouncedSearchQuery,
    filterHandle,
    filterTag,
    filterStatus,
    filterProject,
    filterProfile,
    filterSchemaVersion,
    sortBy,
    filterLocation,
    filterShotType,
    filterFocal,
    filterAperture,
    filterDof,
    filterLightTemp,
    filterTrainingReadiness,
    filterTrainingLaneHint,
    filterTrainingStyleTag,
    filterTrainingQualityFlag,
    filterIdentityClusterHint,
    filterLookStateHint,
  }), [
    workspaceId,
    debouncedSearchQuery,
    filterHandle,
    filterTag,
    filterStatus,
    filterProject,
    filterProfile,
    filterSchemaVersion,
    sortBy,
    filterLocation,
    filterShotType,
    filterFocal,
    filterAperture,
    filterDof,
    filterLightTemp,
    filterTrainingReadiness,
    filterTrainingLaneHint,
    filterTrainingStyleTag,
    filterTrainingQualityFlag,
    filterIdentityClusterHint,
    filterLookStateHint,
  ]);

  const referencesCacheKey = useMemo(
    () => `${apiUrl || 'local'}::${queryStateKey}`,
    [apiUrl, queryStateKey],
  );

  useEffect(() => {
    currentQueryKeyRef.current = queryStateKey;
    deferredBackgroundRefreshModeRef.current = null;
    withReferencesDebugStore((store) => {
      store.currentQueryKey = queryStateKey;
      store.currentSortBy = sortBy;
      store.latestStartedRequestId = requestSeqRef.current;
      store.latestAppliedRequestId = latestAppliedRequestIdRef.current;
    });
  }, [queryStateKey, sortBy]);

  useEffect(() => {
    const cachedList = ENABLE_REFERENCES_PANEL_CACHE
      ? referencesListCache.get(referencesCacheKey)
      : null;
    if (cachedList) {
      referencesRef.current = cachedList.references;
      hasMoreRef.current = cachedList.hasMore;
      setReferences(cachedList.references);
      setTotalReferences(cachedList.totalReferences);
      setCounts(cachedList.counts);
      setViewState(cachedList.viewState);
      setErrorMessage('');
    } else {
      // When switching to a new uncached query, clear the previous query immediately
      // so the UI never shows stale cards under the new filter selection.
      referencesRef.current = [];
      hasMoreRef.current = true;
      loadingMoreRef.current = false;
      setReferences([]);
      setSelectedIds(new Set());
      setTotalReferences(0);
      setCounts({
        total: 0,
        completed: 0,
        running: 0,
        pending: 0,
        failed: 0,
      });
      setLoadingMore(false);
      setViewState('loading');
      setErrorMessage('');
    }

    const cachedFacets = ENABLE_REFERENCES_PANEL_CACHE
      ? referencesFacetsCache.get(referencesCacheKey)
      : null;
    if (cachedFacets) {
      facetsRef.current = cachedFacets;
      setFacets(cachedFacets);
    } else if (!cachedList) {
      const emptyFacets: ReferenceFacets = {
        source_handles: [],
        tags: [],
        analysis_profiles: [],
        training_readiness_values: [],
        training_lane_hint_values: [],
        training_style_tag_values: [],
        training_quality_flag_values: [],
        identity_cluster_hint_values: [],
        look_state_hint_values: [],
        source_handle_options: [],
        tag_options: [],
        analysis_profile_options: [],
        training_readiness_options: [],
        training_lane_hint_options: [],
        training_style_tag_options: [],
        training_quality_flag_options: [],
        identity_cluster_hint_options: [],
        look_state_hint_options: [],
      };
      facetsRef.current = emptyFacets;
      setFacets(emptyFacets);
    }
  }, [referencesCacheKey]);

  const appendCommonFilters = useCallback((qs: URLSearchParams) => {
    qs.set('workspace_id', workspaceId);
    if (debouncedSearchQuery) qs.set('search', debouncedSearchQuery);
    if (filterHandle) qs.set('source_handle', filterHandle);
    if (filterTag) qs.set('tags', filterTag);
    if (filterProject) qs.set('project_id', filterProject);
    if (filterStatus) qs.set('analysis_status', filterStatus);
    if (filterProfile) qs.set('analysis_profile', filterProfile);
    if (filterSchemaVersion) qs.set('schema_version', filterSchemaVersion);

    if (filterLocation) qs.set('location', filterLocation);
    if (filterShotType) qs.set('shot_type', filterShotType);
    if (filterFocal) {
      if (filterFocal.startsWith('class:')) {
        qs.set('focal_class', filterFocal.replace('class:', ''));
      } else {
        qs.set('focal_mm', filterFocal);
      }
    }
    if (filterAperture) qs.set('aperture', filterAperture);
    if (filterDof) qs.set('dof', filterDof);
    if (filterLightTemp) qs.set('light_temp', filterLightTemp);
    if (filterTrainingReadiness) qs.set('training_readiness', filterTrainingReadiness);
    if (filterTrainingLaneHint) qs.set('training_lane_hint', filterTrainingLaneHint);
    if (filterTrainingStyleTag) qs.set('training_style_tag', filterTrainingStyleTag);
    if (filterTrainingQualityFlag) qs.set('training_quality_flag', filterTrainingQualityFlag);
    if (filterIdentityClusterHint) qs.set('identity_cluster_hint', filterIdentityClusterHint);
    if (filterLookStateHint) qs.set('look_state_hint', filterLookStateHint);
  }, [
    workspaceId,
    debouncedSearchQuery,
    filterHandle,
    filterTag,
    filterProject,
    filterStatus,
    filterProfile,
    filterSchemaVersion,
    filterLocation,
    filterShotType,
    filterFocal,
    filterAperture,
    filterDof,
    filterLightTemp,
    filterTrainingReadiness,
    filterTrainingLaneHint,
    filterTrainingStyleTag,
    filterTrainingQualityFlag,
    filterIdentityClusterHint,
    filterLookStateHint,
  ]);

  const buildReferencesQuery = useCallback((offset: number, limit: number) => {
    const cappedLimit = Math.min(limit, 200);
    const qs = new URLSearchParams();
    qs.set('offset', String(offset));
    qs.set('limit', String(cappedLimit));
    qs.set('sort_by', sortBy);
    qs.set('include_counts', 'false');
    appendCommonFilters(qs);
    return qs;
  }, [appendCommonFilters, sortBy]);

  const buildFacetsQuery = useCallback(() => {
    const qs = new URLSearchParams();
    appendCommonFilters(qs);
    return qs;
  }, [appendCommonFilters]);

  const fetchFacets = useCallback(async () => {
    try {
      const res = await fetch(`${apiUrl}/api/v1/ig/references/facets?${buildFacetsQuery().toString()}`);
      if (!res.ok) throw new Error(`HTTP Error ${res.status}`);
      const data = await res.json();
      const nextFacets = {
        source_handles: Array.isArray(data.source_handles) ? data.source_handles : [],
        tags: Array.isArray(data.tags) ? data.tags : [],
        analysis_profiles: Array.isArray(data.analysis_profiles) ? data.analysis_profiles : [],
        training_readiness_values: Array.isArray(data.training_readiness_values) ? data.training_readiness_values : [],
        training_lane_hint_values: Array.isArray(data.training_lane_hint_values) ? data.training_lane_hint_values : [],
        training_style_tag_values: Array.isArray(data.training_style_tag_values) ? data.training_style_tag_values : [],
        training_quality_flag_values: Array.isArray(data.training_quality_flag_values) ? data.training_quality_flag_values : [],
        identity_cluster_hint_values: Array.isArray(data.identity_cluster_hint_values) ? data.identity_cluster_hint_values : [],
        look_state_hint_values: Array.isArray(data.look_state_hint_values) ? data.look_state_hint_values : [],
        source_handle_options: normalizeFacetOptions(data.source_handle_options, data.source_handles),
        tag_options: normalizeFacetOptions(data.tag_options, data.tags),
        analysis_profile_options: normalizeFacetOptions(data.analysis_profile_options, data.analysis_profiles),
        training_readiness_options: normalizeFacetOptions(data.training_readiness_options, data.training_readiness_values),
        training_lane_hint_options: normalizeFacetOptions(data.training_lane_hint_options, data.training_lane_hint_values),
        training_style_tag_options: normalizeFacetOptions(data.training_style_tag_options, data.training_style_tag_values),
        training_quality_flag_options: normalizeFacetOptions(data.training_quality_flag_options, data.training_quality_flag_values),
        identity_cluster_hint_options: normalizeFacetOptions(data.identity_cluster_hint_options, data.identity_cluster_hint_values),
        look_state_hint_options: normalizeFacetOptions(data.look_state_hint_options, data.look_state_hint_values),
      };
      if (ENABLE_REFERENCES_PANEL_CACHE) {
        referencesFacetsCache.set(referencesCacheKey, nextFacets);
      }
      facetsRef.current = nextFacets;
      setFacets(nextFacets);
    } catch {
      const emptyFacets = {
        source_handles: [],
        tags: [],
        analysis_profiles: [],
        training_readiness_values: [],
        training_lane_hint_values: [],
        training_style_tag_values: [],
        training_quality_flag_values: [],
        identity_cluster_hint_values: [],
        look_state_hint_values: [],
        source_handle_options: [],
        tag_options: [],
        analysis_profile_options: [],
        training_readiness_options: [],
        training_lane_hint_options: [],
        training_style_tag_options: [],
        training_quality_flag_options: [],
        identity_cluster_hint_options: [],
        look_state_hint_options: [],
      };
      if (ENABLE_REFERENCES_PANEL_CACHE) {
        referencesFacetsCache.set(referencesCacheKey, emptyFacets);
      }
      facetsRef.current = emptyFacets;
      setFacets(emptyFacets);
    }
  }, [apiUrl, buildFacetsQuery, referencesCacheKey]);

  const scheduleFacetsRefresh = useCallback((delayMs = 350) => {
    if (facetsRefreshTimerRef.current) {
      clearTimeout(facetsRefreshTimerRef.current);
    }
    facetsRefreshTimerRef.current = window.setTimeout(() => {
      facetsRefreshTimerRef.current = null;
      void fetchFacetsRef.current?.();
    }, delayMs);
  }, []);

  const fetchReferences = useCallback(async (
    mode: ReferenceFetchMode = 'reset',
    isBackgroundRefresh = false,
  ): Promise<ReferenceFetchResult> => {
    const cachedList = ENABLE_REFERENCES_PANEL_CACHE
      ? referencesListCache.get(referencesCacheKey)
      : null;
    const loadedCount = referencesRef.current.length;
    const offset = mode === 'append' ? loadedCount : 0;
    let limit = REFERENCES_PAGE_SIZE;
    if (mode === 'refresh_loaded') {
      limit = Math.max(loadedCount, REFERENCES_PAGE_SIZE);
    } else if (mode === 'refresh_head') {
      limit = BACKGROUND_REFRESH_PAGE_SIZE;
    }

    if (mode === 'append') {
      if (loadingMoreRef.current || !hasMoreRef.current) {
        return { outcome: 'dropped' };
      }
      loadingMoreRef.current = true;
      setLoadingMore(true);
    } else if (mode === 'refresh_head' && headRefreshInFlightRef.current) {
      return { outcome: 'dropped' };
    } else if (!isBackgroundRefresh && !cachedList && loadedCount === 0) {
      setViewState('loading');
    }

    const requestId = requestSeqRef.current + 1;
    requestSeqRef.current = requestId;
    const requestQueryKey = queryStateKey;
    const requestSortBy = sortBy;
    const controller = new AbortController();
    if (mode === 'refresh_head') {
      headRefreshInFlightRef.current = true;
    }
    if (mode !== 'append') {
      blockingNonAppendRequestIdRef.current = requestId;
    }

    latestRequestIdByQueryKeyRef.current.set(requestQueryKey, requestId);
    if (mode !== 'append') {
      inflightRequestsRef.current.forEach((inflightController) => inflightController.abort());
      inflightRequestsRef.current.clear();
    }
    inflightRequestsRef.current.set(requestId, controller);

    recordReferencesDebugEvent({
      ts: new Date().toISOString(),
      type: 'start',
      requestId,
      mode,
      sortBy: requestSortBy,
      offset,
      limit,
      queryKey: requestQueryKey,
      currentQueryKey: currentQueryKeyRef.current,
    }, {
      currentSortBy: requestSortBy,
      currentQueryKey: currentQueryKeyRef.current,
      latestStartedRequestId: requestId,
      latestAppliedRequestId: latestAppliedRequestIdRef.current,
    });

    setErrorMessage('');
    try {
      const res = await fetch(
        `${apiUrl}/api/v1/ig/references/?${buildReferencesQuery(offset, limit).toString()}`,
        { signal: controller.signal },
      );
      if (!res.ok) throw new Error(`HTTP Error ${res.status}`);
      const data = await res.json();
      const nextPage = Array.isArray(data.references) ? data.references : [];
      const nextTotal = Number(data.total || 0);
      const nextCounts = {
        total: nextTotal,
        completed: 0,
        running: 0,
        pending: 0,
        failed: 0,
        ...(data.counts || {}),
      };

      const latestRequestId = latestRequestIdByQueryKeyRef.current.get(requestQueryKey);
      if (requestQueryKey !== currentQueryKeyRef.current) {
        recordReferencesDebugEvent({
          ts: new Date().toISOString(),
          type: 'drop_stale_query',
          requestId,
          mode,
          sortBy: requestSortBy,
          offset,
          limit,
          queryKey: requestQueryKey,
          currentQueryKey: currentQueryKeyRef.current,
          message: 'query_key_mismatch',
        });
        return { outcome: 'dropped' };
      }
      if (latestRequestId !== requestId) {
        recordReferencesDebugEvent({
          ts: new Date().toISOString(),
          type: 'drop_stale_request',
          requestId,
          mode,
          sortBy: requestSortBy,
          offset,
          limit,
          queryKey: requestQueryKey,
          currentQueryKey: currentQueryKeyRef.current,
          message: `latest_request_id=${latestRequestId ?? 'none'}`,
        });
        return { outcome: 'dropped' };
      }

      setTotalReferences(nextTotal);
      setCounts(nextCounts);
      if (mode === 'append') {
        setReferences((prev) => {
          const seen = new Set(prev.map((entry) => entry.reference_id));
          const merged = [...prev];
          nextPage.forEach((entry: ReferenceEntry) => {
            if (!seen.has(entry.reference_id)) {
              seen.add(entry.reference_id);
              merged.push(entry);
            }
          });
          hasMoreRef.current = merged.length < nextTotal;
          return merged;
        });
      } else if (mode === 'refresh_head') {
        setReferences((prev) => {
          const merged = mergeRefHeadWindow(prev, nextPage, nextTotal);
          hasMoreRef.current = merged.length < nextTotal;
          return merged;
        });
      } else {
        hasMoreRef.current = nextPage.length < nextTotal;
        setReferences(nextPage);
        if (mode === 'reset') {
          setSelectedIds(new Set());
        }
      }

      if (ENABLE_REFERENCES_PANEL_CACHE) {
        referencesListCache.set(referencesCacheKey, {
          references: mode === 'append'
            ? (() => {
                const seen = new Set(referencesRef.current.map((entry) => entry.reference_id));
                const merged = [...referencesRef.current];
                nextPage.forEach((entry: ReferenceEntry) => {
                  if (!seen.has(entry.reference_id)) {
                    seen.add(entry.reference_id);
                    merged.push(entry);
                  }
                });
                return merged;
              })()
            : mode === 'refresh_head'
              ? mergeRefHeadWindow(referencesRef.current, nextPage, nextTotal)
              : nextPage,
          totalReferences: nextTotal,
          counts: nextCounts,
          viewState: nextTotal > 0 ? 'loaded' : 'empty',
          hasMore: hasMoreRef.current,
        });
      }

      latestAppliedRequestIdRef.current = requestId;
      recordReferencesDebugEvent({
        ts: new Date().toISOString(),
        type: 'apply',
        requestId,
        mode,
        sortBy: requestSortBy,
        offset,
        limit,
        queryKey: requestQueryKey,
        currentQueryKey: currentQueryKeyRef.current,
      }, {
        currentSortBy: requestSortBy,
        currentQueryKey: currentQueryKeyRef.current,
        latestStartedRequestId: requestSeqRef.current,
        latestAppliedRequestId: requestId,
      });
      setViewState(nextTotal > 0 ? 'loaded' : 'empty');
      if (mode === 'reset' || mode === 'refresh_head') {
        scheduleFacetsRefresh(mode === 'reset' ? 250 : 500);
      }
      return {
        outcome: 'applied',
        headReferenceId: nextPage[0]?.reference_id ?? null,
        total: nextTotal,
      };
    } catch (e: any) {
      if (e?.name === 'AbortError') {
        recordReferencesDebugEvent({
          ts: new Date().toISOString(),
          type: 'abort',
          requestId,
          mode,
          sortBy: requestSortBy,
          offset,
          limit,
          queryKey: requestQueryKey,
          currentQueryKey: currentQueryKeyRef.current,
        });
        return { outcome: 'aborted' };
      }
      const message = e?.message || String(e);
      recordReferencesDebugEvent({
        ts: new Date().toISOString(),
        type: 'error',
        requestId,
        mode,
        sortBy: requestSortBy,
        offset,
        limit,
        queryKey: requestQueryKey,
        currentQueryKey: currentQueryKeyRef.current,
        message,
      });
      if (!isBackgroundRefresh && mode !== 'append') {
        setErrorMessage(message);
        setViewState('error');
      }
      return {
        outcome: 'error',
        errorMessage: message,
      };
    } finally {
      inflightRequestsRef.current.delete(requestId);
      if (mode === 'append') {
        loadingMoreRef.current = false;
        setLoadingMore(false);
      } else {
        if (mode === 'refresh_head') {
          headRefreshInFlightRef.current = false;
        }
        if (blockingNonAppendRequestIdRef.current === requestId) {
          blockingNonAppendRequestIdRef.current = null;
        }
      }
    }
  }, [apiUrl, buildReferencesQuery, queryStateKey, referencesCacheKey, scheduleFacetsRefresh, sortBy]);

  useEffect(() => {
    fetchReferencesRef.current = fetchReferences;
  }, [fetchReferences]);

  useEffect(() => {
    fetchFacetsRef.current = fetchFacets;
  }, [fetchFacets]);

  useEffect(() => () => {
    inflightRequestsRef.current.forEach((controller) => controller.abort());
    inflightRequestsRef.current.clear();
    if (facetsRefreshTimerRef.current) {
      clearTimeout(facetsRefreshTimerRef.current);
      facetsRefreshTimerRef.current = null;
    }
  }, []);
  const lifecycleRefreshTimerRef = useRef<number | null>(null);
  const lifecycleRefreshTokenRef = useRef(0);

  const scheduleWorkspaceRefreshAttempt = useCallback((token: number, attempt: number, delayMs: number) => {
    if (lifecycleRefreshTimerRef.current) clearTimeout(lifecycleRefreshTimerRef.current);
    lifecycleRefreshTimerRef.current = window.setTimeout(() => {
      void (async () => {
        if (token !== lifecycleRefreshTokenRef.current) return;
        const container = scrollContainerRef.current;
        if (container && container.scrollTop > BACKGROUND_REFRESH_NEAR_TOP_THRESHOLD_PX) {
          deferredBackgroundRefreshModeRef.current = 'refresh_loaded';
          return;
        }
        const result = await fetchReferencesRef.current?.('refresh_loaded', true);
        if (token !== lifecycleRefreshTokenRef.current) return;
        if (result?.outcome === 'applied') {
          scheduleFacetsRefresh(500);
          return;
        }
        if (result?.outcome === 'error' && attempt < 2) {
          const retryDelayMs = attempt === 0 ? 2_000 : 4_000;
          scheduleWorkspaceRefreshAttempt(token, attempt + 1, retryDelayMs);
        }
      })();
    }, delayMs);
  }, [scheduleFacetsRefresh]);

  const scheduleWorkspaceRefresh = useCallback(() => {
    const token = lifecycleRefreshTokenRef.current + 1;
    lifecycleRefreshTokenRef.current = token;
    scheduleWorkspaceRefreshAttempt(token, 0, 1_500);
  }, [scheduleWorkspaceRefreshAttempt]);

  useEffect(() => () => {
    lifecycleRefreshTokenRef.current += 1;
    if (lifecycleRefreshTimerRef.current) {
      clearTimeout(lifecycleRefreshTimerRef.current);
      lifecycleRefreshTimerRef.current = null;
    }
  }, []);

  useIGWorkspaceEvents({
    workspaceId,
    apiUrl,
    onEvent: (_event, metadata) => {
      if (!metadata.terminal) return;
      if (!hasIGRefreshHint(metadata, 'references')) return;
      scheduleWorkspaceRefresh();
    },
  });

  useEffect(() => {
    void fetchReferences('reset');
  }, [fetchReferences]);

  useEffect(() => {
    if (!shouldSyncHeadForSort(sortBy)) return undefined;
    if (viewState !== 'loaded') return undefined;

    const syncHead = () => {
      if (typeof document !== 'undefined' && document.visibilityState === 'hidden') return;
      if (loadingMoreRef.current) return;
      if (headRefreshInFlightRef.current) return;
      const container = scrollContainerRef.current;
      if (container && container.scrollTop > BACKGROUND_REFRESH_NEAR_TOP_THRESHOLD_PX) {
        if (deferredBackgroundRefreshModeRef.current !== 'refresh_loaded') {
          deferredBackgroundRefreshModeRef.current = 'refresh_head';
        }
        return;
      }
      void fetchReferencesRef.current?.('refresh_head', true);
    };

    const intervalId = window.setInterval(syncHead, ANALYZED_LATEST_HEAD_SYNC_INTERVAL_MS);
    const handleWindowFocus = () => {
      syncHead();
    };
    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible') {
        syncHead();
      }
    };

    window.addEventListener('focus', handleWindowFocus);
    document.addEventListener('visibilitychange', handleVisibilityChange);

    return () => {
      window.clearInterval(intervalId);
      window.removeEventListener('focus', handleWindowFocus);
      document.removeEventListener('visibilitychange', handleVisibilityChange);
    };
  }, [sortBy, viewState, queryStateKey]);

  const gridResetKey = queryStateKey;

  const handleEndReached = useCallback(() => {
    if (
      viewState !== 'loaded'
      || !hasMoreRef.current
      || loadingMoreRef.current
      || headRefreshInFlightRef.current
      || blockingNonAppendRequestIdRef.current !== null
    ) {
      return;
    }
    void fetchReferences('append', true);
  }, [fetchReferences, viewState]);

  const handleReferencesScroll = useCallback((event: React.UIEvent<HTMLDivElement>) => {
    const container = event.currentTarget;
    if (container.scrollTop <= BACKGROUND_REFRESH_NEAR_TOP_THRESHOLD_PX) {
      const deferredMode = deferredBackgroundRefreshModeRef.current;
      if (deferredMode && !loadingMoreRef.current && !headRefreshInFlightRef.current) {
        deferredBackgroundRefreshModeRef.current = null;
        void fetchReferencesRef.current?.(deferredMode, true);
      }
    }
    if (isScrollContainerNearEnd(container)) {
      handleEndReached();
    }
  }, [handleEndReached]);

  const checkViewportEndReached = useCallback(() => {
    if (
      viewState !== 'loaded'
      || !hasMoreRef.current
      || loadingMoreRef.current
      || headRefreshInFlightRef.current
      || blockingNonAppendRequestIdRef.current !== null
    ) {
      return;
    }
    const container = scrollContainerRef.current;
    if (!container) return;
    if (isScrollContainerNearEnd(container)) {
      handleEndReached();
    }
  }, [handleEndReached, viewState]);

  useEffect(() => {
    if (viewState !== 'loaded') return;
    const container = scrollContainerRef.current;
    if (!container) return;
    if (container.clientHeight <= 0) return;
    if (container.scrollHeight <= container.clientHeight + 1) {
      handleEndReached();
    }
  }, [viewState, references.length, totalReferences, handleEndReached]);

  useEffect(() => {
    if (viewState !== 'loaded') return;
    const handleWindowResize = () => {
      checkViewportEndReached();
    };
    window.addEventListener('resize', handleWindowResize);
    const rafId = window.requestAnimationFrame(() => {
      checkViewportEndReached();
    });
    return () => {
      window.cancelAnimationFrame(rafId);
      window.removeEventListener('resize', handleWindowResize);
    };
  }, [viewState, references.length, totalReferences, checkViewportEndReached]);

  useEffect(() => {
    if (viewState !== 'loaded' || typeof IntersectionObserver === 'undefined') return;
    const root = scrollContainerRef.current;
    const target = endSentinelRef.current;
    if (!target || !root) return;

    const observer = new IntersectionObserver((entries) => {
      if (entries.some((entry) => entry.isIntersecting)) {
        handleEndReached();
      }
    }, {
      root,
      rootMargin: `${AUTO_APPEND_NEAR_END_THRESHOLD_PX}px 0px`,
      threshold: 0,
    });

    observer.observe(target);
    return () => {
      observer.disconnect();
    };
  }, [handleEndReached, viewState, references.length, totalReferences]);

  const handleDelete = useCallback(async (refId: string) => {
    try {
      await fetch(`${apiUrl}/api/v1/ig/references/${refId}?workspace_id=${workspaceId}`, {
        method: 'DELETE',
      });
      void fetchReferences('refresh_loaded', true);
    } catch (e) {
      console.error('Delete failed:', e);
    }
  }, [apiUrl, fetchReferences, workspaceId]);

  const handlePin = async () => {
    const raw = pinAccountInput.trim();
    if (!raw) {
      setPinError('Account URL or handle is required');
      return;
    }
    // Extract handle: support URL or plain handle
    let handle = raw;
    const urlMatch = raw.match(/instagram\.com\/([\w.]+)/);
    if (urlMatch) handle = urlMatch[1];
    handle = handle.replace(/^@/, '').replace(/\/$/, '');
    if (!handle) {
      setPinError('Could not parse handle from input');
      return;
    }

    setPinning(true);
    setPinStartSlow(false);
    setPinError('');
    setPinNotice('');
    setPinSuccess('');
    let softTimeoutId: number | null = null;
    let hardTimeoutId: number | null = null;
    try {
      const submittedAt = Date.now();
      const qs = new URLSearchParams({
        playbook_code: 'ig_batch_pin_references',
        workspace_id: workspaceId,
        profile_id: 'default-user',
      });
      applyExecutionBackendHint(qs, workspaceId);
      const controller = new AbortController();
      softTimeoutId = window.setTimeout(() => {
        setPinStartSlow(true);
        setPinNotice('Starting batch pin… first request can take around 10-20 seconds.');
      }, BATCH_PIN_START_SOFT_TIMEOUT_MS);
      hardTimeoutId = window.setTimeout(() => controller.abort(), BATCH_PIN_START_HARD_TIMEOUT_MS);
      const res = await fetch(`${apiUrl}/api/v1/playbooks/execute/start?${qs.toString()}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        signal: controller.signal,
        body: JSON.stringify({
          inputs: injectWorkspaceIGBrowserProfileInputs(workspaceId, {
            workspace_id: workspaceId,
            target_handle: handle,
            target_count: pinPostCount,
          }),
        }),
      });
      if (softTimeoutId !== null) window.clearTimeout(softTimeoutId);
      if (hardTimeoutId !== null) window.clearTimeout(hardTimeoutId);
      const raw = await res.text();
      const data = parseJsonSafely<any>(raw) || {};
      if (!res.ok) {
        const msg = typeof data.detail === 'string' ? data.detail
          : Array.isArray(data.detail) ? data.detail.map((d: any) => d.msg || JSON.stringify(d)).join('; ')
          : raw || JSON.stringify(data.detail || data);
        throw new Error(msg);
      }
      const executionId = typeof data.execution_id === 'string' ? data.execution_id : '';
      if (typeof window !== 'undefined' && executionId) {
        window.dispatchEvent(new CustomEvent('mindscape:execution_started', {
          detail: {
            workspaceId,
            executionId,
            playbookCode: 'ig_batch_pin_references',
            startedAt: new Date(submittedAt).toISOString(),
            inputs: {
              workspace_id: workspaceId,
              target_handle: handle,
              target_count: pinPostCount,
            },
          },
        }));
      }
      setPinStartSlow(false);
      setPinNotice('');
      setPinSuccess(`Batch pin started for @${handle} (${pinPostCount} posts)`);
      setPinAccountInput('');
      setTimeout(() => setPinSuccess(''), 5000);
    } catch (e: any) {
      if (e instanceof DOMException && e.name === 'AbortError') {
        let confirmedExecutionId = '';
        for (let attempt = 0; attempt < BATCH_PIN_SUMMARY_POLL_ATTEMPTS; attempt += 1) {
          try {
            const summaryRes = await fetch(
              `${apiUrl}/api/v1/ig/insights/latest-batch-pin-summary?workspace_id=${encodeURIComponent(workspaceId)}&handle=${encodeURIComponent(handle)}`,
              {
                headers: { 'Content-Type': 'application/json' },
              },
            );
            if (summaryRes.ok) {
              const summaryRaw = await summaryRes.text();
              const summary = parseJsonSafely<LatestBatchPinSummaryResponse>(summaryRaw);
              const latestAttempt = summary?.latest_attempt;
              const createdAtMs = latestAttempt?.created_at ? Date.parse(latestAttempt.created_at) : Number.NaN;
              if (
                latestAttempt?.execution_id
                && Number.isFinite(createdAtMs)
                && createdAtMs >= submittedAt - 5_000
              ) {
                confirmedExecutionId = latestAttempt.execution_id;
                if (typeof window !== 'undefined') {
                  window.dispatchEvent(new CustomEvent('mindscape:execution_started', {
                    detail: {
                      workspaceId,
                      executionId: latestAttempt.execution_id,
                      playbookCode: 'ig_batch_pin_references',
                      startedAt: latestAttempt.created_at,
                      inputs: {
                        workspace_id: workspaceId,
                        target_handle: handle,
                        target_count: pinPostCount,
                      },
                    },
                  }));
                }
                setPinSuccess(`Batch pin queued for @${handle} (${pinPostCount} posts)`);
                setPinStartSlow(false);
                setPinNotice('');
                setPinAccountInput('');
                setTimeout(() => setPinSuccess(''), 5000);
                return;
              }
            }
          } catch (summaryError) {
            console.warn('Batch pin fallback summary lookup failed:', summaryError);
          }
          if (attempt < BATCH_PIN_SUMMARY_POLL_ATTEMPTS - 1) {
            await sleep(BATCH_PIN_SUMMARY_POLL_INTERVAL_MS);
          }
        }
        setPinError(
          confirmedExecutionId
            ? `Batch pin queued for @${handle}, but the start response timed out`
            : 'Batch pin start timed out before the UI received confirmation. Check Run Logs and retry if no queue item appears.',
        );
      } else {
        setPinError(e.message || 'Batch pin failed');
      }
    } finally {
      if (softTimeoutId !== null) window.clearTimeout(softTimeoutId);
      if (hardTimeoutId !== null) window.clearTimeout(hardTimeoutId);
      setPinStartSlow(false);
      setPinning(false);
    }
  };

  // Batch retry handler
  const handleBatchRetry = async () => {
    if (selectedIds.size === 0) return;
    setBatchRetrying(true);
    setBatchResult('');
    try {
      if (batchFilterStatus === 'COMPLETED') {
        const selectedReferences = references.filter((ref) => selectedIds.has(ref.reference_id));
        const statusCounts = selectedReferences.reduce<Record<string, number>>((acc, ref) => {
          const status = (ref.analysis_status || 'NONE').toUpperCase();
          acc[status] = (acc[status] || 0) + 1;
          return acc;
        }, {});
        const statusLines = Object.entries(statusCounts)
          .sort((a, b) => a[0].localeCompare(b[0]))
          .map(([status, count]) => `- ${status}: ${count}`)
          .join('\n');
        const confirmed = window.confirm(
          [
            `Re-analyze ${selectedIds.size} selected references?`,
            '',
            'Selected status distribution:',
            statusLines || '- NONE: 0',
            '',
            'Only COMPLETED references will be enqueued.',
            'Existing analysis will remain visible until the new run succeeds.',
          ].join('\n'),
        );
        if (!confirmed) {
          return;
        }
      }

      const res = await fetch(`${apiUrl}/api/v1/ig/references/batch-retry-analysis`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(
          {
            workspace_id: workspaceId,
            reference_ids: Array.from(selectedIds),
            filter_status: batchFilterStatus,
            analysis_profile: batchProfile,
          },
        ),
      });
      const data = await res.json();
      setBatchResult(`Enqueued: ${data.total_enqueued}, Skipped: ${data.total_skipped}, Errors: ${data.total_errors}`);
      setSelectedIds(new Set());
      setTimeout(() => { void fetchReferencesRef.current?.('refresh_loaded', true); }, 1500);
    } catch (e: any) {
      setBatchResult(`Error: ${e.message}`);
    } finally {
      setBatchRetrying(false);
    }
  };

  // Batch carousel fetch handler
  const handleBatchCarouselFetch = async () => {
    if (selectedIds.size === 0) return;
    setBatchRetrying(true);
    setBatchResult('');
    try {
      const selectedReferences = references.filter((r: ReferenceEntry) => selectedIds.has(r.reference_id));
      const shortcodes = selectedReferences
        .filter((r: ReferenceEntry) => r.source_shortcode)
        .map((r: ReferenceEntry) => r.source_shortcode.replace(/_c\d+$/, ''))
        .filter((v: string, i: number, a: string[]) => a.indexOf(v) === i);

      if (shortcodes.length === 0) {
        setBatchResult('No shortcodes found in selected references');
        return;
      }

      const sourceHandles = Array.from(
        new Set(
          selectedReferences
            .map((r: ReferenceEntry) => (r.source_handle || '').trim())
            .filter(Boolean),
        ),
      );
      const sourceHandle = sourceHandles.length === 1
        ? sourceHandles[0].replace(/^@/, '')
        : undefined;

      const inputs = injectWorkspaceIGBrowserProfileInputs(workspaceId, {
        workspace_id: workspaceId,
        shortcodes,
        ...(sourceHandle ? { source_handle: sourceHandle } : {}),
        tags: ['post_detail'],
      });
      const qs = new URLSearchParams({
        playbook_code: 'ig_pin_post_detail',
        workspace_id: workspaceId,
        profile_id: 'default-user',
        auto_execute: 'true',
      });
      applyExecutionBackendHint(qs, workspaceId);

      const res = await fetch(`${apiUrl}/api/v1/playbooks/execute/start?${qs.toString()}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ inputs }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
      const executionId = typeof data.execution_id === 'string' ? data.execution_id : '';
      setBatchResult(`Queued carousel fetch for ${shortcodes.length} post${shortcodes.length === 1 ? '' : 's'}${executionId ? ` · ${executionId.slice(0, 8)}` : ''}`);
      setSelectedIds(new Set());
      if (typeof window !== 'undefined' && executionId) {
        window.dispatchEvent(new CustomEvent('mindscape:execution_started', {
          detail: {
            workspaceId,
            executionId,
            playbookCode: 'ig_pin_post_detail',
            startedAt: new Date().toISOString(),
            inputs,
          },
        }));
      }
      setTimeout(() => { void fetchReferencesRef.current?.('refresh_loaded', true); }, 1500);
    } catch (e: any) {
      setBatchResult(`Error: ${e.message}`);
    } finally {
      setBatchRetrying(false);
    }
  };

  const handleOpenTrainingModal = useCallback((refs: ReferenceEntry[]) => {
    if (!refs.length) return;
    setBatchResult('');
    setTrainingModalReferences(refs);
    setTrainingModalOpen(true);
  }, []);

  const handleBatchAddToTraining = useCallback(() => {
    if (selectedIds.size === 0) return;
    const selectedReferences = referencesRef.current.filter((ref) => selectedIds.has(ref.reference_id));
    handleOpenTrainingModal(selectedReferences);
  }, [handleOpenTrainingModal, selectedIds]);

  const handleSingleAddToTraining = useCallback((referenceId: string) => {
    const reference = referencesRef.current.find((item) => item.reference_id === referenceId);
    if (!reference) return;
    handleOpenTrainingModal([reference]);
  }, [handleOpenTrainingModal]);

  const handleTrainingModalClose = useCallback(() => {
    setTrainingModalOpen(false);
    setTrainingModalReferences([]);
  }, []);

  const handleTrainingIntakeSuccess = useCallback((payload: {
    mode: 'create' | 'append';
    candidateId: string;
    candidateDisplayName: string;
    addedCount: number;
    dedupedCount: number;
    trainingIntentCount: number;
    trainingIntentAddedCount: number;
    trainingIntentDedupedCount: number;
  }) => {
    const nextMessage = payload.mode === 'create'
      ? `Draft candidate ${payload.candidateDisplayName} created · refs ${payload.addedCount} · intents ${payload.trainingIntentCount} · intake only, no auto-dispatch`
      : `Appended to ${payload.candidateDisplayName} · refs +${payload.addedCount} (${payload.dedupedCount} deduped) · intents +${payload.trainingIntentAddedCount} (${payload.trainingIntentDedupedCount} deduped) · intake only, no auto-dispatch`;
    setBatchResult(nextMessage);
    setSelectedIds((prev) => {
      if (prev.size === 0) return prev;
      const next = new Set(prev);
      trainingModalReferences.forEach((reference) => next.delete(reference.reference_id));
      return next;
    });
    setTrainingModalOpen(false);
    setTrainingModalReferences([]);
  }, [trainingModalReferences]);

  const toggleSelect = useCallback((refId: string) => {
    setSelectedIds(prev => {
      const next = new Set(prev);
      if (next.has(refId)) next.delete(refId); else next.add(refId);
      return next;
    });
  }, []);

  const toggleSelectAll = useCallback(() => {
    if (selectedIds.size === references.length) setSelectedIds(new Set());
    else setSelectedIds(new Set(references.map(r => r.reference_id)));
  }, [references, selectedIds.size]);

  const sourceHandleOptions = useMemo(() => {
    return buildFacetOptions(facets.source_handle_options, filterHandle);
  }, [facets.source_handle_options, filterHandle]);

  const tagOptions = useMemo(() => {
    return buildFacetOptions(facets.tag_options, filterTag);
  }, [facets.tag_options, filterTag]);

  const analysisProfiles = useMemo(() => {
    const values = new Set(facets.analysis_profiles);
    if (filterProfile) values.add(filterProfile);
    return Array.from(values).sort();
  }, [facets.analysis_profiles, filterProfile]);

  const trainingLaneHintOptions = useMemo(() => {
    return buildFacetOptions(facets.training_lane_hint_options, filterTrainingLaneHint);
  }, [facets.training_lane_hint_options, filterTrainingLaneHint]);

  const trainingStyleTagOptions = useMemo(() => {
    return buildFacetOptions(facets.training_style_tag_options, filterTrainingStyleTag);
  }, [facets.training_style_tag_options, filterTrainingStyleTag]);

  const trainingQualityFlagOptions = useMemo(() => {
    return buildFacetOptions(facets.training_quality_flag_options, filterTrainingQualityFlag);
  }, [facets.training_quality_flag_options, filterTrainingQualityFlag]);

  const identityClusterHintOptions = useMemo(() => {
    return buildFacetOptions(facets.identity_cluster_hint_options, filterIdentityClusterHint);
  }, [facets.identity_cluster_hint_options, filterIdentityClusterHint]);

  const lookStateHintOptions = useMemo(() => {
    return buildFacetOptions(facets.look_state_hint_options, filterLookStateHint);
  }, [facets.look_state_hint_options, filterLookStateHint]);

  return (
    <div className="flex flex-col h-full">
      {/* Header & Search */}
      <div className="flex items-center gap-3 px-4 py-3 border-b border-gray-200 dark:border-gray-700">
        <div className="flex items-center gap-2 shrink-0">
          <Pin className="w-4 h-4 text-rose-500" />
          <h2 className="text-sm font-semibold text-gray-800 dark:text-gray-200">References</h2>
        </div>
        
        <div className="relative flex-1 max-w-sm ml-auto">
          <Search className="absolute left-2 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-gray-400" />
          <input
            type="text"
            placeholder="Search references..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-8 pr-7 py-1.5 text-xs bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-md focus:outline-none focus:ring-1 focus:ring-rose-400 transition-shadow"
          />
          {searchQuery && (
            <button
              onClick={() => setSearchQuery('')}
              className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 transition-colors"
            >
              <span className="text-sm font-medium">✕</span>
            </button>
          )}
        </div>

        <button
          onClick={() => setShowPinForm(!showPinForm)}
          className={`p-1.5 rounded-md transition-colors shrink-0 ${showPinForm ? 'bg-rose-100 text-rose-600 dark:bg-rose-900/30 dark:text-rose-400' : 'text-gray-400 hover:text-rose-500 hover:bg-gray-100 dark:hover:bg-gray-800'}`}
          title="Pin new reference"
        >
          <Plus className="w-4 h-4" />
        </button>
      </div>

      {/* Pin form (collapsible) — Smart account batch pin */}
      {showPinForm && (
        <div className="px-4 py-3 space-y-2 border-b border-rose-200 dark:border-rose-800/50 bg-rose-50/50 dark:bg-rose-950/20">
          <div className="flex items-center gap-1 text-xs font-medium text-rose-600 dark:text-rose-400 mb-1">
            <Pin className="w-3 h-3" />
            Batch Pin from Account
          </div>
          <div className="flex gap-2">
            <input
              type="text"
              placeholder="IG account URL or @handle"
              value={pinAccountInput}
              onChange={(e) => { setPinAccountInput(e.target.value); setPinError(''); }}
              className="flex-1 px-2.5 py-1.5 text-xs bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-md focus:outline-none focus:ring-1 focus:ring-rose-400"
            />
            <select
              value={pinPostCount}
              onChange={(e) => setPinPostCount(Number(e.target.value))}
              className="px-2 py-1.5 text-xs bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-md focus:outline-none focus:ring-1 focus:ring-rose-400"
            >
              <option value={100}>100 posts</option>
              <option value={300}>300 posts</option>
              <option value={500}>500 posts</option>
            </select>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={handlePin}
              disabled={pinning || !pinAccountInput.trim()}
              className="flex items-center gap-1 px-3 py-1.5 text-xs font-medium text-white bg-rose-500 hover:bg-rose-600 disabled:bg-gray-300 disabled:text-gray-500 dark:disabled:bg-gray-700 rounded-md transition-colors"
            >
              {pinning ? <Loader2 className="w-3 h-3 animate-spin" /> : <Pin className="w-3 h-3" />}
              {pinning ? (pinStartSlow ? 'Still starting...' : 'Starting...') : 'Batch Pin'}
            </button>
            {pinError && <span className="text-[10px] text-red-500">{pinError}</span>}
            {!pinError && pinNotice && <span className="text-[10px] text-amber-600 dark:text-amber-400">{pinNotice}</span>}
            {pinSuccess && <span className="text-[10px] text-green-600 dark:text-green-400">{pinSuccess}</span>}
          </div>
        </div>
      )}

      {/* Filters (Search moved to header) */}
      <div className="px-4 py-2 flex flex-wrap gap-2 border-b border-gray-100 dark:border-gray-800">
        <FacetPicker
          allLabel="All accounts"
          value={filterHandle}
          options={sourceHandleOptions}
          onChange={setFilterHandle}
          searchPlaceholder="Search source accounts..."
          browseLabel={`Browse ${sourceHandleOptions.length} source accounts already pinned in references`}
        />
        <FacetPicker
          allLabel="All tags"
          value={filterTag}
          options={tagOptions}
          onChange={setFilterTag}
          searchPlaceholder="Search tags..."
          browseLabel={`Browse ${tagOptions.length} tags across pinned references`}
        />
        <select
          value={filterStatus}
          onChange={(e) => setFilterStatus(e.target.value)}
          className="min-w-0 text-xs bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded px-2 py-1 truncate flex-[1_1_15%]"
        >
          <option value="">All status</option>
          <option value="COMPLETED">✅ Completed</option>
          <option value="RUNNING">▶ Running</option>
          <option value="PENDING">⏳ Pending</option>
          <option value="FAILED">❌ Failed</option>
        </select>
        <select
          value={filterProfile}
          onChange={(e) => setFilterProfile(e.target.value)}
          className="min-w-0 text-xs bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded px-2 py-1 truncate flex-[1_1_15%]"
        >
          <option value="">All profiles</option>
          {analysisProfiles.map((profile) => (
            <option key={profile} value={profile}>{profile}</option>
          ))}
        </select>
        
        <select
          value={sortBy}
          onChange={(e) => setSortBy(e.target.value)}
          className="min-w-0 text-xs bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded px-2 py-1 truncate flex-[1_1_15%]"
        >
          <option value="analyzed_latest">🔬 Latest analyzed</option>
          <option value="analyzed_oldest">🔬 Earliest analyzed</option>
          <option value="pending_latest">⏳ Latest pending</option>
          <option value="pending_oldest">⏳ Earliest pending</option>
          <option value="newest">⏱ Newest pinned</option>
          <option value="oldest">⏱ Oldest pinned</option>
          <option value="handle_az">🔤 Handle A→Z</option>
          <option value="handle_za">🔤 Handle Z→A</option>
          <option value="status">📊 Status</option>
        </select>
        {projects.length > 0 && (
          <select
            value={filterProject}
            onChange={(e) => setFilterProject(e.target.value)}
            className="min-w-0 text-xs bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded px-2 py-1 truncate flex-[1_1_15%]"
          >
            <option value="">All projects</option>
            {projects.map((p) => (
              <option key={p.id} value={p.id}>{p.title}</option>
            ))}
          </select>
        )}

        {/* Force line break for visual filters */}
        <div className="w-full h-0"></div>

        {/* V2.0 Visual Content Filters */}
        <select
          value={filterLocation}
          onChange={(e) => setFilterLocation(e.target.value)}
          className="min-w-0 text-xs bg-indigo-50 dark:bg-indigo-900/20 text-indigo-700 dark:text-indigo-300 border border-indigo-200 dark:border-indigo-800 rounded px-2 py-1 truncate flex-[1_1_15%]"
        >
          <option value="">All Locations</option>
          <option value="indoor">Indoor</option>
          <option value="outdoor">Outdoor</option>
          <option value="studio">Studio</option>
        </select>
        <select
          value={filterShotType}
          onChange={(e) => setFilterShotType(e.target.value)}
          className="min-w-0 text-xs bg-indigo-50 dark:bg-indigo-900/20 text-indigo-700 dark:text-indigo-300 border border-indigo-200 dark:border-indigo-800 rounded px-2 py-1 truncate flex-[1_1_15%]"
        >
          <option value="">All Shot Types</option>
          <option value="extreme-close-up">Extreme Close-up</option>
          <option value="close-up">Close-up</option>
          <option value="medium-close-up">Medium Close-up</option>
          <option value="medium">Medium</option>
          <option value="medium-wide">Medium Wide</option>
          <option value="wide">Wide</option>
          <option value="extreme-wide">Extreme Wide</option>
        </select>
        <select
          value={filterFocal}
          onChange={(e) => setFilterFocal(e.target.value)}
          className="min-w-0 text-xs bg-indigo-50 dark:bg-indigo-900/20 text-indigo-700 dark:text-indigo-300 border border-indigo-200 dark:border-indigo-800 rounded px-2 py-1 truncate flex-[1_1_15%]"
        >
          <option value="">All Focal Lengths</option>
          <optgroup label="Ultra-wide">
            <option value="class:ultra-wide">Any Ultra-wide</option>
            <option value="12mm">12mm</option>
            <option value="14mm">14mm</option>
            <option value="16mm">16mm</option>
            <option value="20mm">20mm</option>
          </optgroup>
          <optgroup label="Wide">
            <option value="class:wide">Any Wide</option>
            <option value="24mm">24mm</option>
            <option value="28mm">28mm</option>
            <option value="35mm">35mm</option>
          </optgroup>
          <optgroup label="Standard">
            <option value="class:standard">Any Standard</option>
            <option value="40mm">40mm</option>
            <option value="50mm">50mm</option>
          </optgroup>
          <optgroup label="Short Telephoto">
            <option value="class:short-telephoto">Any Short Telephoto</option>
            <option value="85mm">85mm</option>
            <option value="105mm">105mm</option>
          </optgroup>
          <optgroup label="Telephoto">
            <option value="class:telephoto">Any Telephoto</option>
            <option value="135mm">135mm</option>
            <option value="200mm">200mm</option>
          </optgroup>
        </select>
        <select
          value={filterAperture}
          onChange={(e) => setFilterAperture(e.target.value)}
          className="min-w-0 text-xs bg-indigo-50 dark:bg-indigo-900/20 text-indigo-700 dark:text-indigo-300 border border-indigo-200 dark:border-indigo-800 rounded px-2 py-1 truncate flex-[1_1_15%]"
        >
          <option value="">All Aperture</option>
          <option value="f/1.4">f/1.4</option>
          <option value="f/2.8">f/2.8</option>
          <option value="f/4">f/4</option>
          <option value="f/5.6">f/5.6</option>
          <option value="f/8">f/8</option>
          <option value="f/11">f/11</option>
          <option value="f/16">f/16</option>
        </select>
        <select
          value={filterDof}
          onChange={(e) => setFilterDof(e.target.value)}
          className="min-w-0 text-xs bg-indigo-50 dark:bg-indigo-900/20 text-indigo-700 dark:text-indigo-300 border border-indigo-200 dark:border-indigo-800 rounded px-2 py-1 truncate flex-[1_1_15%]"
        >
          <option value="">All DoF</option>
          <option value="shallow">Shallow</option>
          <option value="moderate">Moderate</option>
          <option value="deep">Deep</option>
        </select>
        <select
          value={filterLightTemp}
          onChange={(e) => setFilterLightTemp(e.target.value)}
          className="min-w-0 text-xs bg-indigo-50 dark:bg-indigo-900/20 text-indigo-700 dark:text-indigo-300 border border-indigo-200 dark:border-indigo-800 rounded px-2 py-1 truncate flex-[1_1_15%]"
        >
          <option value="">All Light Temp</option>
          <option value="warm">Warm</option>
          <option value="neutral">Neutral</option>
          <option value="cool">Cool</option>
        </select>

        <div className="w-full h-0"></div>

        <select
          value={filterTrainingReadiness}
          onChange={(e) => setFilterTrainingReadiness(e.target.value)}
          className="min-w-0 text-xs bg-emerald-50 dark:bg-emerald-900/20 text-emerald-700 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-800 rounded px-2 py-1 truncate flex-[1_1_15%]"
        >
          <option value="">All Readiness</option>
          <option value="keep">Keep</option>
          <option value="review">Review</option>
          <option value="reject">Reject</option>
        </select>
        <FacetPicker
          allLabel="All lane hints"
          value={filterTrainingLaneHint}
          options={trainingLaneHintOptions}
          onChange={setFilterTrainingLaneHint}
          searchPlaceholder="Search lane hints..."
          browseLabel={`Browse ${trainingLaneHintOptions.length} training lane hints`}
        />
        <FacetPicker
          allLabel="All style tags"
          value={filterTrainingStyleTag}
          options={trainingStyleTagOptions}
          onChange={setFilterTrainingStyleTag}
          searchPlaceholder="Search style tags..."
          browseLabel={`Browse ${trainingStyleTagOptions.length} training style tags`}
        />
        <FacetPicker
          allLabel="All quality flags"
          value={filterTrainingQualityFlag}
          options={trainingQualityFlagOptions}
          onChange={setFilterTrainingQualityFlag}
          searchPlaceholder="Search quality flags..."
          browseLabel={`Browse ${trainingQualityFlagOptions.length} training quality flags`}
        />
        <FacetPicker
          allLabel="All identity clusters"
          value={filterIdentityClusterHint}
          options={identityClusterHintOptions}
          onChange={setFilterIdentityClusterHint}
          searchPlaceholder="Search identity clusters..."
          browseLabel={`Browse ${identityClusterHintOptions.length} identity cluster hints`}
        />
        <FacetPicker
          allLabel="All look states"
          value={filterLookStateHint}
          options={lookStateHintOptions}
          onChange={setFilterLookStateHint}
          searchPlaceholder="Search look states..."
          browseLabel={`Browse ${lookStateHintOptions.length} look state hints`}
        />
      </div>

      {/* Batch action bar */}
      {selectedIds.size > 0 && (
        <div className="flex items-center gap-2 px-4 py-2 bg-blue-50 dark:bg-blue-900/20 border-b border-blue-200 dark:border-blue-800">
          <button onClick={toggleSelectAll} className="text-xs text-blue-600 dark:text-blue-400 hover:underline">
            {selectedIds.size === references.length ? 'Deselect all' : 'Select all'}
          </button>
          <span className="text-xs text-blue-500">{selectedIds.size} selected</span>
          <div className="ml-auto flex gap-2 items-center">
            {/* Action type selector */}
            <select
              value={batchAction}
              onChange={(e) => setBatchAction(e.target.value as 'retry' | 'carousel' | 'training')}
              className="text-xs bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded px-2 py-1 font-medium"
            >
              <option value="retry">🔄 Retry / Re-analyze</option>
              <option value="carousel">🎠 Fetch Carousel</option>
              <option value="training">🧪 Add To Training</option>
            </select>

            {/* Retry-specific options */}
            {batchAction === 'retry' && (
              <>
                <select
                  value={batchFilterStatus}
                  onChange={(e) => setBatchFilterStatus(e.target.value)}
                  className="text-xs bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded px-2 py-1"
                >
                  <option value="FAILED">Retry FAILED</option>
                  <option value="PENDING">Retry PENDING</option>
                  <option value="COMPLETED">Re-analyze COMPLETED</option>
                </select>
                <select
                  value={batchProfile}
                  onChange={(e) => setBatchProfile(e.target.value)}
                  className="text-xs bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded px-2 py-1"
                >
                  <option value="visual_anatomy">visual_anatomy</option>
                  <option value="aesthetic_core">aesthetic_core</option>
                  <option value="portrait_deep">portrait_deep</option>
                  <option value="cinematic">cinematic</option>
                  <option value="product_material">product_material</option>
                </select>
              </>
            )}

            {/* Execute button */}
            <button
              onClick={
                batchAction === 'carousel'
                  ? handleBatchCarouselFetch
                  : batchAction === 'training'
                    ? handleBatchAddToTraining
                    : handleBatchRetry
              }
              disabled={batchRetrying && batchAction !== 'training'}
              className={`flex items-center gap-1 px-3 py-1 text-xs font-medium text-white rounded disabled:opacity-50 transition-colors ${
                batchAction === 'carousel'
                  ? 'bg-purple-500 hover:bg-purple-600'
                  : batchAction === 'training'
                    ? 'bg-emerald-500 hover:bg-emerald-600'
                  : 'bg-blue-500 hover:bg-blue-600'
              }`}
            >
              {batchRetrying && batchAction !== 'training'
                ? <Loader2 className="w-3 h-3 animate-spin" />
                : batchAction === 'training'
                  ? <Plus className="w-3 h-3" />
                : batchAction === 'carousel'
                  ? <Layers className="w-3 h-3" />
                  : <RefreshCw className="w-3 h-3" />
              }
              {batchAction === 'training'
                ? 'Add To Training'
                : batchAction === 'carousel'
                ? 'Fetch Carousel'
                : batchFilterStatus === 'COMPLETED' ? 'Re-analyze' : 'Retry Analysis'
              }
            </button>
            <button onClick={() => setSelectedIds(new Set())} className="px-2 py-1 text-xs text-gray-500 hover:text-gray-700 dark:hover:text-gray-300">Cancel</button>
          </div>
        </div>
      )}
      {batchResult && (
        <div className="px-4 py-1.5 text-[10px] bg-green-50 dark:bg-green-900/20 text-green-700 dark:text-green-400 border-b border-green-200 dark:border-green-800">
          {batchResult}
        </div>
      )}

      {/* Content area */}
      <div
        ref={handleScrollContainerRef}
        data-testid="references-scroll-container"
        className="flex-1 min-h-0 overflow-y-auto"
        onScroll={handleReferencesScroll}
      >
        {viewState === 'loading' && (
          <div className="flex flex-col items-center justify-center h-40 text-gray-400">
            <Loader2 className="w-6 h-6 animate-spin mb-2" />
            <span className="text-xs">Loading references...</span>
          </div>
        )}

        {viewState === 'error' && (
          <div className="flex flex-col items-center justify-center h-40 text-red-400">
            <AlertCircle className="w-6 h-6 mb-2" />
            <span className="text-xs">{errorMessage}</span>
            <button
              onClick={() => { void fetchReferences('reset'); }}
              className="mt-2 text-xs text-rose-500 hover:underline"
            >
              Retry
            </button>
          </div>
        )}

        {viewState === 'empty' && (
          <div className="flex flex-col items-center justify-center h-40 text-gray-400">
            <FolderOpen className="w-8 h-8 mb-2 opacity-50" />
            <span className="text-xs">No references pinned yet</span>
            <button
              onClick={() => setShowPinForm(true)}
              className="mt-2 flex items-center gap-1 text-xs text-rose-500 hover:text-rose-600 hover:underline"
            >
              <Plus className="w-3 h-3" /> Pin your first reference
            </button>
          </div>
        )}

        {viewState === 'loaded' && !trainingModalOpen && (
          <div key={gridResetKey}>
            <VirtuosoGrid
              data={references}
              customScrollParent={gridScrollParent ?? undefined}
              computeItemKey={(_index, ref) => ref.reference_id}
              endReached={handleEndReached}
              increaseViewportBy={{ top: 240, bottom: 480 }}
              overscan={{ main: 240, reverse: 120 }}
              listClassName="grid grid-cols-2 xl:grid-cols-4 gap-2 p-3 pb-4"
              itemClassName="min-w-0"
              itemContent={(_index, ref) => (
                <ReferenceGridCard
                  refData={ref}
                  apiUrl={apiUrl}
                  workspaceId={workspaceId}
                  selected={selectedIds.has(ref.reference_id)}
                  onToggleSelect={toggleSelect}
                  onViewDetail={handleViewDetail}
                  onAddToTraining={handleSingleAddToTraining}
                  onDelete={handleDelete}
                />
              )}
            />
            <div ref={endSentinelRef} data-testid="references-end-sentinel" className="h-px w-full" />
            <div className="px-3 pb-4 text-center text-xs text-gray-500 dark:text-gray-400">
              {loadingMore
                ? 'Loading more references...'
                : totalReferences > references.length
                  ? `Showing ${references.length} of ${totalReferences}`
                  : ''}
            </div>
          </div>
        )}

        {viewState === 'loaded' && trainingModalOpen && (
          <div className="flex h-40 flex-col items-center justify-center px-4 text-center text-xs text-gray-500 dark:text-gray-400">
            <Loader2 className="mb-2 h-5 w-5 animate-spin text-emerald-500" />
            <div>Training intake modal is open.</div>
            <div className="mt-1">Reference grid paused to keep intake requests responsive.</div>
          </div>
        )}
      </div>

      <BaseModal
        isOpen={!!detailRef}
        onClose={() => setDetailRef(null)}
        title="Analysis Detail"
        maxWidth="max-w-2xl"
      >
        {detailRef && (
          <div className="space-y-4">
            {/* Thumbnail */}
            {detailRef.reference_id && (
              <img
                src={getReferenceImageUrl(apiUrl, workspaceId, detailRef.reference_id)}
                className="w-full rounded-lg max-h-64 object-contain bg-gray-100 dark:bg-gray-900"
                alt="Reference"
              />
            )}

            {/* Vision Analysis */}
            <VisionAnalysisDetail
              detailRef={detailRef}
              imageUrl={detailRef.reference_id ? getReferenceImageUrl(apiUrl, workspaceId, detailRef.reference_id) : undefined}
            />

            {/* Carousel siblings */}
            {detailRef.carousel_total && detailRef.carousel_total > 1 && (
              <CarouselSiblings
                referenceId={detailRef.reference_id}
                workspaceId={workspaceId}
                apiUrl={apiUrl}
              />
            )}



            {/* Tags */}
            {(detailRef.tags?.length > 0 || detailRef.auto_tags?.length > 0) && (
              <div className="pt-3 border-t border-gray-200 dark:border-gray-700">
                <h4 className="text-xs font-medium text-gray-500 mb-2">Tags</h4>
                <div className="flex flex-wrap gap-1">
                  {detailRef.tags?.map((t: string) => (
                    <span key={`tag-${t}`} className="text-xs bg-rose-100 dark:bg-rose-900/30 text-rose-600 px-1.5 py-0.5 rounded">{t}</span>
                  ))}
                  {detailRef.auto_tags?.map((t: string) => (
                    <span key={`auto-${t}`} className="text-xs bg-blue-100 dark:bg-blue-900/30 text-blue-600 px-1.5 py-0.5 rounded">{t}</span>
                  ))}
                </div>
              </div>
            )}

            {/* IG Link */}
            {detailInstagramTarget && (
              <div className="pt-3 border-t border-gray-200 dark:border-gray-700">
                <a
                  href={detailInstagramTarget.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-xs text-purple-500 hover:text-purple-700 flex items-center gap-1"
                >
                  <ExternalLink className="w-3 h-3" />
                  View on Instagram
                </a>
                {detailInstagramTarget.mode === 'account' && detailPermalinkUrl && (
                  <a
                    href={detailPermalinkUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="mt-2 text-[11px] text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200 flex items-center gap-1"
                  >
                    <ExternalLink className="w-3 h-3" />
                    Open exact post permalink
                  </a>
                )}
              </div>
            )}
          </div>
        )}
      </BaseModal>

      <AddToTrainingCandidateModal
        isOpen={trainingModalOpen}
        onClose={handleTrainingModalClose}
        apiUrl={apiUrl}
        workspaceId={workspaceId}
        selectedReferences={trainingModalReferences}
        onSuccess={handleTrainingIntakeSuccess}
      />
    </div>
  );
}
