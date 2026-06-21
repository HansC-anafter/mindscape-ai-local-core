import type { DecisionCardData } from '../DecisionCard';
import type { DecisionFilter, IntentCard } from './types';

export function getPendingIntentCards(intentCards: IntentCard[]) {
  return intentCards.filter(card => card.status === 'pending_decision');
}

export function getHistoryIntentCards(intentCards: IntentCard[]) {
  return intentCards.filter(card => card.status !== 'pending_decision');
}

export function sortDecisionCards(
  decisionCards: DecisionCardData[],
  currentUserId: string
) {
  return [...decisionCards].sort((a, b) => {
    if (a.priority === 'blocker' && b.priority !== 'blocker') return -1;
    if (a.priority !== 'blocker' && b.priority === 'blocker') return 1;

    const aIsMine = a.assignee === currentUserId;
    const bIsMine = b.assignee === currentUserId;
    if (aIsMine && !bIsMine) return -1;
    if (!aIsMine && bIsMine) return 1;
    if (a.dueAt && b.dueAt) {
      return a.dueAt.getTime() - b.dueAt.getTime();
    }
    if (a.dueAt && !b.dueAt) return -1;
    if (!a.dueAt && b.dueAt) return 1;

    return 0;
  });
}

export function filterDecisionCards(
  sortedDecisionCards: DecisionCardData[],
  filter: DecisionFilter,
  currentUserId: string
) {
  switch (filter) {
    case 'blockers':
      return sortedDecisionCards.filter(card => card.priority === 'blocker' && card.status === 'OPEN');
    case 'assigned-to-me':
      return sortedDecisionCards.filter(card => card.assignee === currentUserId && card.status === 'OPEN');
    case 'mentioned-me':
      return sortedDecisionCards.filter(card => card.watchers?.includes(currentUserId) && card.status === 'OPEN');
    case 'waiting-on-others':
      return sortedDecisionCards.filter(card => card.assignee && card.assignee !== currentUserId && card.status === 'OPEN');
    default:
      return sortedDecisionCards.filter(card => card.status === 'OPEN' || card.status === 'NEED_INFO');
  }
}

export function countOpenDecisionCards(decisionCards: DecisionCardData[]) {
  return decisionCards.filter(card => card.status === 'OPEN' || card.status === 'NEED_INFO').length;
}

export function countBlockerCards(decisionCards: DecisionCardData[]) {
  return decisionCards.filter(card => card.priority === 'blocker' && card.status === 'OPEN').length;
}

export function countAssignedToMeCards(
  decisionCards: DecisionCardData[],
  currentUserId: string
) {
  return decisionCards.filter(card => card.assignee === currentUserId && card.status === 'OPEN').length;
}

export function countMentionedMeCards(
  decisionCards: DecisionCardData[],
  currentUserId: string
) {
  return decisionCards.filter(card => card.watchers?.includes(currentUserId) && card.status === 'OPEN').length;
}

export function countWaitingOnOthersCards(
  decisionCards: DecisionCardData[],
  currentUserId: string
) {
  return decisionCards.filter(card => card.assignee && card.assignee !== currentUserId && card.status === 'OPEN').length;
}
