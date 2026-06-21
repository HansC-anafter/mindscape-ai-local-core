import React from 'react';

import type { StepEvent } from '../types/execution';
import type { Translator } from './stepDetailPanelTypes';

export function StepEventsSection({
  stepEvents,
  t,
}: {
  stepEvents: StepEvent[];
  t: Translator;
}) {
  if (stepEvents.length === 0) {
    return null;
  }

  return (
    <div className="mb-3">
      <h4 className="text-xs font-medium text-gray-900 dark:text-gray-100 mb-1.5">
        {t('eventStream' as any)}
      </h4>
      <div className="space-y-1.5">
        {stepEvents.map((event) => (
          <div
            key={event.id}
            className="flex gap-2 p-1.5 bg-surface-accent dark:bg-gray-700 rounded border border-default dark:border-gray-600"
          >
            <div className="flex-shrink-0 text-[10px] text-gray-500 dark:text-gray-300 w-14">
              {event.timestamp.toLocaleTimeString(undefined, {
                hour: '2-digit',
                minute: '2-digit',
                second: '2-digit',
              })}
            </div>
            <div className="flex-1 min-w-0">
              <div className="text-[10px] text-gray-600 dark:text-gray-300">
                {event.type === 'tool' && event.tool && (
                  <span className="font-medium">
                    {t('tool' as any)} {event.tool}
                  </span>
                )}
                {event.type === 'collaboration' && event.agent && (
                  <span className="font-medium">
                    {t('collaboration' as any)} {event.agent}
                  </span>
                )}
                {event.type === 'step' && event.agent && (
                  <span className="font-medium">
                    {t('agent' as any)} {event.agent}
                  </span>
                )}
              </div>
              <div className="text-xs text-gray-900 dark:text-gray-100 mt-0.5">
                {event.content}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
