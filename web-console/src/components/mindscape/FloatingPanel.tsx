'use client';

/**
 * FloatingPanel - A draggable, resizable floating panel component
 *
 * Used for node details and chat dialogs in the Mindscape Canvas.
 */

import React, { useState, useRef, useCallback, useEffect } from 'react';

interface FloatingPanelProps {
    title: string;
    isOpen: boolean;
    onClose: () => void;
    children: React.ReactNode;
    defaultPosition?: { x: number; y: number };
    defaultSize?: { width: number; height: number };
    minWidth?: number;
    minHeight?: number;
    className?: string;
}

export function FloatingPanel({
    title,
    isOpen,
    onClose,
    children,
    defaultPosition = { x: 100, y: 100 },
    defaultSize = { width: 360, height: 400 },
    minWidth = 280,
    minHeight = 200,
    className = '',
}: FloatingPanelProps) {
    const [position, setPosition] = useState(defaultPosition);
    const [size, setSize] = useState(defaultSize);
    const [isDragging, setIsDragging] = useState(false);
    const [isResizing, setIsResizing] = useState(false);
    const panelRef = useRef<HTMLDivElement>(null);
    const dragOffset = useRef({ x: 0, y: 0 });
    const resizeStart = useRef({ x: 0, y: 0, width: 0, height: 0 });

    // Handle drag start
    const handleDragStart = useCallback((e: React.MouseEvent) => {
        if ((e.target as HTMLElement).closest('.panel-controls')) return;

        setIsDragging(true);
        dragOffset.current = {
            x: e.clientX - position.x,
            y: e.clientY - position.y,
        };
        e.preventDefault();
    }, [position]);

    // Handle resize start
    const handleResizeStart = useCallback((e: React.MouseEvent) => {
        setIsResizing(true);
        resizeStart.current = {
            x: e.clientX,
            y: e.clientY,
            width: size.width,
            height: size.height,
        };
        e.preventDefault();
        e.stopPropagation();
    }, [size]);

    // Handle mouse move
    useEffect(() => {
        const handleMouseMove = (e: MouseEvent) => {
            if (isDragging) {
                setPosition({
                    x: e.clientX - dragOffset.current.x,
                    y: e.clientY - dragOffset.current.y,
                });
            }
            if (isResizing) {
                const deltaX = e.clientX - resizeStart.current.x;
                const deltaY = e.clientY - resizeStart.current.y;
                setSize({
                    width: Math.max(minWidth, resizeStart.current.width + deltaX),
                    height: Math.max(minHeight, resizeStart.current.height + deltaY),
                });
            }
        };

        const handleMouseUp = () => {
            setIsDragging(false);
            setIsResizing(false);
        };

        if (isDragging || isResizing) {
            document.addEventListener('mousemove', handleMouseMove);
            document.addEventListener('mouseup', handleMouseUp);
        }

        return () => {
            document.removeEventListener('mousemove', handleMouseMove);
            document.removeEventListener('mouseup', handleMouseUp);
        };
    }, [isDragging, isResizing, minWidth, minHeight]);

    if (!isOpen) return null;

    return (
        <div
            ref={panelRef}
            className={`fixed bg-white rounded-xl shadow-2xl border border-gray-200 flex flex-col overflow-hidden z-50 ${className}`}
            style={{
                left: position.x,
                top: position.y,
                width: size.width,
                height: size.height,
                cursor: isDragging ? 'grabbing' : 'default',
            }}
        >
            {/* Header - Draggable */}
            <div
                className="flex items-center justify-between px-4 py-3 bg-gradient-to-r from-indigo-50 to-purple-50 border-b border-gray-100 cursor-grab select-none"
                onMouseDown={handleDragStart}
            >
                <h3 className="font-semibold text-gray-800 text-sm">{title}</h3>
                <div className="panel-controls flex items-center gap-1">
                    <button
                        onClick={onClose}
                        className="w-6 h-6 flex items-center justify-center rounded hover:bg-gray-200 text-gray-500 hover:text-gray-700 transition-colors"
                    >
                        ✕
                    </button>
                </div>
            </div>

            {/* Content */}
            <div className="flex-1 overflow-auto p-4">
                {children}
            </div>

            {/* Resize Handle */}
            <div
                className="absolute bottom-0 right-0 w-4 h-4 cursor-se-resize"
                onMouseDown={handleResizeStart}
            >
                <svg
                    className="w-3 h-3 text-gray-400 absolute bottom-1 right-1"
                    fill="currentColor"
                    viewBox="0 0 6 6"
                >
                    <circle cx="5" cy="5" r="1" />
                    <circle cx="5" cy="2" r="1" />
                    <circle cx="2" cy="5" r="1" />
                </svg>
            </div>
        </div>
    );
}
