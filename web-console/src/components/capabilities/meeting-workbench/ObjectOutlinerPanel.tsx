import { Boxes } from 'lucide-react';

import type {
  AddressableObjectRef,
  AddressableObjectSummary,
  ObjectMeetingAttachResponse,
} from '@/lib/addressable-object-layer';
import type { GraphViewMode, MeetingNode, MeetingNodeStatus, MeetingTranslate } from './meetingWorkbenchTypes';
import type { MeetingMissingContext } from './meetingWorkbenchStatus';
import { isRecord, readString, safeMentionId } from './meetingWorkbenchUtils';

type OutlinerSectionId = 'target' | 'sources' | 'evidence' | 'constraints' | 'outputs' | 'review';

interface OutlinerItem {
  id: string;
  title: string;
  subtitle: string;
  status: MeetingNodeStatus;
  nodeId?: string;
  placeholder?: boolean;
}

const OUTLINER_SECTIONS: Array<{
  id: OutlinerSectionId;
  labelKey: Parameters<MeetingTranslate>[0];
}> = [
  { id: 'target', labelKey: 'meetingWorkbenchOutlinerTarget' },
  { id: 'sources', labelKey: 'meetingWorkbenchOutlinerSources' },
  { id: 'evidence', labelKey: 'meetingWorkbenchOutlinerEvidence' },
  { id: 'constraints', labelKey: 'meetingWorkbenchOutlinerConstraints' },
  { id: 'outputs', labelKey: 'meetingWorkbenchOutlinerOutputs' },
  { id: 'review', labelKey: 'meetingWorkbenchOutlinerReview' },
];

function outlinerStatusClass(status: MeetingNodeStatus, placeholder = false): string {
  if (placeholder) {
    return 'bg-slate-300 dark:bg-slate-700';
  }
  if (status === 'error' || status === 'blocked') {
    return 'bg-rose-500';
  }
  if (status === 'running') {
    return 'bg-amber-500';
  }
  if (status === 'context') {
    return 'bg-emerald-500';
  }
  return 'bg-blue-500';
}

function refKey(ref: AddressableObjectRef): string {
  return [ref.uri, ref.owner_pack, ref.object_kind, ref.object_id].filter(Boolean).join('|');
}

function refTitle(ref: AddressableObjectRef): string {
  return [ref.object_kind, ref.object_id].filter(Boolean).join(' ') || ref.uri || 'object';
}

function refSubtitle(ref: AddressableObjectRef): string {
  return [ref.owner_pack, ref.object_kind].filter(Boolean).join(' / ') || ref.uri || 'object';
}

function refItem(ref: AddressableObjectRef, role: string, nodeId?: string): OutlinerItem {
  return {
    id: `${role}-${safeMentionId(refKey(ref) || refTitle(ref))}`,
    title: refTitle(ref),
    subtitle: refSubtitle(ref),
    status: 'context',
    nodeId,
  };
}

function readRef(value: unknown): AddressableObjectRef | null {
  if (!isRecord(value)) {
    return null;
  }
  const ownerPack = readString(value.owner_pack);
  const objectKind = readString(value.object_kind);
  const objectId = readString(value.object_id);
  if (!ownerPack || !objectKind || !objectId) {
    return null;
  }
  return {
    uri: readString(value.uri) || `mindscape://${ownerPack}/${objectKind}/${objectId}`,
    owner_pack: ownerPack,
    object_kind: objectKind,
    object_id: objectId,
    workspace_id: readString(value.workspace_id) || undefined,
    version: readString(value.version) || undefined,
    selector: isRecord(value.selector) ? value.selector : undefined,
    source_surface: readString(value.source_surface) || undefined,
  };
}

function addItem(target: OutlinerItem[], seen: Set<string>, item: OutlinerItem) {
  if (seen.has(item.id)) {
    return;
  }
  seen.add(item.id);
  target.push(item);
}

function buildOutlinerSections({
  nodes,
  summary,
  attachResponse,
  t,
}: {
  nodes: MeetingNode[];
  summary: AddressableObjectSummary | null;
  attachResponse: ObjectMeetingAttachResponse | null;
  t: MeetingTranslate;
}): Record<OutlinerSectionId, OutlinerItem[]> {
  const sections: Record<OutlinerSectionId, OutlinerItem[]> = {
    target: [],
    sources: [],
    evidence: [],
    constraints: [],
    outputs: [],
    review: [],
  };
  const seen = new Set<string>();

  if (attachResponse?.target_ref) {
    addItem(sections.target, seen, refItem(attachResponse.target_ref, 'target'));
  }

  if (summary?.ref) {
    const sourceId = `source-${safeMentionId(refKey(summary.ref) || refTitle(summary.ref))}`;
    if (!seen.has(sourceId)) {
      seen.add(sourceId);
      addItem(sections.sources, seen, {
        ...refItem(summary.ref, 'source', 'object'),
        id: 'object',
        title: summary.title || refTitle(summary.ref),
        subtitle: refSubtitle(summary.ref),
      });
    }
  }

  attachResponse?.attachments.forEach((attachment) => {
    const role = readString(attachment.role);
    const item = refItem(attachment.ref, role);
    if (role === 'target') {
      addItem(sections.target, seen, item);
    } else if (role === 'evidence') {
      addItem(sections.evidence, seen, item);
    } else if (role === 'constraint' || role === 'baseline' || role === 'character') {
      addItem(sections.constraints, seen, item);
    } else {
      addItem(sections.sources, seen, item);
    }
  });

  nodes.forEach((node) => {
    const role = readString(node.metadata?.role);
    const ref = readRef(node.metadata?.ref);
    if (ref && role) {
      const item = refItem(ref, role, node.id);
      if (role === 'target') {
        addItem(sections.target, seen, item);
      } else if (role === 'evidence') {
        addItem(sections.evidence, seen, item);
      } else if (role === 'constraint' || role === 'baseline' || role === 'character') {
        addItem(sections.constraints, seen, item);
      } else if (role === 'output') {
        addItem(sections.outputs, seen, item);
      } else {
        addItem(sections.sources, seen, item);
      }
    }

    const targetRef = readRef(node.metadata?.target_ref);
    if (targetRef) {
      addItem(sections.target, seen, refItem(targetRef, 'target', node.id));
    }

    const proposalRef = readRef(node.metadata?.proposal_ref);
    if (proposalRef) {
      addItem(sections.review, seen, refItem(proposalRef, 'review', node.id));
    }

    if (node.lane === 'artifacts' || node.kind === 'artifact' || node.lane === 'outputs') {
      addItem(sections.outputs, seen, {
        id: `output-${node.id}`,
        title: node.title,
        subtitle: node.eyebrow,
        status: node.status,
        nodeId: node.id,
      });
    }
  });

  attachResponse?.staged_refs.forEach((ref) => addItem(sections.outputs, seen, refItem(ref, 'staged')));
  attachResponse?.review_routes.forEach((route, index) => {
    addItem(sections.review, seen, {
      id: `review-route-${safeMentionId(route)}-${index}`,
      title: t('meetingWorkbenchAttachmentReviewRoute'),
      subtitle: route,
      status: 'pending',
    });
  });

  if (sections.target.length === 0) {
    sections.target.push({
      id: 'missing-target',
      title: t('meetingWorkbenchMissingTarget'),
      subtitle: t('meetingWorkbenchMissingTargetDetail'),
      status: 'blocked',
      placeholder: true,
    });
  }

  return sections;
}

export function ObjectOutlinerPanel({
  graphViewMode,
  nodes,
  summary,
  attachResponse,
  selectedNodeId,
  activeMissingContext,
  onSelectNode,
  onSelectMissingContext,
  t,
}: {
  graphViewMode: GraphViewMode;
  nodes: MeetingNode[];
  summary: AddressableObjectSummary | null;
  attachResponse: ObjectMeetingAttachResponse | null;
  selectedNodeId: string;
  activeMissingContext: MeetingMissingContext | null;
  onSelectNode: (nodeId: string) => void;
  onSelectMissingContext: (context: MeetingMissingContext) => void;
  t: MeetingTranslate;
}) {
  if (graphViewMode !== 'work') {
    return null;
  }

  const sections = buildOutlinerSections({ nodes, summary, attachResponse, t });

  return (
    <aside
      className="hidden w-60 shrink-0 flex-col border-r border-slate-200 bg-white/95 dark:border-slate-800 dark:bg-slate-950/95 lg:flex"
      data-testid="meeting-object-outliner"
      aria-label={t('meetingWorkbenchObjectOutliner')}
    >
      <div className="flex h-9 shrink-0 items-center gap-2 border-b border-slate-200 px-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-slate-500 dark:border-slate-800 dark:text-slate-400">
        <Boxes className="h-3.5 w-3.5" aria-hidden="true" />
        {t('meetingWorkbenchObjectOutliner')}
      </div>
      <div className="min-h-0 flex-1 space-y-2 overflow-auto p-2">
        {OUTLINER_SECTIONS.map((section) => {
          const sectionItems = sections[section.id].slice(0, 8);
          return (
            <section key={section.id} data-testid={`meeting-object-outliner-section-${section.id}`}>
              <div className="mb-1 flex items-center justify-between gap-2 px-1 text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-400 dark:text-slate-500">
                <span>{t(section.labelKey)}</span>
                <span className="tabular-nums">{sectionItems.length}</span>
              </div>
              <div className="space-y-1">
                {sectionItems.length > 0 ? (
                  sectionItems.map((item) => {
                    const missingContext = item.id === 'missing-target' ? 'target' : null;
                    const selected = Boolean(item.nodeId)
                      ? item.nodeId === selectedNodeId
                      : Boolean(missingContext && missingContext === activeMissingContext);
                    return (
                      <button
                        key={item.id}
                        type="button"
                        onClick={() => {
                          if (item.nodeId) {
                            onSelectNode(item.nodeId);
                            return;
                          }
                          if (missingContext) {
                            onSelectMissingContext(missingContext);
                          }
                        }}
                        disabled={!item.nodeId && !missingContext}
                        className={`flex h-10 w-full min-w-0 items-center gap-2 rounded-md border px-2 text-left text-xs transition-colors ${
                          selected
                            ? item.placeholder
                              ? 'border-amber-300 bg-amber-50 text-amber-800 dark:border-amber-700 dark:bg-amber-950/40 dark:text-amber-200'
                              : 'border-blue-400 bg-blue-50 text-blue-800 dark:border-blue-600 dark:bg-blue-950/50 dark:text-blue-200'
                            : item.placeholder
                              ? 'border-dashed border-slate-200 bg-slate-50 text-slate-400 dark:border-slate-800 dark:bg-slate-900/60 dark:text-slate-500'
                              : 'border-slate-200 bg-white text-slate-700 hover:border-blue-200 hover:bg-blue-50/60 disabled:hover:border-slate-200 disabled:hover:bg-white dark:border-slate-800 dark:bg-slate-950 dark:text-slate-200 dark:hover:border-blue-800 dark:hover:bg-blue-950/30 dark:disabled:hover:border-slate-800 dark:disabled:hover:bg-slate-950'
                        }`}
                        data-testid={`meeting-object-outliner-node-${item.id}`}
                        aria-pressed={selected}
                        title={item.title}
                      >
                        <span className={`h-2 w-2 shrink-0 rounded-full ${outlinerStatusClass(item.status, item.placeholder)}`} />
                        <span className="min-w-0 flex-1">
                          <span className="block truncate font-medium">{item.title}</span>
                          <span className="block truncate text-[10px] opacity-60">{item.subtitle}</span>
                        </span>
                      </button>
                    );
                  })
                ) : (
                  <div className="rounded-md border border-dashed border-slate-200 px-2 py-2 text-xs text-slate-400 dark:border-slate-800 dark:text-slate-500">
                    {t('meetingWorkbenchEmpty')}
                  </div>
                )}
              </div>
            </section>
          );
        })}
      </div>
    </aside>
  );
}
