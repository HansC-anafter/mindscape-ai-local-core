'use client';

import React from 'react';
import { DragDropContext, Droppable, Draggable, DropResult } from '@dnd-kit/core';
import { CorkboardViewProps, ViewItem } from './types';

/**
 * CorkboardView - Card-based view similar to Scrivener's Corkboard
 *
 * Displays items as cards in a grid layout, similar to a corkboard with index cards.
 * Supports drag-and-drop reordering and card selection.
 */
export function CorkboardView<T extends ViewItem>({
  items,
  selectedId,
  onSelect,
  onReorder,
  renderCard,
  getCardStatus,
  allowReorder = false,
  columns = 3
}: CorkboardViewProps<T>) {
  const handleDragEnd = (result: DropResult) => {
    if (!result.destination || !allowReorder || !onReorder) return;

    const reorderedItems = Array.from(items);
    const [movedItem] = reorderedItems.splice(result.source.index, 1);
    reorderedItems.splice(result.destination.index, 0, movedItem);
    onReorder(reorderedItems);
  };

  const defaultRenderCard = (item: T, isSelected: boolean) => (
    <div
      className={`p-4 bg-white dark:bg-gray-800 border-2 rounded-lg shadow-sm cursor-pointer transition-all ${
        isSelected
          ? 'border-blue-500 shadow-md'
          : 'border-gray-200 dark:border-gray-700 hover:border-gray-300 dark:hover:border-gray-600'
      }`}
      onClick={() => onSelect?.(item)}
    >
      <div className="font-medium text-gray-900 dark:text-gray-100 mb-2">
        {item.title}
      </div>
      {getCardStatus && (
        <div className="text-xs text-gray-500 dark:text-gray-400">
          {getCardStatus(item)}
        </div>
      )}
    </div>
  );

  const gridStyle = {
    gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))`
  };

  const content = (
    <div
      className="grid gap-4 p-4 overflow-y-auto"
      style={gridStyle}
    >
      {items.map((item, index) => {
        const isSelected = selectedId === item.id;
        const cardContent = renderCard
          ? renderCard(item, isSelected)
          : defaultRenderCard(item, isSelected);

        if (!allowReorder) {
          return <div key={item.id}>{cardContent}</div>;
        }

        return (
          <Draggable key={item.id} draggableId={item.id} index={index}>
            {(provided, snapshot) => (
              <div
                ref={provided.innerRef}
                {...provided.draggableProps}
                {...provided.dragHandleProps}
                className={snapshot.isDragging ? 'opacity-50' : ''}
              >
                {cardContent}
              </div>
            )}
          </Draggable>
        );
      })}
    </div>
  );

  if (allowReorder) {
    return (
      <DragDropContext onDragEnd={handleDragEnd}>
        <Droppable droppableId="corkboard-items" direction="grid">
          {(provided) => (
            <div {...provided.droppableProps} ref={provided.innerRef}>
              {content}
              {provided.placeholder}
            </div>
          )}
        </Droppable>
      </DragDropContext>
    );
  }

  return content;
}

