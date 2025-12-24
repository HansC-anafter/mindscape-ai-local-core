"use client";

import React, { useState } from "react";

interface UnsplashImageReference {
  photo_id: string;
  urls: {
    raw?: string;
    full?: string;
    regular?: string;
    small?: string;
    thumb?: string;
  };
  photographer?: {
    name?: string;
    username?: string;
    profile_url?: string;
  };
  description?: string;
  tags?: string[];
  color?: string;
  width?: number;
  height?: number;
}

interface VisualLens {
  id: string;
  lens_id: string;
  name: string;
  description?: string;
  source_photographer?: string;
  source_image_references?: UnsplashImageReference[];
  schema_data?: {
    light_color_tokens?: {
      color_palette?: string[];
      color_temperature?: string;
      saturation?: string;
    };
    mood_narrative?: {
      emotion_keywords?: string[];
      narrative_distance?: string;
    };
    composition_rules?: {
      whitespace_ratio?: number;
      geometric_preference?: string;
    };
    web_translation_rules?: {
      border_radius?: string;
      shadow_style?: string;
      layout_density?: string;
    };
  };
  summary?: string;
}

interface VisualLensPreviewCardProps {
  lens: VisualLens;
  onSelect?: (lensId: string) => void;
  onEdit?: (lensId: string) => void;
  onDelete?: (lensId: string) => void;
}

export default function VisualLensPreviewCard({
  lens,
  onSelect,
  onEdit,
  onDelete,
}: VisualLensPreviewCardProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  const [showDetails, setShowDetails] = useState(false);

  const colorPalette = lens.schema_data?.light_color_tokens?.color_palette || [];
  const emotionKeywords = lens.schema_data?.mood_narrative?.emotion_keywords || [];
  const imageReferences = lens.source_image_references || [];

  return (
    <div className="border rounded-lg p-4 bg-white shadow-sm hover:shadow-md transition-shadow">
      {/* Header */}
      <div className="flex justify-between items-start mb-4">
        <div className="flex-1">
          <h3 className="text-lg font-semibold text-gray-900">{lens.name}</h3>
          {lens.description && (
            <p className="text-sm text-gray-600 mt-1">{lens.description}</p>
          )}
          {lens.source_photographer && (
            <p className="text-xs text-gray-500 mt-1">
              攝影師：{lens.source_photographer}
            </p>
          )}
        </div>
        <div className="flex gap-2">
          {onSelect && (
            <button
              onClick={() => onSelect(lens.lens_id)}
              className="px-3 py-1 text-sm bg-blue-600 text-white rounded hover:bg-blue-700"
            >
              選用
            </button>
          )}
          {onEdit && (
            <button
              onClick={() => onEdit(lens.lens_id)}
              className="px-3 py-1 text-sm bg-gray-200 text-gray-700 rounded hover:bg-gray-300"
            >
              編輯
            </button>
          )}
          {onDelete && (
            <button
              onClick={() => onDelete(lens.lens_id)}
              className="px-3 py-1 text-sm bg-red-100 text-red-700 rounded hover:bg-red-200"
            >
              刪除
            </button>
          )}
        </div>
      </div>

      {/* Summary */}
      {lens.summary && (
        <div className="mb-4 p-3 bg-gray-50 rounded text-sm text-gray-700">
          {lens.summary}
        </div>
      )}

      {/* Color Palette */}
      {colorPalette.length > 0 && (
        <div className="mb-4">
          <h4 className="text-sm font-medium text-gray-700 mb-2">色彩色盤</h4>
          <div className="flex gap-2 flex-wrap">
            {colorPalette.map((color, index) => (
              <div
                key={index}
                className="w-12 h-12 rounded border border-gray-300"
                style={{ backgroundColor: color }}
                title={color}
              />
            ))}
          </div>
        </div>
      )}

      {/* Emotion Keywords */}
      {emotionKeywords.length > 0 && (
        <div className="mb-4">
          <h4 className="text-sm font-medium text-gray-700 mb-2">情緒調性</h4>
          <div className="flex gap-2 flex-wrap">
            {emotionKeywords.map((emotion, index) => (
              <span
                key={index}
                className="px-2 py-1 bg-purple-100 text-purple-700 rounded text-xs"
              >
                {emotion}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Image References Grid */}
      {imageReferences.length > 0 && (
        <div className="mb-4">
          <h4 className="text-sm font-medium text-gray-700 mb-2">
            參考圖片 ({imageReferences.length})
          </h4>
          <div className="grid grid-cols-4 gap-2">
            {imageReferences.slice(0, isExpanded ? imageReferences.length : 8).map(
              (ref, index) => (
                <div
                  key={ref.photo_id || index}
                  className="relative aspect-square rounded overflow-hidden border border-gray-200"
                >
                  {ref.urls.thumb ? (
                    <img
                      src={ref.urls.thumb}
                      alt={ref.description || `Reference ${index + 1}`}
                      className="w-full h-full object-cover"
                      loading="lazy"
                    />
                  ) : (
                    <div
                      className="w-full h-full"
                      style={{ backgroundColor: ref.color || "#ccc" }}
                    />
                  )}
                  {ref.photographer?.name && (
                    <div className="absolute bottom-0 left-0 right-0 bg-black bg-opacity-50 text-white text-xs p-1 truncate">
                      {ref.photographer.name}
                    </div>
                  )}
                </div>
              )
            )}
          </div>
          {imageReferences.length > 8 && (
            <button
              onClick={() => setIsExpanded(!isExpanded)}
              className="mt-2 text-sm text-blue-600 hover:text-blue-800"
            >
              {isExpanded ? "收起" : `展開全部 (${imageReferences.length} 張)`}
            </button>
          )}
        </div>
      )}

      {/* Composition Summary */}
      {lens.schema_data?.composition_rules && (
        <div className="mb-4 text-sm text-gray-600">
          <span className="font-medium">留白比例：</span>
          {((lens.schema_data.composition_rules.whitespace_ratio || 0) * 100).toFixed(0)}%
          {lens.schema_data.composition_rules.geometric_preference && (
            <>
              {" · "}
              <span className="font-medium">幾何偏好：</span>
              {lens.schema_data.composition_rules.geometric_preference}
            </>
          )}
        </div>
      )}

      {/* Web Translation Rules */}
      {lens.schema_data?.web_translation_rules && (
        <div className="mb-4 text-sm text-gray-600">
          {lens.schema_data.web_translation_rules.border_radius && (
            <div>
              <span className="font-medium">邊框半徑：</span>
              {lens.schema_data.web_translation_rules.border_radius}
            </div>
          )}
          {lens.schema_data.web_translation_rules.shadow_style && (
            <div>
              <span className="font-medium">陰影風格：</span>
              {lens.schema_data.web_translation_rules.shadow_style}
            </div>
          )}
          {lens.schema_data.web_translation_rules.layout_density && (
            <div>
              <span className="font-medium">布局密度：</span>
              {lens.schema_data.web_translation_rules.layout_density}
            </div>
          )}
        </div>
      )}

      {/* Details Toggle */}
      <button
        onClick={() => setShowDetails(!showDetails)}
        className="text-sm text-gray-500 hover:text-gray-700"
      >
        {showDetails ? "隱藏" : "顯示"}技術詳情
      </button>

      {/* Technical Details */}
      {showDetails && (
        <div className="mt-4 p-3 bg-gray-50 rounded">
          <pre className="text-xs overflow-auto max-h-96">
            {JSON.stringify(lens.schema_data, null, 2)}
          </pre>
        </div>
      )}
    </div>
  );
}

