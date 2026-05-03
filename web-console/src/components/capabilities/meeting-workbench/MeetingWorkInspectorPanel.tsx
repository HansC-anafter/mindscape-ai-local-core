import type {
  AddressableObjectSummary,
  ObjectGraphProjection,
  ObjectMeetingAttachResponse,
} from '@/lib/addressable-object-layer';
import { MeetingRuntimeInspectorContent } from './MeetingRuntimeInspectorPanel';
import {
  collectObjectGuidanceCards,
  collectObjectGuidanceReviewAffordances,
  type ObjectGuidanceDisplayCard,
} from './meetingGraphObjectProjection';
import { addressableRefKey, formatKind, graphRefLabel } from './meetingGraphProjection';
import type { InspectorTab, MeetingCommandImpact, MeetingNode, MeetingTranslate, RuntimeInspectorSnapshot } from './meetingWorkbenchTypes';
import { readString } from './meetingWorkbenchUtils';

function StatTile({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-md border border-slate-200 p-2 dark:border-slate-800">
      <div className="text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-500">{label}</div>
      <div className="mt-1 text-sm font-semibold text-slate-900 dark:text-slate-100">{value}</div>
    </div>
  );
}

function getSelectedGuidanceCard(
  selectedNode: MeetingNode | null,
  guidanceCards: ObjectGuidanceDisplayCard[],
): ObjectGuidanceDisplayCard | null {
  const guidanceId = readString(selectedNode?.metadata?.guidance_id);
  if (!guidanceId) {
    return null;
  }
  const objectUri = readString(selectedNode?.metadata?.object_uri);
  return guidanceCards.find((card) => {
    const sameGuidance = card.id === guidanceId;
    const sameObject = !objectUri || card.projection.ref.uri === objectUri;
    return sameGuidance && sameObject;
  }) ?? null;
}

function GuidanceCommandBlock({
  card,
  t,
}: {
  card: ObjectGuidanceDisplayCard;
  t: MeetingTranslate;
}) {
  return (
    <>
      {card.command_template ? (
        <div className="mt-2 rounded border border-slate-200 bg-white px-2 py-1.5 font-mono text-[11px] text-slate-600 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-300">
          <span className="mr-1 font-sans font-semibold text-slate-400">{t('meetingWorkbenchCommandTemplate')}:</span>
          {card.command_template}
        </div>
      ) : null}
      {card.target_ref ? (
        <div className="mt-2 truncate text-[11px] text-slate-500 dark:text-slate-400">
          <span className="font-semibold">{t('meetingWorkbenchTargetRef')}:</span> {graphRefLabel(card.target_ref)}
        </div>
      ) : null}
      {card.proposal_ref ? (
        <div className="mt-1 truncate text-[11px] text-slate-500 dark:text-slate-400">
          <span className="font-semibold">{t('meetingWorkbenchProposalRef')}:</span> {graphRefLabel(card.proposal_ref)}
        </div>
      ) : null}
      {(card.required_roles || []).length > 0 ? (
        <div className="mt-1 truncate text-[11px] text-slate-500 dark:text-slate-400">
          <span className="font-semibold">{t('meetingWorkbenchRequiredContext')}:</span> {card.required_roles?.join(', ')}
        </div>
      ) : null}
    </>
  );
}

export function MeetingWorkInspectorContent({
  activeInspector,
  selectedNode,
  runtimeSnapshot,
  workspaceId,
  meetingId,
  summary,
  attachResponse,
  objectGraphProjections,
  objectGraphLoading,
  objectGraphError,
  commandImpact,
  t,
}: {
  activeInspector: InspectorTab;
  selectedNode: MeetingNode | null;
  runtimeSnapshot: RuntimeInspectorSnapshot;
  workspaceId: string;
  meetingId: string;
  summary: AddressableObjectSummary | null;
  attachResponse: ObjectMeetingAttachResponse | null;
  objectGraphProjections: ObjectGraphProjection[];
  objectGraphLoading: boolean;
  objectGraphError: string | null;
  commandImpact: MeetingCommandImpact | null;
  t: MeetingTranslate;
}) {
  if (activeInspector === 'object') {
    return (
      <div className="space-y-3" data-testid="meeting-work-summary-panel">
        <div className="rounded-md border border-slate-200 p-2 dark:border-slate-800">
          <div className="text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-500">{t('meetingWorkbenchSelected')}</div>
          <div className="mt-1 text-sm font-semibold text-slate-950 dark:text-slate-100">
            {selectedNode?.title || summary?.title || t('meetingWorkbenchNoNodeSelected')}
          </div>
          <p className="mt-1 text-xs leading-5 text-slate-500 dark:text-slate-400">
            {selectedNode?.detail || summary?.summary_text || t('meetingWorkbenchNoSelectedMeetingNode')}
          </p>
        </div>
        <div className="grid grid-cols-2 gap-2">
          <StatTile label={t('meetingWorkbenchStatus')} value={selectedNode?.status || 'none'} />
          <StatTile label={t('meetingWorkbenchKind')} value={selectedNode ? formatKind(selectedNode.kind) : 'none'} />
        </div>
        <div className="rounded-md border border-slate-200 p-2 text-xs dark:border-slate-800">
          <div className="font-semibold text-slate-900 dark:text-slate-100">{summary?.title || t('meetingWorkbenchFocusObject')}</div>
          <div className="mt-1 truncate font-mono text-[11px] text-slate-500 dark:text-slate-400">
            {summary?.ref.uri || 'mindscape://object'}
          </div>
        </div>
      </div>
    );
  }

  if (activeInspector === 'graph') {
    const guidanceCards = collectObjectGuidanceCards(objectGraphProjections);
    const selectedGuidanceCard = getSelectedGuidanceCard(selectedNode, guidanceCards);
    return (
      <div className="space-y-3" data-testid="meeting-work-guidance-panel">
        {selectedGuidanceCard ? (
          <div
            className="rounded-md border border-blue-200 bg-blue-50/70 p-2 text-xs dark:border-blue-900/50 dark:bg-blue-950/20"
            data-testid="meeting-work-selected-guidance-card"
          >
            <div className="text-[10px] font-semibold uppercase tracking-[0.12em] text-blue-700 dark:text-blue-300">
              {t('meetingWorkbenchSelectedGuidance')}
            </div>
            <div className="mt-1 font-semibold text-slate-950 dark:text-slate-100">{selectedGuidanceCard.title}</div>
            {selectedGuidanceCard.description ? (
              <div className="mt-1 leading-5 text-slate-600 dark:text-slate-300">
                <span className="font-semibold">{t('meetingWorkbenchGuidanceReason')}:</span> {selectedGuidanceCard.description}
              </div>
            ) : null}
            <GuidanceCommandBlock card={selectedGuidanceCard} t={t} />
            {(selectedGuidanceCard.review_routes || []).length > 0 ? (
              <div className="mt-2 space-y-1">
                {(selectedGuidanceCard.review_routes || []).slice(0, 3).map((route) => (
                  <a key={route} href={route} className="block truncate rounded border border-blue-100 bg-white/80 px-2 py-1.5 text-[11px] font-medium text-blue-700 hover:bg-white dark:border-blue-900/50 dark:bg-blue-950/40 dark:text-blue-200 dark:hover:bg-blue-950/60">
                    <span className="mr-1 font-semibold">{selectedGuidanceCard.review_label || t('meetingWorkbenchReviewRoute')}:</span>
                    {route}
                  </a>
                ))}
              </div>
            ) : null}
          </div>
        ) : null}
        <div className="rounded-md border border-slate-200 p-2 text-xs dark:border-slate-800">
          <div className="flex items-center justify-between gap-2">
            <div className="font-semibold text-slate-900 dark:text-slate-100">{t('meetingWorkbenchContextRelations')}</div>
            <div className="rounded bg-slate-100 px-1.5 py-0.5 font-semibold tabular-nums text-slate-500 dark:bg-slate-900 dark:text-slate-400">
              {objectGraphProjections.length}
            </div>
          </div>
          {objectGraphLoading ? <div className="mt-2 text-slate-500 dark:text-slate-400">{t('meetingWorkbenchLoadingRelations')}</div> : null}
          {objectGraphError ? (
            <div className="mt-2 rounded bg-amber-50 px-2 py-1.5 text-amber-700 dark:bg-amber-950/20 dark:text-amber-300">
              {objectGraphError}
            </div>
          ) : null}
        </div>
        <div className="rounded-md border border-slate-200 p-2 text-xs dark:border-slate-800">
          <div className="flex items-center justify-between gap-2">
            <div className="font-semibold text-slate-900 dark:text-slate-100">{t('meetingWorkbenchGuidanceCards')}</div>
            <div className="rounded bg-slate-100 px-1.5 py-0.5 font-semibold tabular-nums text-slate-500 dark:bg-slate-900 dark:text-slate-400">
              {guidanceCards.length}
            </div>
          </div>
          <div className="mt-2 space-y-2">
            {guidanceCards.length > 0 ? (
              guidanceCards.slice(0, 6).map((card) => (
                <div key={`${addressableRefKey(card.projection.ref)}-${card.id}`} className="rounded-md bg-slate-50 p-2 dark:bg-slate-900">
                  <div className="font-semibold text-slate-900 dark:text-slate-100">{card.title}</div>
                  {card.description ? (
                    <div className="mt-1 leading-5 text-slate-500 dark:text-slate-400">{card.description}</div>
                  ) : null}
                  <GuidanceCommandBlock card={card} t={t} />
                  {(card.review_routes || []).length > 0 ? (
                    <div className="mt-2 space-y-1">
                      {(card.review_routes || []).slice(0, 3).map((route) => (
                        <a key={route} href={route} className="block truncate rounded border border-blue-100 bg-blue-50 px-2 py-1.5 text-[11px] font-medium text-blue-700 hover:bg-blue-100 dark:border-blue-900/50 dark:bg-blue-950/30 dark:text-blue-200 dark:hover:bg-blue-950/50">
                          <span className="mr-1 font-semibold">{card.review_label || t('meetingWorkbenchReviewRoute')}:</span>
                          {route}
                        </a>
                      ))}
                    </div>
                  ) : null}
                </div>
              ))
            ) : (
              <div className="text-slate-400 dark:text-slate-500">{t('meetingWorkbenchNoGuidanceCards')}</div>
            )}
          </div>
        </div>
        <div className="max-h-60 space-y-2 overflow-auto">
          {objectGraphProjections.map((projection) => (
            <div key={addressableRefKey(projection.ref)} className="rounded-md border border-slate-200 p-2 text-xs dark:border-slate-800">
              <div className="font-semibold text-slate-900 dark:text-slate-100">
                {projection.summary?.title || graphRefLabel(projection.ref)}
              </div>
              <div className="mt-2 flex flex-wrap gap-1.5">
                {(projection.relations || []).slice(0, 6).map((relation, index) => (
                  <span key={`${relation.relation_kind}-${index}`} className="rounded-full bg-slate-100 px-2 py-1 text-[11px] text-slate-600 dark:bg-slate-900 dark:text-slate-300">
                    {relation.direction} {relation.relation_kind}
                  </span>
                ))}
                {(projection.relations || []).length === 0 ? <span className="text-slate-400 dark:text-slate-500">{t('meetingWorkbenchNoBoundedRelations')}</span> : null}
              </div>
            </div>
          ))}
        </div>
      </div>
    );
  }

  if (activeInspector === 'prompts') {
    return (
      <div className="space-y-3" data-testid="meeting-work-actions-panel">
        <div className="rounded-md border border-slate-200 p-2 dark:border-slate-800">
          <div className="text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-500">{t('meetingWorkbenchActionFocus')}</div>
          <div className="mt-1 text-sm font-semibold text-slate-950 dark:text-slate-100">
            {commandImpact?.commandText || selectedNode?.title || t('meetingWorkbenchReadyForInstruction')}
          </div>
          <p className="mt-1 text-xs leading-5 text-slate-500 dark:text-slate-400">
            {selectedNode?.detail || t('meetingWorkbenchCommandLedgerReady')}
          </p>
        </div>
        <div className="grid grid-cols-2 gap-2">
          <StatTile label={t('meetingWorkbenchRelated')} value={commandImpact?.relatedNodes.length ?? 0} />
          <StatTile label={t('meetingWorkbenchOutputs')} value={commandImpact?.outputs.length ?? 0} />
          <StatTile label={t('meetingWorkbenchArtifacts')} value={commandImpact?.artifacts.length ?? 0} />
          <StatTile label={t('meetingWorkbenchActions')} value={commandImpact?.actionItems.length ?? 0} />
        </div>
      </div>
    );
  }

  if (activeInspector === 'session') {
    return (
      <dl className="grid gap-2 text-xs" data-testid="meeting-work-context-panel">
        <div className="rounded-md border border-slate-200 p-2 dark:border-slate-800">
          <dt className="font-semibold uppercase tracking-[0.12em] text-slate-500">{t('meetingWorkbenchMeeting')}</dt>
          <dd className="mt-1 font-mono">{meetingId}</dd>
        </div>
        <div className="rounded-md border border-slate-200 p-2 dark:border-slate-800">
          <dt className="font-semibold uppercase tracking-[0.12em] text-slate-500">{t('meetingWorkbenchWorkspace')}</dt>
          <dd className="mt-1 font-mono">{workspaceId}</dd>
        </div>
        <div className="rounded-md border border-slate-200 p-2 dark:border-slate-800">
          <dt className="font-semibold uppercase tracking-[0.12em] text-slate-500">{t('meetingWorkbenchFocus')}</dt>
          <dd className="mt-1 truncate font-mono">{summary?.ref.uri || 'mindscape://object'}</dd>
        </div>
      </dl>
    );
  }

  if (activeInspector === 'runtime') {
    return <MeetingRuntimeInspectorContent runtimeSnapshot={runtimeSnapshot} />;
  }

  if (activeInspector === 'patch') {
    const attachReviewRoutes = attachResponse?.review_routes ?? [];
    const guidanceReviewRoutes = collectObjectGuidanceReviewAffordances(objectGraphProjections);
    return (
      <div className="space-y-2 text-xs" data-testid="meeting-work-review-panel">
        {attachReviewRoutes.map((route) => (
          <a key={route} href={route} className="block rounded-md border border-slate-200 p-2 text-slate-700 hover:bg-slate-50 dark:border-slate-800 dark:text-slate-200 dark:hover:bg-slate-900">
            <div className="text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-500">{t('meetingWorkbenchAttachmentReviewRoute')}</div>
            <div className="mt-1 truncate">{route}</div>
          </a>
        ))}
        {guidanceReviewRoutes.length > 0 ? (
          guidanceReviewRoutes.map((affordance) => (
            <a key={affordance.id} href={affordance.route} className="block rounded-md border border-slate-200 p-2 text-slate-700 hover:bg-slate-50 dark:border-slate-800 dark:text-slate-200 dark:hover:bg-slate-900">
              <div className="text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-500">{t('meetingWorkbenchGuidanceReviewRoute')}</div>
              <div className="mt-1 font-semibold text-slate-900 dark:text-slate-100">{affordance.label}</div>
              <div className="mt-1 truncate">{affordance.route}</div>
            </a>
          ))
        ) : (
          attachReviewRoutes.length === 0 ? (
            <div className="rounded-md border border-slate-200 p-2 dark:border-slate-800">{t('meetingWorkbenchNoReviewRoutesStaged')}</div>
          ) : null
        )}
      </div>
    );
  }

  return null;
}
