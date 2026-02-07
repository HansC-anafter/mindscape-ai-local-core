'use client';

import React from 'react';
// @ts-ignore - Optional dependency
import { DragDropContext, Droppable, Draggable, DropResult } from 'react-beautiful-dnd';
import { OutlinerViewProps, ViewItem } from './types';

/**
 * OutlinerView - Table-based outline view similar to Scrivener's Outliner
 *
 * Displays items in a table format with customizable columns.
 * Supports drag-and-drop reordering and row selection.
 */
export function OutlinerView<T extends ViewItem>({
  items,
  selectedId,
  onSelect,
  onReorder,
  columns,
  allowReorder = false
}: OutlinerViewProps<T>) {
  const handleDragEnd = (result: DropResult) => {
    if (!result.destination || !allowReorder || !onReorder) return;

    const reorderedItems = Array.from(items);
    const [movedItem] = reorderedItems.splice(result.source.index, 1);
    reorderedItems.splice(result.destination.index, 0, movedItem);
    onReorder(reorderedItems);
  };

  const renderCell = (item: T, column: typeof columns[0]) => {
    if (column.render) {
      return column.render(item);
    }
    return item[column.key] || '';
  };

  const content = (
    <div className="overflow-y-auto">
      <table className="w-full border-collapse">
        <thead className="sticky top-0 bg-gray-50 dark:bg-gray-800 border-b dark:border-gray-700">
          <tr>
            {columns.map((column) => (
              <th
                key={column.key}
                className="px-4 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider"
                style={{ width: column.width }}
              >
                {column.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="bg-white dark:bg-gray-900 divide-y divide-gray-200 dark:divide-gray-700">
          {items.map((item, index) => {
            const isSelected = selectedId === item.id;
            const row = (
              <tr
                key={item.id}
                className={`cursor-pointer transition-colors ${
                  isSelected
                    ? 'bg-blue-50 dark:bg-blue-900/20'
                    : 'hover:bg-gray-50 dark:hover:bg-gray-800'
                }`}
                onClick={() => onSelect?.(item)}
              >
                {columns.map((column) => (
                  <td
                    key={column.key}
                    className="px-4 py-2 text-sm text-gray-900 dark:text-gray-100"
                  >
                    {renderCell(item, column)}
                  </td>
                ))}
              </tr>
            );

            if (!allowReorder) {
              return row;
            }

            return (
              <Draggable key={item.id} draggableId={item.id} index={index}>
                {(provided: any, snapshot: any) => (
                  <tr
                    ref={provided.innerRef}
                    {...provided.draggableProps}
                    {...provided.dragHandleProps}
                    className={`${snapshot.isDragging ? 'opacity-50' : ''} ${
                      isSelected
                        ? 'bg-blue-50 dark:bg-blue-900/20'
                        : 'hover:bg-gray-50 dark:hover:bg-gray-800'
                    }`}
                    onClick={() => onSelect?.(item)}
                  >
                    {columns.map((column) => (
                      <td
                        key={column.key}
                        className="px-4 py-2 text-sm text-gray-900 dark:text-gray-100"
                      >
                        {renderCell(item, column)}
                      </td>
                    ))}
                  </tr>
                )}
              </Draggable>
            );
          })}
        </tbody>
      </table>
    </div>
  );

  if (allowReorder) {
    return (
      <DragDropContext onDragEnd={handleDragEnd}>
        <Droppable droppableId="outliner-items">
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

