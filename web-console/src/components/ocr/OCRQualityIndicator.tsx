'use client';

import React from 'react';

interface OCRQuality {
  average_confidence?: number;
  overall_quality?: 'high' | 'medium' | 'low';
  low_confidence_segments?: number;
  total_blocks?: number;
}

interface OCRQualityIndicatorProps {
  quality: OCRQuality;
  ocrUsed?: boolean;
}

export default function OCRQualityIndicator({ quality, ocrUsed }: OCRQualityIndicatorProps) {
  if (!ocrUsed) {
    return null;
  }

  const overallQuality = quality.overall_quality || 'medium';
  const avgConfidence = quality.average_confidence || 0;
  const lowConfSegments = quality.low_confidence_segments || 0;

  const getQualityColor = (quality: string) => {
    switch (quality) {
      case 'high':
        return 'bg-green-100 text-green-700 border-green-300';
      case 'medium':
        return 'bg-yellow-100 text-yellow-700 border-yellow-300';
      case 'low':
        return 'bg-red-100 text-red-700 border-red-300';
      default:
        return 'bg-gray-100 text-gray-700 border-gray-300';
    }
  };

  const getQualityLabel = (quality: string) => {
    switch (quality) {
      case 'high':
        return 'High Quality';
      case 'medium':
        return 'Medium Quality';
      case 'low':
        return 'Low Quality';
      default:
        return 'Unknown';
    }
  };

  return (
    <div className="mt-2 p-2 bg-gray-50 rounded border border-gray-200">
      <div className="flex items-center justify-between mb-1">
        <span className="text-xs font-medium text-gray-700">OCR Quality</span>
        <span
          className={`px-1.5 py-0.5 rounded text-xs font-medium border ${getQualityColor(overallQuality)}`}
        >
          {getQualityLabel(overallQuality)}
        </span>
      </div>
      <div className="space-y-1">
        <div className="flex items-center justify-between text-xs">
          <span className="text-gray-600">Average Confidence:</span>
          <span className="font-medium text-gray-900">
            {(avgConfidence * 100).toFixed(1)}%
          </span>
        </div>
        {lowConfSegments > 0 && (
          <div className="flex items-center justify-between text-xs">
            <span className="text-gray-600">Low Confidence Segments:</span>
            <span className="font-medium text-red-600">{lowConfSegments}</span>
          </div>
        )}
        {overallQuality === 'low' && (
          <div className="mt-1 text-xs text-red-600 italic">
            ⚠️ Quality below recommended threshold. Please review carefully.
          </div>
        )}
      </div>
    </div>
  );
}






