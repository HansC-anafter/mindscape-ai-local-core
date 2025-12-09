'use client';

import React, { useState, useEffect } from 'react';
import { t } from '@/lib/i18n';
import './IntentCardPanel.css';

export interface IntentCard {
  id: string;
  title: string;
  description?: string;
  status: 'pending_decision' | 'confirmed' | 'rejected';
  priority: 'high' | 'medium' | 'low';
  decisions?: Array<{
    id: string;
    question: string;
    options: string[];
    selectedOption?: string;
  }>;
  createdAt?: string;
}

interface IntentCardPanelProps {
  workspaceId: string;
  apiUrl: string;
}

export function IntentCardPanel({ workspaceId, apiUrl }: IntentCardPanelProps) {
  const [intentCards, setIntentCards] = useState<IntentCard[]>([]);
  const [showHistory, setShowHistory] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadIntentCards();
  }, [workspaceId, apiUrl]);

  const loadIntentCards = async () => {
    try {
      setLoading(true);
      const response = await fetch(
        `${apiUrl}/api/v1/workspaces/${workspaceId}/intent-cards?status=all`
      );
      if (response.ok) {
        const data = await response.json();
        setIntentCards(data.intentCards || []);
      } else {
        setIntentCards([]);
      }
    } catch (err) {
      console.error('Failed to load intent cards:', err);
      setIntentCards([]);
    } finally {
      setLoading(false);
    }
  };

  const pendingCards = intentCards.filter(c => c.status === 'pending_decision');
  const historyCards = intentCards.filter(c => c.status !== 'pending_decision');
  const highPriorityCount = pendingCards.filter(c => c.priority === 'high').length;
  const hasHighPriority = highPriorityCount > 0;

  if (loading) {
    return (
      <div className="intent-card-panel">
        <div className="empty-state">
          <span className="hint">Loading...</span>
        </div>
      </div>
    );
  }

  return (
    <div className="intent-card-panel">
      <div className={`section-header priority ${hasHighPriority ? 'has-high-priority' : ''}`}>
        <span className="title">Pending Decisions</span>
        {pendingCards.length > 0 && (
          <span className="badge pending">{pendingCards.length}</span>
        )}
        {highPriorityCount > 0 && (
          <span className="badge high-priority priority-badge" title={`${highPriorityCount} high priority items`}>
            {highPriorityCount}
          </span>
        )}
      </div>

      <div className="pending-intents">
        {pendingCards.length === 0 ? (
          <div className="empty-state">
            <span className="hint">No pending decisions</span>
          </div>
        ) : (
          pendingCards.map(card => (
            <IntentCardItem key={card.id} card={card} />
          ))
        )}
      </div>

      {historyCards.length > 0 && (
        <div className="history-intents">
          <button
            className={`history-toggle ${showHistory ? 'expanded' : ''}`}
            onClick={() => setShowHistory(!showHistory)}
          >
            <span className="chevron" />
            <span>History ({historyCards.length})</span>
          </button>

          {showHistory && (
            <div className="history-list">
              {historyCards.map(card => (
                <IntentCardItem key={card.id} card={card} collapsed />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function IntentCardItem({ card, collapsed }: { card: IntentCard; collapsed?: boolean }) {
  return (
    <div className={`intent-card-item ${card.priority} ${collapsed ? 'collapsed' : ''}`}>
      <div className="card-header">
        <span className="card-title">{card.title}</span>
        <span className={`priority-badge ${card.priority}`}>
          {card.priority === 'high' ? 'High' : card.priority === 'medium' ? 'Medium' : 'Low'}
        </span>
      </div>
      {!collapsed && card.description && (
        <div className="card-description">{card.description}</div>
      )}
      {!collapsed && card.decisions && card.decisions.length > 0 && (
        <div className="decisions-list">
          {card.decisions.map(decision => (
            <div key={decision.id} className="decision-item">
              <div className="decision-question">{decision.question}</div>
              <div className="decision-options">
                {decision.options.map(option => (
                  <label key={option} className="option-label">
                    <input
                      type="radio"
                      name={decision.id}
                      value={option}
                      checked={decision.selectedOption === option}
                      readOnly
                    />
                    <span>{option}</span>
                  </label>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

