'use client';

import React from 'react';
// @ts-ignore - Optional dependency, may not be installed
import { DragDropContext, Droppable, Draggable, DropResult } from 'react-beautiful-dnd';
import { BinderViewProps, ViewItem } from './types';

/**
 * BinderView - Tree-like file browser view
 *
 * Displays items in a hierarchical tree structure, similar to Scrivener's Binder.
 * Supports drag-and-drop reordering and item selection.
 */
export function BinderView<T extends ViewItem>({
  items,
  selectedId,
  onSelect,
  onReorder,
  renderItem,
  getItemIcon,
  getItemStatus,
  allowReorder = false
}: BinderViewProps<T>) {
  const handleDragEnd = (result: DropResult) => {
    if (!result.destination || !allowReorder || !onReorder) return;

    const reorderedItems = Array.from(items);
    const [movedItem] = reorderedItems.splice(result.source.index, 1);
    reorderedItems.splice(result.destination.index, 0, movedItem);
    onReorder(reorderedItems);
  };

  const defaultRenderItem = (item: T, isSelected: boolean) => (
    <div
      className={`p-2 cursor-pointer transition-colors ${isSelected
        ? 'bg-blue-50 dark:bg-blue-900/20 border-l-4 border-blue-500'
        : 'hover:bg-gray-50 dark:hover:bg-gray-800'
        }`}
      onClick={() => onSelect?.(item)}
    >
      <div className="flex items-center gap-2">
        {getItemIcon && getItemIcon(item)}
        <span className="font-medium text-gray-900 dark:text-gray-100 flex-1">
          {item.title}
        </span>
        {getItemStatus && (
          <span className="text-xs text-gray-500 dark:text-gray-400">
            {getItemStatus(item)}
          </span>
        )}
      </div>
    </div>
  );

  const content = (
    <div className="flex-1 overflow-y-auto">
      {items.map((item, index) => {
        const isSelected = selectedId === item.id;
        const itemContent = renderItem
          ? renderItem(item, isSelected)
          : defaultRenderItem(item, isSelected);

        if (!allowReorder) {
          return <div key={item.id}>{itemContent}</div>;
        }

        return (
          <Draggable key={item.id} draggableId={item.id} index={index}>
            {(provided: any, snapshot: any) => (
              <div
                ref={provided.innerRef}
                {...provided.draggableProps}
                {...provided.dragHandleProps}
                className={snapshot.isDragging ? 'opacity-50' : ''}
              >
                {itemContent}
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
        <Droppable droppableId="binder-items">
          {(provided: any) => (
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

