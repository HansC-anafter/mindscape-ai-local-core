import React, { useState, useEffect, useRef, useCallback } from 'react';
import { createPortal } from 'react-dom';
import { Pin } from 'lucide-react';
import { getPostThumbnailUrl, getProxiedImageUrl } from '../utils';

interface GridPost {
    post_shortcode: string;
    post_type: string;
    post_url?: string;
    thumbnail_url?: string;
}

export function PostPreviewPopover({
    account,
    triggerRef,
    isOpen,
    onPinReference,
}: {
    account: any;
    triggerRef: React.RefObject<HTMLElement>;
    isOpen: boolean;
    onPinReference?: (imageUrl: string, sourceHandle: string, shortcode: string) => void;
}) {
    const [coords, setCoords] = useState({ top: 0, left: 0 });
    const [mounted, setMounted] = useState(false);

    useEffect(() => {
        setMounted(true);
        return () => setMounted(false);
    }, []);

    useEffect(() => {
        if (isOpen && triggerRef.current) {
            const rect = triggerRef.current.getBoundingClientRect();

            // Calculate position to show it on the right, or left if no space
            let left = rect.left + rect.width + 10;
            if (left + 320 > window.innerWidth) {
                left = rect.left - 320 - 10;
            }

            // Calculate top so it doesn't go off-screen
            let top = rect.top;
            if (top + 340 > window.innerHeight) {
                top = window.innerHeight - 340 - 10;
            }
            if (top < 0) top = 10;

            setCoords({ top, left });
        }
    }, [isOpen, triggerRef]);

    if (!isOpen || !mounted) return null;

    let posts: GridPost[] = [];
    try {
        if (account.grid_posts_json) {
            posts = JSON.parse(account.grid_posts_json);
        }
    } catch (e) {
        // ignore
    }

    if (posts.length === 0) return null;

    const content = (
        <div
            className="fixed z-[100] bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg shadow-2xl p-3 transition-all duration-200 ease-in-out"
            style={{
                top: coords.top,
                left: coords.left,
                width: 320,
            }}
        >
            <div className="text-xs font-semibold text-gray-700 dark:text-gray-300 mb-2">
                Recent Posts
            </div>
            <div className="grid grid-cols-3 gap-1.5">
                {posts.slice(0, 9).map((post) => {
                    const proxyUrl = post.post_shortcode
                        ? getPostThumbnailUrl('', post.post_shortcode)
                        : getProxiedImageUrl('', post.thumbnail_url);
                    return (
                        <div key={post.post_shortcode} className="aspect-square bg-gray-100 dark:bg-gray-900 rounded overflow-hidden relative group">
                            {proxyUrl ? (
                                <img src={proxyUrl} alt="Thumbnail" className="w-full h-full object-cover" />
                            ) : (
                                <div className="w-full h-full flex items-center justify-center text-xs text-gray-400">N/A</div>
                            )}
                            {post.post_type === 'reel' && (
                                <div className="absolute top-1 right-1 text-[8px] bg-black/60 text-white px-1 py-0.5 rounded">R</div>
                            )}
                            {/* Pin reference button */}
                            {onPinReference && proxyUrl && (
                                <button
                                    onClick={(e) => {
                                        e.stopPropagation();
                                        onPinReference(
                                            post.thumbnail_url || '',
                                            account.username || '',
                                            post.post_shortcode || '',
                                        );
                                    }}
                                    className="absolute bottom-1 right-1 p-1 bg-black/60 rounded-full text-white opacity-0 group-hover:opacity-100 hover:bg-rose-500 transition-all"
                                    title="Pin as reference"
                                >
                                    <Pin className="w-3 h-3" />
                                </button>
                            )}
                        </div>
                    );
                })}
            </div>
        </div>
    );

    return createPortal(content, document.body);
}
